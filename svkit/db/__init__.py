"""SQLite 커널 — 커넥션 진입점과 엔진 선택만. 스키마·질의는 각 모듈이 갖는다."""
import sqlite3
from contextlib import contextmanager

from svkit.db.base import connect, get_db, table_counts  # noqa: F401


@contextmanager
def get_conn():
    """with 블록용 연결 — 예외 없으면 commit, 있으면 rollback."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# postgres 심볼만 지연 해석 — sqlite 전용 배포에 sqlalchemy 가 딸려오면 안 된다.
from svkit.db.sqlite import SqliteDB  # noqa: E402,F401

_POSTGRES = {"build_database_url", "get_engine", "get_sessionmaker", "get_session",
             "SessionLocal", "session", "rows", "row"}


def __getattr__(name: str):
    """`DB_PATH` 와 postgres 심볼만 지연 해석 — 그 외는 AttributeError 여야 한다
    (서브모듈 import 가 그 폴백으로 돈다).

    **값을 `globals()` 에 캐시하지 않는다** — 캐시하면 첫 접근 값이 굳어
    `APP_DB_PATH` 를 나중에 세운 쪽이 조용히 무시된다.
    """
    if name == "DB_PATH":
        from svkit.db.base import db_path

        return db_path()
    if name in _POSTGRES:
        from svkit.db import postgres

        return getattr(postgres, name)
    raise AttributeError(f"module 'svkit.db' has no attribute {name!r}")