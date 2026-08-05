"""공유 SQLite 연결 + 스키마 초기화.

모든 도메인이 하나의 SQLite 파일(app.db)을 공유한다.
각 도메인은 자기 테이블을 `<slug>_` 접두로 네임스페이스 분리하여 충돌을 피한다.

조회 헬퍼(`fetch_all`·`fetch_one`·`scalar`·`insert_id`·`exists`)와 연결 이름
(`conn`·`read`)은 **svkit2 와 이름·인자 순서를 맞춰 뒀다.** SQL 을 넘기는지
SQLAlchemy 표현식을 넘기는지는 판마다 다르지만(그건 각자의 전제다), 호출
줄의 모양이 같아 합칠 때 바뀌는 것이 문장 안쪽으로 좁아진다.
"""
import os
import sqlite3
import time
from contextlib import contextmanager

from . import config

_INITIALIZED = False

# 권장: DB 파일은 named volume(리눅스 ext4)에 둘 것. Docker Desktop(Windows/mac)의
# 바인드마운트 파일시스템은 WAL 공유메모리(-shm)/락을 완전히 지원하지 않아
# 동시 접속 폭주 시 'unable to open database file'(SQLITE_CANTOPEN)이 간헐 발생한다.
# 아래 connect() 재시도는 그 잔여 실패에 대한 방어이며, 근본 해결은 볼륨 배치다.
_CONNECT_RETRIES = 5
_CONNECT_BACKOFF = 0.15


def _ensure_dir() -> None:
    d = os.path.dirname(config.DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)


def connect() -> sqlite3.Connection:
    """새 연결을 연다 (WAL, row factory, FK on). 일시적 open 실패는 재시도."""
    _ensure_dir()
    last = None
    for attempt in range(_CONNECT_RETRIES):
        try:
            conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            return conn
        except sqlite3.OperationalError as e:
            last = e
            time.sleep(_CONNECT_BACKOFF * (attempt + 1))
    raise last


@contextmanager
def get_conn():
    """with 블록용 연결. 예외 없으면 commit, 있으면 rollback."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


#: svkit2 와 이름을 맞춘 별칭. 그쪽은 쓰기(`conn`)와 읽기(`read`)를 나누지만
#: SQLite 단일 파일에서는 같은 연결이라 둘 다 get_conn 이다.
conn = get_conn
read = get_conn


# ── 조회 헬퍼 (svkit2 와 같은 이름·인자 순서) ──

def fetch_all(c, sql: str, params=()) -> list:
    """행을 dict 목록으로."""
    return [dict(r) for r in c.execute(sql, params).fetchall()]


def fetch_one(c, sql: str, params=()) -> dict | None:
    row = c.execute(sql, params).fetchone()
    return dict(row) if row is not None else None


def scalar(c, sql: str, params=(), default=None):
    """단일 값 조회(COUNT 등). 행이 없거나 NULL 이면 default."""
    row = c.execute(sql, params).fetchone()
    if row is None or row[0] is None:
        return default
    return row[0]


def insert_id(c, table: str, values: dict):
    """INSERT 후 새 PK. table 은 내부 규약값(사용자 입력 아님)."""
    cols = ", ".join(values)
    marks = ", ".join("?" * len(values))
    cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
    return cur.lastrowid


def exists(c, table: str, where: str, params=()) -> bool:
    return c.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", params).fetchone() is not None


def executescript(sql: str) -> None:
    """스키마 SQL 을 실행(멱등 CREATE TABLE IF NOT EXISTS 전제)."""
    with get_conn() as conn:
        conn.executescript(sql)


def init_all() -> None:
    """공통/도메인 스키마 초기화 + 도메인 마이그레이션 훅 실행.

    순서: ① 도메인 migrate 훅(테이블 rename 등 — 스키마 생성 전에 실행해야
    IF NOT EXISTS 가 빈 테이블을 먼저 만들지 않는다) ② 도메인 schema
    ③ 공통 인프라 스키마(auth/queue/etl).
    """
    global _INITIALIZED
    from svkit import registry  # 지연 import (순환 방지)
    DOMAINS = registry.DOMAINS

    _ensure_dir()
    for dom in DOMAINS:
        mig = dom.get("migrate")
        if callable(mig):
            with get_conn() as conn:
                mig(conn)
    for dom in DOMAINS:
        schema = dom.get("schema")
        if schema:
            executescript(schema)
    from svkit import auth as _auth
    from svkit import etl as _etl, queue as _queue, scheduler as _scheduler
    for schema in (_auth.SCHEMA, _queue.SCHEMA, _etl.SCHEMA, _scheduler.SCHEMA):
        executescript(schema)
    _scheduler.init_defaults()
    _INITIALIZED = True


def backup() -> str:
    """DB 스냅샷 백업(최근 10개 유지). 반환: 백업 파일 경로"""
    import glob
    from datetime import datetime

    base = os.path.basename(config.DB_PATH).rsplit(".", 1)[0]
    bak_dir = config.BACKUP_DIR
    os.makedirs(bak_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_path = os.path.join(bak_dir, f"{base}_{ts}.db")
    src = connect()
    dst = sqlite3.connect(bak_path)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    files = sorted(glob.glob(os.path.join(bak_dir, f"{base}_*.db")))
    for old in files[:-10]:
        try:
            os.remove(old)
        except OSError:
            pass
    return bak_path


def backend() -> str:
    """활성 백엔드 이름. 이 판은 SQLite 고정(전제)."""
    return "sqlite"


def supports_skip_locked() -> bool:
    """행 잠금 건너뛰기 지원 여부. SQLite 는 없다 — 쓰기 직렬화로 대신한다."""
    return False


__all__ = [
    "connect", "get_conn", "conn", "read", "executescript", "init_all", "backup",
    "fetch_all", "fetch_one", "scalar", "insert_id", "exists",
    "backend", "supports_skip_locked",
]
