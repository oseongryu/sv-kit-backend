"""환경변수 해석 — 불리언 플래그 판정의 단일 지점."""
from __future__ import annotations

import os
from svkit.loader import conf

_TRUE = ("1", "true", "t", "y", "yes", "on")
_FALSE = ("0", "false", "f", "n", "no", "off")


def flag(name: str, default: bool = True) -> bool:
    """불리언 환경변수. 값이 없거나 알 수 없으면 default."""
    raw = conf.get_str(name).strip().lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return default


def env_first(*names: str, default: str = "") -> str:
    """준 이름 순서대로 보고 처음으로 값이 있는 것. 다 비면 default.

    이름이 신·구로 갈린 설정의 폴백 규칙을 여기 하나에 둔다 — 이미 배포된 .env·이미지가
    구 이름을 갖고 있어 새 이름만 볼 수 없다.
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


__all__ = ["flag", "env_first"]
