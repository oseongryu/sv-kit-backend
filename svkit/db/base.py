"""DB 커넥션·경로. 커넥션 규약은 커널이 갖고, 여기는 DB 경로 결정만."""
import os
import sqlite3
from pathlib import Path

from svkit.loader import conf
from svkit import hooks
from svkit.db.kernel import connect as _connect

# APP_DB_PATH 가 단일 소스 — 여기서 따로 도출하면 빈 DB 를 조용히 새로 만든다.
DB_PATH = Path(os.environ.get("APP_DB_PATH")
               or hooks.app_root() / "db" / "app.db")


def connect() -> sqlite3.Connection:
    """디렉토리 생성은 이 호출 시점에 일어난다 (모듈 로드 시점이 아니다).

    동시성 옵션은 기본이 꺼짐이다 — 워커를 갈라 여러 프로세스가 같은 파일을 무는
    배포만 `config/<edition>.yml` 에서 켠다.
    """
    return _connect(
        DB_PATH,
        foreign_keys=conf.get_bool("APP_SQLITE_FOREIGN_KEYS"),
        busy_timeout_ms=conf.get_int("APP_SQLITE_BUSY_TIMEOUT"),
        journal=conf.get_str("APP_SQLITE_JOURNAL"),
        same_thread=conf.get_bool("APP_SQLITE_SAME_THREAD", True),
        retries=conf.get_int("APP_SQLITE_CONNECT_RETRIES", 1))


def get_db() -> sqlite3.Connection:
    """호출부가 commit/close 하는 raw 커넥션 — `connect()` 와 같다."""
    return connect()


def table_counts(*tables) -> dict:
    """테이블 row 수. 미생성 테이블·DB 부재는 None(예외 대신).

    DB 파일이 없으면 만들지 않는다 — 점검이 부수효과를 내지 않게.
    """
    import os

    if not os.path.exists(DB_PATH):
        return {t: None for t in tables}
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        out = {}
        for t in tables:
            try:
                out[t] = int(cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
            except sqlite3.Error:
                out[t] = None
        return out
    finally:
        con.close()
