"""프레임워크 중립 예외 — 웹 프레임워크를 import 하지 않는다.

서비스 층은 프레임워크를 모르는 것이 규약이라, 실패를 표현할 수단도 프레임워크와
무관해야 한다. 응답으로의 변환은 커널이 한다.

    raise ApiError("작업 없음", 404)
"""
from __future__ import annotations


class ApiError(Exception):
    """규약 실패 응답으로 변환되는 예외."""

    __slots__ = ("message", "status")

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status

    def __repr__(self) -> str:
        return f"ApiError({self.message!r}, status={self.status})"


__all__ = ["ApiError"]
