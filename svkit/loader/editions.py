"""edition 로더 — 배포 변형 배선으로 모듈을 조합해 부팅한다.

각 edition.py 는 싣는 모듈 전부를 담은 `MODULES`(첫 항목이 대표 도메인)와 세 함수를
노출한다. 그 목록이 곧 게이팅이다 — 목록에 없는 모듈은 import 되지 않는다.

  setup_env()   — 커널 import 전에 호출. APP_* env 는 반드시 여기서 깔아야 한다.
  create_app()  — 앱 조립
  run_dev(app)  — 개발 서버 실행
"""
import importlib
import os
import sys
from pathlib import Path

from svkit import hooks

BACKEND_ROOT = hooks.app_root()
MODULE_PREFIX = "module_"


EDITIONS_DIR = BACKEND_ROOT / "editions"


def module_dir(name: str) -> Path:
    """edition 이름 → 배선 디렉토리. 이름을 다는 층은 이 하나다."""
    return EDITIONS_DIR / name


def discover() -> list[str]:
    """설치된 배포 변형 목록. 파일 존재가 곧 선언이다."""
    return sorted(p.parent.name for p in EDITIONS_DIR.glob("*/edition.py"))


def declared_modules(name: str) -> tuple:
    """`editions/<name>/edition.py` 의 MODULES — **import 하지 않고** AST 로 읽는다.

    한 프로세스에 edition 을 둘 이상 로드하지 않기 위함이다. 절삭 도구도 같은 값을
    읽는다(`scripts/z_carve.sh`).
    """
    import ast

    src = (EDITIONS_DIR / name / "edition.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MODULES" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise RuntimeError(f"editions/{name}/edition.py 에 MODULES 가 없다")


def resolve(explicit: str | None = None) -> str:
    """edition 결정 — 인자 → env(EDITION→FLAVOR) → backend/.edition(→.flavor) → 하나뿐이면 그것.

    변형이 둘 이상인데 지정이 없으면 실패시킨다. 기본값을 두면 구성이 다른 리포
    (일부 변형만 담은 절삭본 등)에서 없는 edition 을 찾다 죽는다.
    """
    name = (explicit or os.environ.get("EDITION") or os.environ.get("FLAVOR") or "").strip()
    if name:
        return name
    for local in (BACKEND_ROOT / ".edition", BACKEND_ROOT / ".flavor"):
        if local.is_file():
            name = local.read_text(encoding="utf-8").strip()
            if name:
                return name
    found = discover()
    if len(found) == 1:
        return found[0]
    if not found:
        raise RuntimeError(f"배포 변형이 없다 — {EDITIONS_DIR}/<이름>/edition.py 가 필요하다")
    raise RuntimeError(
        f"배포 변형이 여럿이라 EDITION 지정이 필요하다 (가능: {', '.join(found)}). "
        f"env EDITION 또는 {BACKEND_ROOT / '.edition'} 파일로 지정할 것"
    )


def module_names(self_pkg: str, modules=()) -> list[str]:
    """edition 이 싣는 모듈 패키지 이름들 — 자기 자신(self_pkg)이 항상 첫 번째다."""
    names = [self_pkg] if self_pkg else []
    for name in modules:
        pkg = f"{MODULE_PREFIX}{name}"
        if not (BACKEND_ROOT / pkg).is_dir():
            raise RuntimeError(f"edition 이 요구하는 모듈이 없다: {BACKEND_ROOT / pkg}")
        names.append(pkg)
    return names


def load(name: str):
    """backend 루트를 sys.path 에 넣은 뒤 그 변형의 배선 모듈을 import 한다."""
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    return importlib.import_module(f"editions.{name}.edition")
