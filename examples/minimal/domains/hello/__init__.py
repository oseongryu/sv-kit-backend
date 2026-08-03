"""hello 도메인 — svkit 도메인 모듈의 최소 형태.

규약: 테이블은 `<slug>_` 접두, 응답은 ok()/err(), blueprint 는 /api/<slug> prefix.
"""
from svkit.api import make_blueprint, page_args
from svkit.db import get_conn
from svkit.response import ok

bp = make_blueprint("hello")

SCHEMA = """
CREATE TABLE IF NOT EXISTS hello_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def seed(conn):
    cnt = conn.execute("SELECT COUNT(*) c FROM hello_item").fetchone()["c"]
    if cnt:
        return
    conn.executemany("INSERT INTO hello_item (name) VALUES (?)",
                     [("사과",), ("바나나",), ("체리",)])


@bp.get("/items")
def items():
    limit, offset = page_args()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM hello_item ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
    return ok([dict(r) for r in rows])


DOMAIN = {
    "slug": "hello",
    "title": "헬로 예제",
    "bp": bp,
    "schema": SCHEMA,
    "seed": seed,
}
