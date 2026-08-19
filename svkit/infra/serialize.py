"""직렬화 — ORM 행을 JSON 으로 안전한 평면 dict 로."""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect


def row_to_dict(obj: Any) -> dict[str, Any]:
    """날짜→ISO, Decimal→float."""
    out: dict[str, Any] = {}
    for col in sa_inspect(obj).mapper.column_attrs:
        val = getattr(obj, col.key)
        if isinstance(val, (_dt.datetime, _dt.date)):
            val = val.isoformat()
        elif isinstance(val, Decimal):
            val = float(val)
        out[col.key] = val
    return out


__all__ = ["row_to_dict"]
