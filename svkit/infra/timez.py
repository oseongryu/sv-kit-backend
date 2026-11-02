"""타임존 — 화면 표기·기간 필터·스케줄러가 공유하는 기준.

이름은 앱이 정한다(`hooks.register(timezone=…)`), 없으면 env `SVKIT_TZ`, 그것도 없으면 UTC.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Optional
from zoneinfo import ZoneInfo
from svkit import hooks


def tz_name() -> str:
    return hooks.timezone()


def tz() -> ZoneInfo:
    return ZoneInfo(tz_name())


def today() -> _dt.date:
    """설정 타임존(기본 KST) 기준 오늘 — 쿼터·일자 집계가 같은 날을 봐야 한다."""
    return _dt.datetime.now(tz()).date()


def kst_iso(value: Any) -> Any:
    """aware datetime 을 운영 타임존 ISO 문자열로(그 외 값은 그대로)."""
    if not isinstance(value, _dt.datetime):
        return value
    if value.tzinfo is not None:
        value = value.astimezone(tz())
    return value.isoformat()


def day_bounds(date_str: str, *, end: bool) -> Optional[_dt.datetime]:
    """'YYYY-MM-DD' → 그 날의 하한(00:00) 또는 상한(23:59:59.999)."""
    try:
        d = _dt.date.fromisoformat(str(date_str)[:10])
    except (ValueError, TypeError):
        return None
    if end:
        return _dt.datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=tz())
    return _dt.datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz())


__all__ = ["tz_name", "tz", "today", "kst_iso", "day_bounds"]
