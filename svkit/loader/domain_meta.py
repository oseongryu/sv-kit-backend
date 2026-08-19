"""모듈 선언 읽기 — edition 이 싣는 모듈들의 `DOMAIN` 을 검증한다.

`DOMAIN` 에서 **리터럴 값만** AST 로 뽑는다 — 이 검증은 env 가 깔리기 전에 돌아야 해서
모듈을 import 할 수 없다. 비리터럴 값은 조용히 건너뛴다.
"""
import ast
from pathlib import Path

from svkit import hooks


def _literals(init_path: Path) -> dict:
    """`DOMAIN = {...}` 에서 리터럴로 평가되는 항목만 뽑는다."""
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "DOMAIN" for t in node.targets):
            continue
        if isinstance(node.value, ast.Dict):
            items = list(zip(node.value.keys, node.value.values))
        elif isinstance(node.value, ast.Call):
            items = [(ast.Constant(kw.arg), kw.value)
                     for kw in node.value.keywords if kw.arg]
        else:
            return {}
        out = {}
        for key, value in items:
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            try:
                out[key.value] = ast.literal_eval(value)
            except (ValueError, TypeError, SyntaxError):
                continue  # bp·migrate 등 비리터럴 — 여기선 쓰지 않는다
        return out
    return {}


def read(module_names, backend_root=None) -> dict[str, dict]:
    """`{모듈 패키지명: {리터럴 키: 값}}` — edition 이 싣는 모듈들의 DOMAIN 선언.

    import 없이 파일로 훑으므로 env 가 깔리기 전에도 쓸 수 있다.
    `DOMAIN` 이 없는 모듈(공용 라이브러리)은 빈 dict 가 된다.
    """
    root = Path(backend_root) if backend_root else hooks.app_root()
    found = {}
    for name in module_names:
        init = root / name / "__init__.py"
        if init.is_file():
            found[name] = _literals(init)
    return found


def check(module_names, backend_root=None) -> str:
    """싣는 모듈들의 선언을 검증하고 `APP_DOMAIN_PACKAGES` 값을 만든다.

    검증은 둘이다 — `requires` 가 가리키는 모듈이 목록에 있는가(없으면 그 도메인은
    조용히 반쪽으로 뜬다), 그리고 테이블 소유자가 겹치지 않는가.
    """
    names = list(module_names)
    meta = read(names, backend_root)

    for name in names:
        for dep in meta.get(name, {}).get("requires") or []:
            # requires 는 slug 로 적는다 — 이미 목록에 있는 이름은 그대로, 나머지는 module_<slug>
            pkg = dep if dep in meta else f"module_{dep}"
            if pkg not in meta:
                raise RuntimeError(f"모듈 '{name}' 이 요구하는 '{pkg}' 가 목록에 없다")

    _check_table_owners(meta, set(meta))
    return ",".join(names)


def _check_table_owners(meta: dict, enabled: set[str]) -> None:
    """켜진 도메인들이 같은 테이블을 소유한다고 선언하면 실패시킨다.

    `tables` 는 "이 도메인을 떼면 무엇이 따라가나"의 답이라 소유자가 둘일 수 없다.
    같은 DB 를 공유하는 것은 함께 켜진 도메인들이므로 검사 범위도 그 집합이다.
    """
    owner: dict[str, str] = {}
    for name in sorted(enabled):
        for table in meta[name].get("tables") or []:
            if table in owner:
                raise RuntimeError(
                    f"테이블 '{table}' 의 소유가 둘이다: {owner[table]}, {name}"
                )
            owner[table] = name
