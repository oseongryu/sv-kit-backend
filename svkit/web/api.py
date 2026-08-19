"""API 서빙 규약 — `/api/<slug>` 라우터·응답 자동 래핑·페이징 파싱."""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, NamedTuple, get_type_hints

from fastapi import APIRouter, Depends, Query
from fastapi.routing import APIRoute

from svkit.web.response import WithMeta, envelope


def _resolved_signature(fn: Callable) -> inspect.Signature:
    """원본 시그니처를 해석된 타입으로 만든다 — 문자열 어노테이션은 원본 모듈 기준."""
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn, include_extras=True)
    except Exception:  # noqa: BLE001 — 런타임에 못 푸는 전방 참조는 원본 그대로 둔다
        hints = {}
    params = [p.replace(annotation=hints.get(p.name, p.annotation))
              for p in sig.parameters.values()]
    # 반환 어노테이션은 뗀다 — 남으면 감싼 dict 가 그 모델에 걸려 검증에서 죽는다.
    return sig.replace(parameters=params, return_annotation=inspect.Signature.empty)


def _wrap_endpoint(fn: Callable) -> Callable:
    """핸들러를 감싸되 시그니처는 보존한다 (FastAPI 의 주입이 원본을 봐야 한다)."""
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def inner(*args: Any, **kwargs: Any):
            return envelope(await fn(*args, **kwargs))

    else:

        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any):
            return envelope(fn(*args, **kwargs))

    inner.__signature__ = _resolved_signature(fn)  # inspect.signature 가 이걸 먼저 본다
    return inner


class OkRoute(APIRoute):
    """반환값을 규약으로 감싸는 라우트. `make_router` 가 이걸 쓴다."""

    def __init__(self, path: str, endpoint: Callable, **kwargs: Any) -> None:
        kwargs["response_model"] = None  # 반환 어노테이션이 래핑을 되돌리지 못하게
        super().__init__(path, _wrap_endpoint(endpoint), **kwargs)


def make_router(slug: str, prefix: str | None = None,
                tags: list[str] | None = None) -> APIRouter:
    """`/api/<slug>` prefix 라우터. prefix 를 주면 그 값이 그대로 쓰인다."""
    return APIRouter(
        prefix=f"/api/{slug}" if prefix is None else prefix,
        tags=tags or [slug],
        route_class=OkRoute,
    )


class Page(NamedTuple):
    limit: int
    offset: int


def page_args(default_limit: int = 50, max_limit: int = 500):
    """`?limit=&offset=` 파싱 의존성 — `page: Page = page_args()`."""

    def _parse(limit: int = Query(default_limit, ge=1),
               offset: int = Query(0, ge=0)) -> Page:
        return Page(min(limit, max_limit), offset)

    return Depends(_parse)


__all__ = ["make_router", "page_args", "Page", "OkRoute", "WithMeta"]
