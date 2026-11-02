"""요청 컨텍스트 — 핸들러 인자로 관통시키기엔 부수적인 요청 정보의 접근점.

    from svkit.web import reqctx
    ip = reqctx.client_ip()

contextvar 라 스레드풀로 넘어가는 동기 핸들러(`def`)에서도 유효하다 — anyio 가 컨텍스트를
복사해 실행한다.
"""
from __future__ import annotations

import os
from contextvars import ContextVar

from starlette.requests import Request
from svkit.loader import conf

_current: ContextVar[Request | None] = ContextVar("current_request", default=None)


class RequestContextMiddleware:
    """현재 요청을 contextvar 에 실어 두는 순수 ASGI 미들웨어."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _current.set(Request(scope, receive))
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)


def current_request() -> Request | None:
    """현재 요청. 요청 밖(부팅·백그라운드 잡)에서는 None."""
    return _current.get()


def header(name: str, default: str = "") -> str:
    request = _current.get()
    if request is None:
        return default
    return request.headers.get(name, default)


def proxy_hops() -> int:
    """신뢰하는 역프록시 hop 수 (env `TRUSTED_PROXY_HOPS`, 기본 2)."""
    try:
        return max(0, conf.get_int("TRUSTED_PROXY_HOPS"))
    except ValueError:
        return 2


def client_ip(default: str = "unknown") -> str:
    """역프록시 hop 을 반영한 클라이언트 IP.

    `X-Forwarded-For` 는 프록시가 왼쪽부터 덧붙이므로 **오른쪽에서 hop 번째**가 우리가
    신뢰할 수 있는 마지막 값이다. 헤더가 짧으면(프록시를 안 거친 직접 호출) 소켓
    주소를 쓴다 — 그쪽이 위조 불가능한 값이다.
    """
    request = _current.get()
    if request is None:
        return default
    parts = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",")
             if p.strip()]
    hops = proxy_hops()
    if hops and len(parts) >= hops:
        return parts[-hops]
    client = request.client
    return client.host if client else default


__all__ = ["RequestContextMiddleware", "current_request", "header",
           "client_ip", "proxy_hops"]
