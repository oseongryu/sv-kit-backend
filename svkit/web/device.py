"""디바이스 토큰 — 앱이 최초 실행 때 받아 두고 계속 쓰는 장수명 토큰.

발급 때 만든 지문(device_id+클라이언트 식별자)을 토큰 클레임에 묶고 요청마다 대조한다.
**IP 는 지문에 넣지 않는다** — 모바일은 셀↔WiFi 전환·캐리어 NAT 로 수시로 바뀌어
정상 사용자가 튕긴다.

클라이언트 식별자는 `X-App-Client` 를 먼저 보고 없으면 `User-Agent` 로 떨어진다.
UA 는 OS·웹뷰가 좌우해 앱이 통제할 수 없다 — OS 업데이트 한 번에 전 사용자가 지문
불일치로 걸리므로, 앱은 자기가 완전히 통제하는 고정 헤더를 보낸다.

**어긋나도 즉시 막지 않는다.** 첫 요청에서 끊으면 무엇이 걸렸는지가 바로 드러나 UA 만
바꿔 가며 지문을 맞출 수 있다. 그래서 기기마다 다른 유예 횟수만큼 통과시키고, 그 뒤
확률을 올려 가며 막다가 램프를 다 지나면 확정 차단한다. 판정은 `device_id`+횟수 해시라
서버는 그대로 재현할 수 있고 밖에서는 무작위로 보인다.

**흐리는 것은 응답뿐이고 로그는 첫 순간부터 정확하다** — 정상 사용자가 UA 가 바뀌어
걸린 것(오탐)과 실제 도용을 운영자가 구분할 수 있어야 한다.

계약:
  issue(device_id, client, secret) -> (토큰, device_id). 시크릿 불일치·차단 기기는 ApiError.
  check(payload, client) -> 통과면 None, 막을 사유가 있으면 그 문자열(**로그용**이다 —
                        응답 문구로 쓰면 무엇이 걸렸는지 알려 주게 된다).
"""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from svkit.infra.logger import get_logger
from svkit.loader import conf
from svkit.web.errors import ApiError
from svkit.web.security import create_token

log = get_logger(__name__)

ROLE_APP = "app"

# 앱이 자기가 통제하는 고정값을 선언하는 자리. 없으면 UA 로 떨어진다.
CLIENT_HEADER = "X-App-Client"


def client_id(app_client: str, user_agent: str) -> str:
    """지문에 쓸 클라이언트 식별자 — 선언한 값이 있으면 그것이 이긴다."""
    return (app_client or "").strip() or (user_agent or "")

