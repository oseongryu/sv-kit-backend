"""응답 규약 — 성공 `{ok, data, meta?}` · 실패 `{ok:false, error}`.

**핸들러 반환값은 라우트 클래스가 자동으로 감싼다.** 도메인 코드는 알맹이만 돌려주면 된다.

    return service.list_items()          # → {"ok": true, "data": [...]}
    return WithMeta(rows, {"total": n})  # → {"ok": true, "data": [...], "meta": {...}}
    raise ApiError("작업 없음", 404)      # → {"ok": false, "error": "작업 없음"}

`ok()` 는 규약 본문을 직접 만들어야 하는 특수 경로에만 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from svkit.infra.errors import ImageDecodeError
from svkit.web.errors import ApiError
from svkit.infra.logger import get_logger

log = get_logger(__name__)


@dataclass
class WithMeta:
    """`{ok, data, meta}` 를 만들고 싶을 때 반환한다."""

    data: Any
    meta: Any


def ok(data: Any = None, meta: Any = None) -> dict:
    """규약 본문을 직접 만든다. 보통은 알맹이만 반환하면 OkRoute 가 감싼다."""
    body: dict[str, Any] = {"ok": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    return body


def err(message: str, status: int = 400) -> HTTPException:
    """실패를 만들어 돌려준다 — 호출부에서 `raise err(...)`."""
    return HTTPException(status_code=status, detail=message)


def is_wrapped(value: Any) -> bool:
    return isinstance(value, dict) and value.get("ok") is True and "data" in value


def envelope(value: Any) -> Any:
    """핸들러 반환값을 규약 형태로. 이미 규약이거나 Response 면 손대지 않는다."""
    if isinstance(value, Response):
        return value
    if isinstance(value, WithMeta):
        return {"ok": True, "data": value.data, "meta": value.meta}
    if is_wrapped(value):
        return value
    return {"ok": True, "data": value}


def error_body(message: str) -> dict:
    return {"ok": False, "error": message}


def install_error_handlers(app: FastAPI, expose_detail: bool = True) -> None:
    """모든 실패 응답을 규약으로 통일한다 (앱 조립 시 1회)."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return JSONResponse(error_body(e.message), status_code=e.status)

    # Starlette HTTPException 에 걸어야 라우터 404·405 도 잡힌다 — 핸들러 조회가
    # MRO 의 부모를 기준으로 하므로 fastapi.HTTPException 에만 걸면 새는 경로가 있다.
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, e: StarletteHTTPException):
        return JSONResponse(error_body(str(e.detail)), status_code=e.status_code)

    @app.exception_handler(ImageDecodeError)
    async def _image_error(_: Request, e: ImageDecodeError):
        return JSONResponse(error_body(str(e)), status_code=400)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, e: RequestValidationError):
        first = (e.errors() or [{}])[0]
        where = ".".join(str(x) for x in first.get("loc", ())[1:]) or "요청"
        msg = first.get("msg", "검증 실패")
        return JSONResponse(error_body(f"파라미터 오류({where}): {msg}"), status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, e: Exception):
        """예상 못 한 예외도 규약 유지 — 원인은 로그로, 응답은 같은 모양으로."""
        log.exception("처리되지 않은 예외")
        if not expose_detail:
            return JSONResponse(error_body("서버 오류"), status_code=500)
        first = str(e).strip().splitlines()[0] if str(e).strip() else ""
        message = f"{type(e).__name__}: {first}"[:300] if first else type(e).__name__
        return JSONResponse(error_body(message), status_code=500)


__all__ = ["ApiError", "WithMeta", "ok", "err", "envelope", "error_body",
           "install_error_handlers", "is_wrapped"]
