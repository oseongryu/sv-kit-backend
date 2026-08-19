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

    if not presented or presented != expected:
        raise HTTPException(
            status_code=401,
            detail="관리자 인증 실패: 유효한 X-Admin-Key 헤더가 필요합니다.",
        )


ADMIN_TOKEN_ENV = "ADMIN_TOKEN"
ADMIN_TOKEN_HEADER = "X-Admin-Token"


def admin_token_configured() -> bool:
    return bool(conf.get_str(ADMIN_TOKEN_ENV).strip())


def check_admin_token(token: Optional[str]) -> None:
    """토큰 검사 — 헤더를 직접 받는 라우트·WebSocket 용."""
    required = conf.get_str(ADMIN_TOKEN_ENV).strip()
    if required and (token or "").strip() != required:
        raise HTTPException(status_code=403, detail="관리 토큰 불일치")


def require_admin_token(
    x_admin_token: Optional[str] = Header(default=None, alias=ADMIN_TOKEN_HEADER),
) -> None:
    check_admin_token(x_admin_token)


# 라우트 선언에 그대로 얹는 의존성 목록
admin_token_only = [Depends(require_admin_token)]


__all__ = ["require_admin_key", "ADMIN_API_KEY_ENV", "ADMIN_API_KEY_HEADER",
           "require_admin_token", "check_admin_token", "admin_token_configured",
           "admin_token_only", "ADMIN_TOKEN_ENV", "ADMIN_TOKEN_HEADER"]
