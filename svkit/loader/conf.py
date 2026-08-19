"""설정 창구 — **파이썬에서 `config/*.yml` 을 해석하는 곳은 여기 하나다.**

`.env` 생성·매니페스트 해석·계약 테스트가 전부 이 함수들을 부른다. 병합 순서와 `${NAME}` 치환 규칙을 각자 구현하면
같은 문법이 층마다 다르게 해석된다.
"""
# **이 영역은 옛 파이썬에서도 import 돼야 한다** — 배포처의 `.env` 생성이
# 호스트 파이썬으로 이 창구를 부르는데 그 파이썬은 3.10 미만일 수 있다.
# `dict | None` 같은 주석이 로드 시점에 평가되면 거기서 죽는다.
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

from svkit import hooks

try:
    import yaml
except ImportError:  # PyYAML 없는 호스트 — 아래 평면 파서로 읽는다
    yaml = None

_CACHE: dict | None = None
_SOURCES: list[str] = []

#: 값 안에서 다른 설정을 가리키는 참조 — `http://<서비스>:${SOME_PORT}`.
#: compose 의 `${NAME:-기본}` 문법은 지원하지 않는다 (이름 하나만).
_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_REF_DEPTH = 5


def _config_dir() -> Path | None:
    explicit = os.environ.get("APP_CONFIG_DIR")
    if explicit:
        p = Path(explicit)
        return p if p.is_dir() else None
    here = hooks.app_root()
    for parent in (here, *here.parents):
        candidate = parent / "config"
        if (candidate / "common.yml").is_file():
            return candidate
    return None


def _capabilities(edition: str) -> list[str]:
    """`editions/<edition>/edition.py` 의 `CAPABILITIES` 리터럴 — 선언 순서 그대로.

    없거나 읽지 못하면 빈 목록이다 (예외를 올리지 않는다). import 하지 않는 이유는
    이 함수가 `setup_env()` 보다 먼저 돌 수 있어서다 — AST 로만 읽는다.
    """
    if not edition:
        return []
    path = hooks.app_root() / "editions" / edition / "edition.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "CAPABILITIES" for t in node.targets):
            continue
        try:
            return [str(v) for v in ast.literal_eval(node.value)]
        except (ValueError, TypeError, SyntaxError):
            return []
    return []


_FLAT_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def _load_flat(text: str, path: Path) -> dict:
    """PyYAML 없는 호스트용 폴백. `config/*.yml` 은 **평면 `KEY: value`** 라는 계약이고,
    그 형태가 아닌 줄을 만나면 조용히 넘기지 않고 죽는다."""
    out: dict = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _FLAT_LINE.match(line)
        if not m:
            raise ValueError(f"평면 KEY: value 가 아니다 ({path}:{lineno}): {raw}")
        value = m.group(2).strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        elif re.fullmatch(r"-?\d+", value):
            value = int(value)
        elif re.fullmatch(r"-?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", value):
            value = float(value)
        out[m.group(1)] = value
    return out


def _load_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        return _load_flat(text, path)
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"설정 파일은 KEY: value 매핑이어야 한다: {path}")
    return {str(k): v for k, v in data.items()}


def expand(text: str, values: dict | None = None, use_env: bool = True) -> str:
    """`${NAME}` 을 채운다. 해석 순서는 `get()` 과 같다 — os.environ 이 먼저다.

    `values` 를 생략하면 현재 스코프의 병합값을 쓴다 — 소비처가 값 출처를 다시 고르지
    않게 하는 것이 이 기본값의 목적이다. `use_env=False` 는 **파일끼리 대조하는 검사**용
    이다(계약 테스트) — 그 판정이 호스트 env 에 따라 달라지면 안 된다.

    **못 찾은 이름은 그대로 남긴다** — 빈 문자열로 지우면 `http://:8503` 같은 주소가
    조용히 만들어져 502 로만 드러난다. 중첩·순환은 깊이 `_REF_DEPTH` 에서 멈춘다.
    """
    if values is None:
        values = _merged()

    def one(m):
        name = m.group(1)
        if use_env and name in os.environ:
            return os.environ[name]
        return str(values.get(name, m.group(0)))

    for _ in range(_REF_DEPTH):
        if "${" not in text:
            break
        text = _REF.sub(one, text)
    return text


def _expand_all(values: dict) -> dict:
    """문자열 값의 참조를 푼 사본. 참조가 없으면 원본 그대로다."""
    return {k: (expand(v, values) if isinstance(v, str) and "${" in v else v)
            for k, v in values.items()}


