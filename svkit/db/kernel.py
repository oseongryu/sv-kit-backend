"""SQLite 공통 커널 — 커넥션·스키마 헬퍼. 의존은 stdlib 뿐이다."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


def _set_journal(conn: sqlite3.Connection, journal: str) -> None:
    """이미 원하는 모드면 건드리지 않는다 — 저널 모드는 DB 파일에 영속되는 속성이고,
    WAL 해제는 다른 연결이 하나도 없어야 성공해서 동시 부팅 중이면 통째로 실패한다."""
    current = (conn.execute("PRAGMA journal_mode").fetchone()[0] or "").upper()
    if current == journal.upper():
        return
    try:
        conn.execute(f"PRAGMA journal_mode={journal}")
    except sqlite3.OperationalError:
        pass


def connect(path, *, foreign_keys: bool = False, busy_timeout_ms: int = 0,
            journal: str = "", same_thread: bool = True,
            retries: int = 1, backoff: float = 0.15) -> sqlite3.Connection:
    """커넥션 규약 한 곳 — row_factory=Row, 부모 디렉토리 보장.

    기본값은 단일 프로세스용이다. 워커를 갈라 여러 프로세스가 같은 파일을 무는
    배포만 busy_timeout·retries 를 켠다 (잠금 경합과 일시적 open 실패가 정상이 된다).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            conn = sqlite3.connect(
                p, timeout=busy_timeout_ms / 1000 if busy_timeout_ms else 5.0,
                check_same_thread=same_thread)
        except sqlite3.OperationalError as e:
            last = e
            time.sleep(backoff * (attempt + 1))
            continue
        conn.row_factory = sqlite3.Row
        if busy_timeout_ms:
            conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        if foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON")
        if journal:
            _set_journal(conn, journal)
        return conn
    raise last


def tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}


def table_sql(conn: sqlite3.Connection, table: str) -> str | None:
    """테이블의 CREATE 문 원문 — rebuild 필요 판정용. 없으면 None."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row else None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """컬럼 이름 집합. 테이블이 없으면 빈 집합."""
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def add_column(conn: sqlite3.Connection, table: str, name: str, decl: str) -> bool:
    """컬럼이 없으면 ALTER 로 더한다 (멱등). 더했으면 True."""
    if name in columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    return True


def rename_tables(conn: sqlite3.Connection, renames: dict[str, str]) -> None:
    """옛 이름 → 새 이름 일괄 (멱등). 새 이름이 이미 있으면 그 항목은 건너뛴다."""
    existing = tables(conn)
    for old, new in renames.items():
        if old in existing and new not in existing:
            conn.execute(f"ALTER TABLE {old} RENAME TO {new}")
            existing.discard(old)
            existing.add(new)
