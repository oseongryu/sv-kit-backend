"""공통 대칭 암호화 유틸(Fernet) — APP_SECRET_KEY 미설정/불일치 시 fail-closed."""
from __future__ import annotations

import json
from typing import Any
from svkit.loader import conf


class CryptoUnavailable(RuntimeError):
    """APP_SECRET_KEY 미설정/무효 등으로 암복호화를 수행할 수 없을 때."""


class SecretUndecryptable(CryptoUnavailable):
    """키는 있으나 그 키로 이 암호문을 풀 수 없을 때(키 교체·환경 간 이동)."""


def _fernet():
    # 호출 시점에 키를 읽어 런타임 주입(.env/시크릿) 반영
    key = conf.get_str("APP_SECRET_KEY").strip()
    if not key:
        raise CryptoUnavailable(
            "APP_SECRET_KEY 미설정 — 인증정보 암호화 저장 불가. "
            "생성: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        from cryptography.fernet import Fernet  # 지연 임포트(선택 의존)
    except ImportError as exc:  # pragma: no cover - 배포 requirements 에 포함
        raise CryptoUnavailable(f"cryptography 미설치: {exc}") from exc
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise CryptoUnavailable(f"APP_SECRET_KEY 형식 오류(Fernet base64 32B 필요): {exc}") from exc


def is_crypto_ready() -> bool:
    """암호화 저장 가능 여부(키 설정 + 라이브러리 로드)를 반환한다(부작용 없음)."""
    try:
        _fernet()
        return True
    except CryptoUnavailable:
        return False


def encrypt_secrets(secrets: dict[str, Any]) -> str:
    token = _fernet().encrypt(json.dumps(secrets, ensure_ascii=False).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secrets(token: str) -> dict[str, Any]:
    if not token:
        return {}
    from cryptography.fernet import InvalidToken  # 라이브러리 부재는 _fernet() 이 먼저 거른다

    fernet = _fernet()
    try:
        raw = fernet.decrypt(str(token).encode("utf-8"))
    except InvalidToken as exc:
        raise SecretUndecryptable(
            "저장된 암호문을 현재 APP_SECRET_KEY 로 복호화할 수 없습니다 — "
            "암호화 당시와 다른 키입니다."
        ) from exc
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def mask_secrets(secrets: dict[str, Any]) -> dict[str, str]:
    """화면 표시용으로 값을 마스킹한다(뒤 4자리만 노출, 그 외 •)."""
    out: dict[str, str] = {}
    for k, v in (secrets or {}).items():
        s = str(v)
        out[k] = ("•" * max(0, len(s) - 4) + s[-4:]) if len(s) > 4 else "••••"
    return out


__all__ = [
    "CryptoUnavailable",
    "SecretUndecryptable",
    "is_crypto_ready",
    "encrypt_secrets",
    "decrypt_secrets",
    "mask_secrets",
]
