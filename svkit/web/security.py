"""비밀번호 해시·자체 JWT — stdlib 만 쓰는 프레임워크 중립 층.

**형식이 동결돼 있다** — 해시는 `pbkdf2$<salt hex>$<dk hex>`(sha256, 200k), 토큰은
HS256 JWT. 기존 DB 에 저장된 해시와 발급된 토큰이 그대로 검증돼야 하므로 파라미터를
바꾸지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from svkit.loader import conf

PBKDF_ITER = 200_000


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF_ITER)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), PBKDF_ITER)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:  # noqa: BLE001 — 형식이 깨진 해시는 불일치로 본다
        return False


def _secret() -> bytes:
    return conf.require("JWT_SECRET").encode()


def create_token(username: str, role: str) -> str:
    ttl = conf.get_int("JWT_TTL")
    header = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64e(json.dumps(
        {"sub": username, "role": role, "exp": int(time.time()) + ttl}).encode())
    seg = f"{header}.{payload}"
    return f"{seg}.{_b64e(hmac.new(_secret(), seg.encode(), hashlib.sha256).digest())}"


def verify_token(token: str) -> dict | None:
    """유효하면 payload, 아니면 None."""
    try:
        seg, sig = token.rsplit(".", 1)
        expected = _b64e(hmac.new(_secret(), seg.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(seg.split(".")[1]))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except Exception:  # noqa: BLE001 — 파싱 실패는 곧 무효 토큰
        return None


__all__ = ["PBKDF_ITER", "hash_password", "verify_password",
           "create_token", "verify_token"]
