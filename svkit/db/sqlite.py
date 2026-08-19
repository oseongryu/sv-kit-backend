"""경량 SQLite 엔진 — 독립 배포단위·사이드카 파일 저장용 (stdlib 전용)."""
from __future__ import annotations

import os
import sqlite3


class SqliteDB:
    """SQLite 파일 하나 = 인스턴스 하나. 테이블명은 프리픽스로 구획한다."""

    def __init__(self, path: str, *, prefix: str = "", busy_timeout_ms: int = 5000):
        self.path = path
        self.prefix = prefix
        self.busy_timeout_ms = busy_timeout_ms

    def table(self, name: str) -> str:
        return self.prefix + name

    def connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000)
        # busy_timeout — 다중 컨테이너 잠금 대기
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        return conn
