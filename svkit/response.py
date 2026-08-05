"""공통 응답 규약 — 성공 `{ok, data, meta?}`, 실패 `{ok:false, error}`.

프론트 `@sv/kit-ui` 의 api 가 이 규약을 기대한다. **본문 dict 를 만드는 자리는
`svkit.base` 하나**이고(svkit2 도 같은 것을 쓴다) 여기서는 Flask 응답으로
바꿔 주기만 한다.

두 가지 실패 표현이 같은 응답을 낸다:

    return err("작업 없음", 404)          # 기존 방식(그대로 유지)
    raise ApiError("작업 없음", 404)      # svkit2 와 같은 방식

`raise` 쪽은 `install_error_handlers` 가 변환한다 — `create_app` 이 부팅 때
등록하므로 도메인은 그냥 던지면 된다.
"""
from flask import jsonify

from svkit.base import (ApiError, WithMeta, envelope as _envelope, error_body,
                        is_wrapped, ok_body)


def ok(data=None, meta=None, status=200):
    """성공 응답. 반환: (Response, status) — Flask 뷰가 그대로 반환한다."""
    return jsonify(ok_body(data, meta)), status


def err(message, status=400):
    """실패 응답. 반환: (Response, status)."""
    return jsonify(error_body(message)), status


def envelope(value):
    """핸들러 반환값을 규약 모양으로(이미 규약이거나 Response 면 손대지 않는다).

    `make_blueprint(..., auto_ok=True)` 가 쓴다 — svkit2 의 `OkRoute` 와 같은 역할.
    """
    from flask import Response

    return _envelope(value, passthrough=(Response,))


def install_error_handlers(app, expose_detail: bool = False,
                           wrap_http_errors: bool = False) -> None:
    """`raise ApiError(...)` 를 `{ok:false, error}` 로 바꾼다.

    expose_detail: 예상 못 한 예외(500)의 원인을 응답 본문에 싣는다. 공개 API 는
        끄는 게 맞고(내부 구조가 새어 나간다), 운영자만 쓰는 관리 콘솔은 켜는 게
        맞다 — 화면이 원인을 말해 주지 못하면 콘솔을 보는 이유가 사라진다.
    wrap_http_errors: Flask 의 404/405/500 까지 규약 모양으로 바꾼다(svkit2 기본
        동작과 같아진다). 기본은 off 다 — 켜면 정적 페이지의 404 도 JSON 이
        되므로, 기존 앱의 동작을 조용히 바꾸지 않으려고 선택으로 뒀다.
    """
    import logging

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return err(e.message, e.status)

    if not wrap_http_errors:
        return

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        return err(e.description or e.name, e.code or 500)

    @app.errorhandler(Exception)
    def _unexpected(e: Exception):
        logging.getLogger("svkit.error").exception("처리되지 않은 예외")
        if not expose_detail:
            return err("서버 오류가 발생했습니다.", 500)
        first = str(e).strip().splitlines()[0] if str(e).strip() else ""
        message = f"{type(e).__name__}: {first}"[:300] if first else type(e).__name__
        return err(message, 500)


__all__ = ["ok", "err", "envelope", "install_error_handlers",
           "ok_body", "error_body", "is_wrapped", "WithMeta"]