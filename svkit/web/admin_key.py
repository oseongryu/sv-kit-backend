"""관리자 인증 — 헤더 하나를 설정값과 비교한다.

두 벌인 이유는 계보마다 이미 굳은 이름이 다르기 때문이다.
- `X-Admin-Key` ↔ `ADMIN_API_KEY` (insight·automation 계보)
- `X-Admin-Token` ↔ `ADMIN_TOKEN` (rn 계보)

공통 계약: 설정값이 비어 있으면 통과(개발·대시보드), 설정돼 있으면 일치해야 한다.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, Header, HTTPException
from svkit.loader import conf

ADMIN_API_KEY_ENV = "ADMIN_API_KEY"
ADMIN_API_KEY_HEADER = "X-Admin-Key"


def _expected_key() -> str:
    """설정된 관리자 API 키(없으면 빈 문자열)."""
    return conf.get_str(ADMIN_API_KEY_ENV).strip()


def require_admin_key(
    x_admin_key: Optional[str] = Header(default=None, alias=ADMIN_API_KEY_HEADER),
    authorization: Optional[str] = Header(default=None),
) -> None:
    expected = _expected_key()
    if not expected:
        # ADMIN_API_KEY 미설정 → 개방(하위호환) — 운영에서 키 설정 시 자동 강제
        return

    presented = (x_admin_key or "").strip()
    if not presented and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            presented = token.strip()

    if presented == expected or _is_admin_jwt(presented):
        return

    raise HTTPException(
        status_code=401,
        detail="관리자 인증 실패: 유효한 토큰이 필요합니다.",
    )


ADMIN_TOKEN_ENV = "ADMIN_TOKEN"
ADMIN_TOKEN_HEADER = "X-Admin-Token"


def admin_token_configured() -> bool:
    return bool(conf.get_str(ADMIN_TOKEN_ENV).strip())


def _is_admin_jwt(token: str) -> bool:
    """로그인이 발급한 관리자 토큰인가. JWT_SECRET 이 없으면 판정 자체를 안 한다."""
    if not token or not conf.get_str("JWT_SECRET").strip():
        return False
    from svkit.web.security import verify_token

    payload = verify_token(token)
    return bool(payload) and payload.get("role") == "admin"


def check_admin_token(token: Optional[str]) -> None:
    """토큰 검사 — 헤더를 직접 받는 라우트·WebSocket 용.

    받는 것은 둘이다 — 로그인이 발급한 관리자 JWT, 그리고 설정 고정값(기계 채널).
    **인증이 켜진 배포에서는 "설정이 없으면 통과" 가 적용되지 않는다** — 앱 토큰
    (role=app)이 게이트를 지나 여기까지 오므로, 열어 두면 앱이 관리 API 를 부를 수 있다.
    """
    presented = (token or "").strip()
    if _is_admin_jwt(presented):
        return
    required = conf.get_str(ADMIN_TOKEN_ENV).strip()
    if required and presented == required:
        return
    if required or conf.get_bool("AUTH_ENABLED"):
        raise HTTPException(status_code=403, detail="관리 권한 필요")


def require_admin_token(
    x_admin_token: Optional[str] = Header(default=None, alias=ADMIN_TOKEN_HEADER),
    authorization: Optional[str] = Header(default=None),
) -> None:
    presented = (x_admin_token or "").strip()
    if not presented and authorization:
        scheme, _, tok = authorization.partition(" ")
        if scheme.lower() == "bearer":
            presented = tok.strip()
    check_admin_token(presented)


# 라우트 선언에 그대로 얹는 의존성 목록
admin_token_only = [Depends(require_admin_token)]


__all__ = ["require_admin_key", "ADMIN_API_KEY_ENV", "ADMIN_API_KEY_HEADER",
           "require_admin_token", "check_admin_token", "admin_token_configured",
           "admin_token_only", "ADMIN_TOKEN_ENV", "ADMIN_TOKEN_HEADER"]
