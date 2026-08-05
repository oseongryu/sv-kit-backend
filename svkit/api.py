"""API 공통 포맷 — 모든 도메인 `api/` 계층이 공유하는 서빙 헬퍼.

응답 규약(ok/err)은 `svkit.response` 를, blueprint/페이징은 이 모듈을 쓴다.

- `make_blueprint(slug)`: `/api/<slug>` prefix blueprint (라우트는 상대경로로 선언)
- `page_args()`:         `?limit=&offset=` 파싱 → `Page(limit, offset)`

**주소 규약과 인자 이름은 svkit2 와 맞춰 뒀다.** `make_router` 라는 별칭도
두는데, 이름만 같을 뿐 **반환 타입은 각 프레임워크의 것**이다(여기는 Flask
Blueprint, svkit2 는 FastAPI APIRouter). 라우트를 데이터로 모아 어댑터가
실체화하는 중립층은 만들지 않는다 — 한 번 만들었다가 되돌린 구조다.
합칠 때 줄어드는 것은 도메인 파일의 **import·선언 줄**이고, 핸들러 본문은
각 프레임워크의 방식(동기+`flask.request` / async+DI)으로 남는다.
"""
from flask import Blueprint, request

from svkit.base import Page, clamp_page, domain_prefix


class OkBlueprint(Blueprint):
    """반환값을 규약 모양으로 감싸는 blueprint (`auto_ok=True` 일 때 쓰인다).

    svkit2 의 `OkRoute` 와 같은 역할이다 — 핸들러가 알맹이만 반환해도
    `{ok:true, data}` 로 나간다. `(body, status)` 튜플과 Response 객체는
    Flask 자신의 규약이므로 손대지 않는다.
    """

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        if view_func is not None:
            view_func = _wrap_ok(view_func)
        return super().add_url_rule(rule, endpoint, view_func, **options)


def _wrap_ok(view_func):
    from functools import wraps

    from svkit.response import envelope

    @wraps(view_func)
    def inner(*a, **kw):
        value = view_func(*a, **kw)
        if isinstance(value, tuple):  # (body, status) — 이미 Flask 규약
            return value
        wrapped = envelope(value)
        return wrapped if not isinstance(wrapped, dict) else (wrapped, 200)

    return inner


def make_blueprint(slug: str, prefix: str | None = None,
                   tags: list[str] | None = None, auto_ok: bool = False) -> Blueprint:
    """`/api/<slug>` prefix blueprint 생성. 라우트는 `@bp.get("/items")` 상대경로로.

    prefix 를 주면 그 값이 그대로 쓰인다(주소 규약을 벗어나는 라우터용).
    tags 는 svkit2(Swagger 그룹명)와 인자 모양을 맞추기 위한 것으로, Flask 판에서는
    `bp.tags` 에 보관만 한다 — 도메인 선언 줄이 두 판에서 같아진다.
    auto_ok=True 면 핸들러가 알맹이만 반환해도 규약으로 감싼다(svkit2 기본 동작).
    """
    cls = OkBlueprint if auto_ok else Blueprint
    bp = cls(slug, __name__, url_prefix=domain_prefix(slug) if prefix is None else prefix)
    bp.tags = tags or [slug]
    return bp


#: svkit2 와 선언 줄을 맞추기 위한 별칭. 반환 타입은 Flask Blueprint 다.
make_router = make_blueprint


def page_args(default_limit: int = 50, max_limit: int = 500) -> Page:
    """페이징 파라미터 파싱. 반환: `Page(limit, offset)`.

    NamedTuple 이라 `limit, offset = page_args()` 는 그대로 되고,
    svkit2 처럼 `page.limit` 로도 읽힌다. limit 은 max_limit 로 상한.
    """
    return clamp_page(request.args.get("limit", type=int),
                      request.args.get("offset", type=int),
                      default_limit, max_limit)


__all__ = ["make_blueprint", "make_router", "page_args", "Page", "OkBlueprint"]