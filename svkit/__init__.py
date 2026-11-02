"""svkit — FastAPI 웹 커널·로더·DB 커널. 영역별 하위 패키지로 갈려 있다.

    svkit.loader/web/db/automation/browser/term/infra

**영역은 곧 의존 등급이다** — 커널(`loader`·`web`)은 fastapi 하나로 돌고 나머지는 extra 다.
쓰지 않는 영역의 의존은 깔지 않아도 되므로, 선택 영역은 최상위 import 대신 `has()` 로 묻는다.

킷은 조각 여럿일 수 있다 — env `SVKIT_PATH`(os.pathsep 구분)로 준 디렉토리에 `svkit/` 이
있으면 이 패키지의 `__path__` 에 붙어 **한 이름공간**이 된다. 공개 커널은 pip 로 깔고
비공개 자산 조각만 그렇게 얹는 식이다. 같은 영역을 둘이 가지면 뒤가 조용히 가려지므로
그 자리에서 실패시킨다.

앱 고유값 주입은 `svkit.hooks` 가 받는다.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_SELF = Path(__file__).resolve().parent


def _extra_roots() -> list[Path]:
    """env `SVKIT_PATH` 가 준 추가 조각의 `svkit/` 들 (선언 순서 유지, 중복 제거)."""
    found: list[Path] = []
    seen = {_SELF}
    for raw in (os.environ.get("SVKIT_PATH") or "").split(os.pathsep):
        if not raw.strip():
            continue
        src = (Path(raw.strip()) / "svkit").resolve()
        if src.is_dir() and src not in seen:
            seen.add(src)
            found.append(src)
    return found


def _areas_of(root: Path) -> list[str]:
    """그 조각이 가진 영역 이름 — 하위 패키지 + 최상위 평면 모듈."""
    names = [p.name for p in root.iterdir()
             if p.is_dir() and (p / "__init__.py").is_file()]
    names += [p.stem for p in root.glob("*.py") if p.name != "__init__.py"]
    return sorted(names)


def _owners() -> dict[str, Path]:
    """영역 → 그것을 가진 조각. 겹치면 실패시킨다.

    겹치면 앞 조각이 이기고 뒤가 조용히 가려져 "파일은 있는데 import 되는 것은 다른 것"이
    된다. 영역 이름이 곧 조각 간 소유 선언이다.
    """
    owner: dict[str, Path] = {}
    for root in (_SELF, *_extra_roots()):
        for area in _areas_of(root):
            if area in owner:
                raise ImportError(
                    f"킷 이름 '{area}' 의 소유가 둘이다: {owner[area]}, {root} — "
                    "조각은 서로 다른 영역만 갖는다")
            owner[area] = root
    return owner


_AREAS = _owners()

__path__ = [str(_SELF), *(str(p) for p in _extra_roots())]


def areas() -> list[str]:
    """실린 영역 이름들."""
    return sorted(_AREAS)


def has(area: str) -> bool:
    """그 영역이 실렸는가. 선택 영역은 최상위 import 말고 이걸로 먼저 묻는다."""
    return area in _AREAS


def require(area: str) -> None:
    """없으면 그 자리에서 실패시킨다 — 그 배포에 반드시 있어야 하는 영역용."""
    if area not in _AREAS:
        raise ImportError(
            f"킷 영역 '{area}' 이 없다 — 조각을 SVKIT_PATH 로 붙이거나 그 판을 설치한다")


def source_of(area: str) -> Path | None:
    """그 영역을 준 조각의 `svkit/` 경로 (진단용)."""
    return _AREAS.get(area)


def importable(area: str) -> bool:
    """`import svkit.<area>` 가 실제로 되는가 — 영역은 있는데 **의존이 없는** 경우를 가른다."""
    if not has(area):
        return False
    try:
        return importlib.util.find_spec(f"svkit.{area}") is not None
    except ImportError:
        return False


__all__ = ["areas", "has", "require", "source_of", "importable"]