DEVICE_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_device (
    device_id  TEXT PRIMARY KEY,
    fp         TEXT NOT NULL,
    ua         TEXT NOT NULL DEFAULT '',
    issued_at  TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT,
    revoked_reason TEXT,
    suspect_hits INTEGER NOT NULL DEFAULT 0,
    suspect_at TEXT,
    suspect_ua TEXT
);
"""

_CACHE_TTL = 30.0
_revoked: set[str] = set()
_loaded_at = 0.0


def ensure_schema() -> None:
    from svkit import db
    from svkit.db.kernel import add_column

    with db.get_conn() as conn:
        conn.executescript(DEVICE_SCHEMA)
        add_column(conn, "auth_device", "suspect_hits", "INTEGER NOT NULL DEFAULT 0")
        add_column(conn, "auth_device", "suspect_at", "TEXT")
        add_column(conn, "auth_device", "suspect_ua", "TEXT")


def fingerprint(device_id: str, client: str) -> str:
    return hashlib.sha256(f"{device_id}\n{client}".encode()).hexdigest()


def _ttl() -> int:
    return conf.get_int("APP_TOKEN_TTL") or 31_536_000


def issue(device_id: str, client: str, secret: str) -> tuple[str, str]:
    expected = conf.get_str("APP_DEVICE_SECRET").strip()
    if not expected:
        raise ApiError(
            "APP_DEVICE_SECRET 미설정 — 서버 설정(config/local.yml)을 채우고 재기동하라", 503)
    if not hmac.compare_digest((secret or "").strip(), expected):
        raise ApiError("발급 거부", 401)

    device_id = (device_id or "").strip() or uuid.uuid4().hex
    fp = fingerprint(device_id, client)

    from svkit import db

    with db.get_conn() as conn:
        conn.executescript(DEVICE_SCHEMA)
        row = conn.execute("SELECT revoked_at FROM auth_device WHERE device_id=?",
                           (device_id,)).fetchone()
        if row and row["revoked_at"]:
            raise ApiError("차단된 기기", 403)
        conn.execute(
            "INSERT INTO auth_device (device_id, fp, ua) VALUES (?,?,?) "
            "ON CONFLICT(device_id) DO UPDATE SET fp=excluded.fp, ua=excluded.ua, "
            "issued_at=datetime('now')",
            (device_id, fp, client))
    return create_token(device_id, ROLE_APP, ttl=_ttl(), extra={"fp": fp}), device_id


def revoke(device_id: str, reason: str) -> None:
    from svkit import db

    with db.get_conn() as conn:
        conn.executescript(DEVICE_SCHEMA)
        conn.execute(
            "UPDATE auth_device SET revoked_at=datetime('now'), revoked_reason=? "
            "WHERE device_id=?", (reason, device_id))
    _revoked.add(device_id)


def _is_revoked(device_id: str) -> bool:
    """차단 목록은 프로세스 안에 캐시한다 — 앱 트래픽 전량이 매 요청 DB 를 치면 안 된다."""
    global _loaded_at

    now = time.monotonic()
    if now - _loaded_at > _CACHE_TTL:
        from svkit import db

        with db.get_conn() as conn:
            conn.executescript(DEVICE_SCHEMA)
            rows = conn.execute(
                "SELECT device_id FROM auth_device WHERE revoked_at IS NOT NULL").fetchall()
        _revoked.clear()
        _revoked.update(r["device_id"] for r in rows)
        _loaded_at = now
    return device_id in _revoked


def _grace_of(device_id: str) -> int:
    """이 기기가 몇 번까지 그냥 통과하는가. **기기마다 다르다** — 고정이면 몇 번째부터
    막히는지가 드러나 그 앞까지만 쓰는 방법이 생긴다."""
    lo = conf.get_int("APP_TOKEN_GRACE_MIN") or 2
    hi = conf.get_int("APP_TOKEN_GRACE_MAX") or 9
    if hi <= lo:
        return lo
    h = int(hashlib.sha256(f"grace:{device_id}".encode()).hexdigest()[:8], 16)
    return lo + h % (hi - lo + 1)


def _blocks(device_id: str, hits: int) -> bool:
    """유예를 넘으면 확률이 올라가고 램프를 다 지나면 확정 차단."""
    grace = _grace_of(device_id)
    if hits <= grace:
        return False
    ramp = conf.get_int("APP_TOKEN_DECAY_HITS") or 12
    over = hits - grace
    if over >= ramp:
        return True
    h = int(hashlib.sha256(f"block:{device_id}:{hits}".encode()).hexdigest()[:8], 16)
    return h % 100 < over * 100 // ramp


def suspect_delay_sec() -> float:
    """막을 때 끄는 시간. 응답이 늘 즉시면 그 자체가 신호가 된다. 기본 0(꺼짐)."""
    return (conf.get_int("APP_TOKEN_SUSPECT_DELAY_MS") or 0) / 1000.0


def _record_suspect(device_id: str, client: str) -> int:
    """지문 불일치 횟수를 올리고 그 값을 돌려준다."""
    from svkit import db

    with db.get_conn() as conn:
        conn.executescript(DEVICE_SCHEMA)
        conn.execute(
            "UPDATE auth_device SET suspect_hits = suspect_hits + 1, "
            "suspect_at = datetime('now'), suspect_ua = ? WHERE device_id = ?",
            (client, device_id))
        row = conn.execute("SELECT suspect_hits FROM auth_device WHERE device_id=?",
                           (device_id,)).fetchone()
    return int(row["suspect_hits"]) if row else 1


def check(payload: dict, client: str) -> str | None:
    device_id = str(payload.get("sub") or "")
    claimed = str(payload.get("fp") or "")
    if not device_id or not claimed:
        return "지문 없는 앱 토큰"
    if _is_revoked(device_id):
        return "차단된 기기"
    if hmac.compare_digest(claimed, fingerprint(device_id, client)):
        return None

    hits = _record_suspect(device_id, client)
    if not _blocks(device_id, hits):
        # 통과시키되 로그는 남긴다 — 오탐(정상 사용자의 UA 변경)도 여기서 드러난다.
        log.warning("지문 불일치 통과 device=%s hits=%d client=%s", device_id, hits, client)
        return None

    if hits - _grace_of(device_id) >= (conf.get_int("APP_TOKEN_DECAY_HITS") or 12):
        revoke(device_id, f"지문 불일치 {hits}회")
        log.warning("기기 차단 device=%s hits=%d", device_id, hits)
    else:
        log.warning("지문 불일치 차단 device=%s hits=%d client=%s", device_id, hits, client)
    return "지문 불일치"


__all__ = ["ROLE_APP", "CLIENT_HEADER", "DEVICE_SCHEMA", "ensure_schema",
           "client_id", "fingerprint", "issue", "revoke", "check", "suspect_delay_sec"]
