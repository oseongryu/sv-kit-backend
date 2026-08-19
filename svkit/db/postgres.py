"""공통 DB 접근 계층 (SQLAlchemy 2.0) — 전 서비스 공유 엔진/세션 팩토리."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from svkit.loader import conf


# SessionLocal 은 unbound sessionmaker — get_engine() 최초 호출 시 엔진에 바인딩
_engine: Engine | None = None
SessionLocal: sessionmaker[Session] = sessionmaker(
    expire_on_commit=False, future=True
)


def build_database_url() -> str:
    host = conf.get_str("POSTGRES_HOST")
    port = conf.get_str("POSTGRES_PORT")
    user = conf.get_str("POSTGRES_USER")
    password = conf.get_str("POSTGRES_PASSWORD")
    db = conf.get_str("POSTGRES_DB")
    return (
        f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{db}"
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            build_database_url(),
            pool_pre_ping=True,
            pool_size=conf.get_int("DB_POOL_SIZE"),
            max_overflow=conf.get_int("DB_MAX_OVERFLOW"),
            future=True,
        )
        SessionLocal.configure(bind=_engine)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    get_engine()
    return SessionLocal


@contextmanager
def get_session() -> Iterator[Session]:
    """트랜잭션 세션 컨텍스트매니저 — commit/rollback/close."""
    factory = get_sessionmaker()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


session = get_session  # 도메인 호출부 계약(session/rows/row)


def rows(sql: str, params: Optional[dict] = None) -> list[dict[str, Any]]:
    with session() as s:
        return [dict(r) for r in s.execute(text(sql), params or {}).mappings().all()]


def row(sql: str, params: Optional[dict] = None) -> Optional[dict[str, Any]]:
    """SELECT 첫 행을 dict 로(없으면 None)."""
    with session() as s:
        r = s.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None


__all__ = [
    "build_database_url",
    "get_engine",
    "get_sessionmaker",
    "get_session",
    "SessionLocal",
    "session",
    "rows",
    "row",
]
