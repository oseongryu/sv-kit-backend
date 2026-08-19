"""도메인 선언 헬퍼 — 모듈 하나가 곧 도메인이고, 배선은 관례로 찾는다.

    from svkit.loader.domain import domain

    DOMAIN = domain(__name__, title="화면 이름", tables=[...], nav=[...])

slug·라우터·migrate 는 전부 모듈 이름에서 관례로 도출한다.
키워드 인자는 **리터럴로만** 적는다 — 부팅 전 검증이 import 없이 AST 로 읽기
때문이다 (변수·연산 금지).
"""
import ast
import importlib
import importlib.util
import pkgutil
from pathlib import Path

MODULE_PREFIX = "module_"

from svkit import hooks


def _defines_migrate(pkg_name: str) -> bool:
    """모듈의 저장소(`<모듈>/db.py`)가 `migrate` 를 **정의하는지** import 없이 확인한다.

    파일 존재로 판정하면 안 된다 — 커널은 훅이 걸린 도메인마다 sqlite 커넥션을 먼저
    열고 부르므로, `migrate` 없는 저장소에도 훅이 걸리면 쓰지도 않을 파일이 생긴다.
    AST 로 읽는 이유는 이 판정이 env 가 깔리기 전에 돌 수 있어서다.
    """
    spec = importlib.util.find_spec(f"{pkg_name}.db")
    if spec is None or not spec.origin:
        return False
    tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == "migrate" for node in tree.body)


def _collect_routers(pkg_name: str) -> list:
    """모듈 안의 `api*.py` 를 import 해 그 안의 라우터를 모은다.

    **도메인 자산은 그 모듈 폴더에 모여 있다** — 라우트(`api*.py`)·서비스(`service*.py`)·
    저장소(`db.py`). 그래서 도메인을 빼는 일이 폴더 삭제 하나로 끝난다.
    """
    from fastapi import APIRouter

    pkg = importlib.import_module(pkg_name)
    names = sorted(m.name for m in pkgutil.iter_modules(pkg.__path__)
                   if m.name == "api" or m.name.startswith("api_"))
    seen: set[int] = set()
    routers = []
    for n in names:
        mod = importlib.import_module(f"{pkg_name}.{n}")
        for value in vars(mod).values():
            if isinstance(value, APIRouter) and id(value) not in seen:
                seen.add(id(value))
                routers.append(value)
    return routers


def _make_migrate(pkg_name: str, nav):
    def _migrate(conn):
        if _defines_migrate(pkg_name):
            importlib.import_module(f"{pkg_name}.db").migrate(conn)
        seeder = hooks.nav_seeder()
        if nav and seeder:
            seeder(conn, nav)
    return _migrate


class _Domain(dict):
    """`routers` 를 **처음 읽을 때** 수집하는 DOMAIN dict — import 시점에 env 가 굳는 것을 막는다."""

    ROUTER_KEY = "routers"

    def __init__(self, pkg_name, base):
        super().__init__(base)
        self._pkg = pkg_name

    def __missing__(self, key):
        if key != self.ROUTER_KEY:
            raise KeyError(key)
        self[key] = _collect_routers(self._pkg)
        return self[key]

    def get(self, key, default=None):
        # dict.get 은 __missing__ 을 타지 않는다 — 커널이 get 으로 읽는다.
        if key == self.ROUTER_KEY:
            return self[key]
        return super().get(key, default)


def domain(pkg_name: str, *, slug: str = "", title: str = "",
           requires=(), tables=(), nav=(), **extra) -> dict:
    """DOMAIN dict 조립. pkg_name 은 호출부의 `__name__` 그대로."""
    name = pkg_name.rsplit(".", 1)[-1]
    if name.startswith(MODULE_PREFIX):
        name = name[len(MODULE_PREFIX):]
    meta = {
        "slug": slug or name,
        "title": title,
        "requires": list(requires),
        "tables": list(tables),
        **extra,
    }
    nav = list(nav)
    if nav:
        meta["nav"] = nav
    # 라우터·저장소는 **모듈 패키지 안**에 있다 — slug 가 아니라 pkg_name 으로 찾는다
    # (모듈 이름과 slug 를 다르게 붙인 모듈이 있어 둘이 갈린다).
    if nav or _defines_migrate(pkg_name):
        meta["migrate"] = _make_migrate(pkg_name, nav)
    return _Domain(pkg_name, meta)  # "routers" 는 처음 읽을 때 수집된다
