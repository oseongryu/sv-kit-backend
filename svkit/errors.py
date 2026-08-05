"""API 실패 표현 — `svkit.base` 의 예외 계열을 그대로 쓴다.

도메인은 `raise ApiError('작업 없음', 404)` 하나만 쓴다. Flask 판에서도
`svkit.response.install_error_handlers` 가 이 예외를 `{ok:false, error}` 로
바꿔 주므로, `return err(msg, status)` 와 `raise ApiError(msg, status)` 중
어느 쪽으로 써도 같은 응답이 나간다.

같은 이름·같은 의미가 svkit2 에도 있다(그쪽도 base 를 상속). 도메인 코드의
실패 처리 문장은 두 판 사이에서 고칠 것이 없다.
"""
from svkit.base import ApiError, Conflict, Forbidden, NotFound, Unauthorized

__all__ = ["ApiError", "NotFound", "Conflict", "Unauthorized", "Forbidden"]