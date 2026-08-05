"""hello 도메인 — svkit 도메인 모듈의 최소 형태.

규약: 테이블은 `<slug>_` 접두, 응답은 ok()/err(), blueprint 는 /api/<slug> prefix.
실패는 `raise ApiError(msg, status)` — svkit2 판과 같은 문장이다.
"""
from svkit import ApiError, Domain
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
    page = page_args()  # Page(limit, offset) — 튜플이라 언팩도 된다
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM hello_item ORDER BY id LIMIT ? OFFSET ?",
            (page.limit, page.offset)).fetchall()
    return ok([dict(r) for r in rows])


@bp.get("/items/<int:item_id>")
def one(item_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM hello_item WHERE id=?", (item_id,)).fetchone()
    if row is None:
        raise ApiError("항목 없음", 404)
    return ok(dict(row))


#: dict 로 써도 되지만, Domain 으로 쓰면 svkit2 판과 선언 줄이 같아진다
#: (그쪽은 `bp=` 대신 `router=`).
DOMAIN = Domain(slug="hello", title="헬로 예제", bp=bp, schema=SCHEMA, seed=seed)