def _merged() -> dict:
    """common → <기능> → <edition> → local 순으로 덮어쓴 값(참조는 푼 뒤다).
    os.environ 은 포함하지 않는다.

    `<기능>.yml` 은 현재 edition 이 `CAPABILITIES` 로 선언한 공용 기능뿐이고 선언 순서를
    따른다 — 선언하지 않은 변형에서는 그 파일이 아예 읽히지 않는다.
    """
    global _CACHE, _SOURCES
    if _CACHE is not None:
        return _CACHE
    merged: dict = {}
    sources: list[str] = []
    d = _config_dir()
    if d:
        edition = os.environ.get("EDITION") or os.environ.get("FLAVOR") or ""
        names = ["common.yml"]
        names += [f"{c}.yml" for c in _capabilities(edition)]
        names += [f"{edition}.yml" if edition else "", "local.yml"]
        for name in names:
            if not name:
                continue
            path = d / name
            values = _load_file(path)
            if values:
                merged.update(values)
                sources.append(str(path))
    _CACHE, _SOURCES = _expand_all(merged), sources
    return _CACHE


def reload() -> None:
    global _CACHE, _SOURCES
    _CACHE, _SOURCES = None, []


def sources() -> list[str]:
    _merged()
    return list(_SOURCES)


def all_values(on_conflict=None) -> dict:
    """**전 변형·전 기능**의 yml 을 합친 값 (참조는 푼 뒤). 캐시하지 않는다.

    한 프로세스가 보는 스코프(`_merged()`)와 다른 자리가 둘 있다 — `.env` 생성은 compose 가
    변형 전부를 한 파일로 보므로 전량이 필요하고, 계약 검사도 전 변형을 한꺼번에 대조한다.
    병합 순서는 `common → 나머지(이름순) → local` 이고 같은 키를 둘이 다르게 정하면
    **뒤가 이긴다** (변형 전용 값은 서로 겹치지 않는다는 전제다).

    `on_conflict(key, prev_path, path)` 를 주면 그 전제가 깨질 때 알려 준다 — 판단은
    부르는 쪽 몫이라 창구는 진단만 넘기고 계속 병합한다.
    """
    d = _config_dir()
    if not d:
        return {}
    names = ["common.yml"]
    names += sorted(p.name for p in d.glob("*.yml")
                    if p.name not in ("common.yml", "local.yml"))
    names += ["local.yml"]
    merged: dict = {}
    seen: dict[str, str] = {}
    for name in names:
        path = d / name
        for key, value in _load_file(path).items():
            prev = seen.get(key)
            if (on_conflict and prev and prev != str(d / "common.yml")
                    and name != "local.yml" and merged.get(key) != value):
                on_conflict(key, prev, str(path))
            merged[key], seen[key] = value, str(path)
    return _expand_all(merged)


def as_env(values: dict | None = None) -> dict[str, str]:
    """`.env` 한 줄씩에 해당하는 문자열 dict.

    값이 없는 키(`KEY:`)는 **빈 문자열로 남긴다** — 키를 빼면 compose 의 `${NAME}` 이
    미정의가 된다.
    """
    out: dict[str, str] = {}
    for key, value in (all_values() if values is None else values).items():
        if value is None:
            out[key] = ""
        elif isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            out[key] = ",".join(str(v) for v in value)
        else:
            out[key] = str(value)
    return out


_MISSING = object()


def get(name: str, default=_MISSING):
    """os.environ 이 이기고, 없으면 config 값, 그것도 없으면 default. 빈 문자열은 값으로 친다.

    config 안 우선순위는 local > <edition> > <기능> > common 이다.
    """
    if name in os.environ:
        return os.environ[name]
    values = _merged()
    if name in values:
        return values[name]
    if default is _MISSING:
        return None
    return default


def require(name: str):
    value = get(name)
    if value is None or value == "":
        raise RuntimeError(f"설정값이 없다: {name} (config/*.yml 또는 환경변수)")
    return value


def get_str(name: str, default: str = "") -> str:
    value = get(name, default)
    return default if value is None else str(value)


def get_int(name: str, default: int = 0) -> int:
    value = get(name, default)
    if value is None or value == "":
        return default
    return int(value)


def get_float(name: str, default: float = 0.0) -> float:
    value = get(name, default)
    if value is None or value == "":
        return default
    return float(value)


def get_bool(name: str, default: bool = False) -> bool:
    value = get(name, default)
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def get_list(name: str, default: list | None = None, sep: str = ",") -> list[str]:
    value = get(name, None)
    if value is None or value == "":
        return list(default or [])
    if isinstance(value, list):
        return [str(v) for v in value]
    return [item.strip() for item in str(value).split(sep) if item.strip()]


def scope_env() -> dict[str, str]:
    """현재 스코프(`_merged()`)의 값만 `.env` 형식으로. os.environ 은 섞지 않는다."""
    return as_env(_merged())
