"""ETL 공통 포맷 — 모든 도메인 `etl/` 계층이 공유하는 수집·배치 유틸.

도메인마다 collector 를 새로 발명하지 말고 이 포맷을 사용한다.

- RateLimiter:     초당 요청 수 제한(간단 스로틀, 프로세스 내)
- throttle:        도메인별 전역 요청 간격(SQLite 공유 — 다중 프로세스/레인 안전)
- http_get_json:   표준 라이브러리 기반 JSON GET (별칭 `get_json`)
- fetch_with_retry: 레이트리밋 + 지수 백오프 재시도 (별칭 `fetch_retry`)
- run_job:         `<slug>_job_run` 에 시작/종료 이력을 남기며 배치 함수를 실행

`get_json`/`fetch_retry` 는 svkit2 의 이름이다. 두 판에서 같은 이름으로 부를 수
있게 별칭을 두되, 이 판은 동기이고 그쪽은 async 라는 차이는 그대로 남는다.
"""
import json
import os
import random
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from svkit.db import get_conn

# 프로세스 간 레이트리밋 공유 상태(throttle 용)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS etl_rate_limit (
    domain TEXT PRIMARY KEY,
    next_at REAL DEFAULT 0
);
'''

_RATE_MIN = float(os.environ.get('RATE_MIN_INTERVAL', '3'))
_RATE_MAX = float(os.environ.get('RATE_MAX_INTERVAL', '6'))

#: svkit2 와 이름을 맞춘 별칭
RATE_MIN = _RATE_MIN
RATE_MAX = _RATE_MAX


class RateLimiter:
    """초당 요청 수 제한 (간단 스로틀)."""

    def __init__(self, rate_per_sec: float):
        self.min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._last = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


def throttle(url):
    """도메인별 전역 요청 간격 확보(SQLite 공유 상태로 워커/레인 간 동기화).

    RATE_MIN_INTERVAL~RATE_MAX_INTERVAL 초 사이 랜덤 간격을 도메인 단위로
    직렬화한다. 필요한 만큼 대기 후 반환.
    """
    try:
        domain = urlparse(url).netloc or 'default'
    except Exception:
        domain = 'default'
    interval = random.uniform(_RATE_MIN, _RATE_MAX)
    wait = interval
    from svkit.db import connect
    conn = connect()
    conn.isolation_level = None
    try:
        conn.execute('BEGIN IMMEDIATE')
        now = time.time()
        row = conn.execute('SELECT next_at FROM etl_rate_limit WHERE domain=?', (domain,)).fetchone()
        next_at = row['next_at'] if row else 0.0
        start = now if next_at < now else next_at
        conn.execute(
            'INSERT INTO etl_rate_limit (domain, next_at) VALUES (?, ?) '
            'ON CONFLICT(domain) DO UPDATE SET next_at=excluded.next_at',
            (domain, start + interval))
        conn.execute('COMMIT')
        wait = start - now
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except Exception:
            pass
        wait = interval  # 폴백: 로컬 간격
    finally:
        conn.close()
    if wait > 0:
        time.sleep(wait)


def http_get_json(url: str, timeout: float | None = None) -> dict:
    """URL에서 JSON을 가져온다 (표준 라이브러리 사용). timeout 미지정 시 config 값."""
    from svkit import config
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_with_retry(url: str, timeout: float | None = None, max_retries: int = 3,
                     backoff_base_sec: float = 0.5,
                     limiter: "RateLimiter | None" = None) -> dict:
    """레이트리밋 + 지수 백오프 재시도로 소스에서 JSON 수집."""
    last_err = None
    for attempt in range(max_retries + 1):
        if limiter is not None:
            limiter.wait()
        try:
            return http_get_json(url, timeout)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(backoff_base_sec * (2 ** attempt))
            continue
    raise RuntimeError(f"수집 실패({url}): {last_err}")


#: svkit2 와 이름을 맞춘 별칭
get_json = http_get_json
fetch_retry = fetch_with_retry


def run_job(slug: str, job_type: str, fn) -> int:
    """`<slug>_job_run` 에 실행 이력을 남기며 배치 함수 fn 을 실행.

    fn() 은 처리한 행 수(int)를 반환한다. 예외가 나면 실패로 기록 후 재발생.
    반환: run_id
    스키마에 `<slug>_job_run` 테이블(아래 컬럼)이 있어야 한다:
      run_id, job_type, status, rows_processed, error_msg, started_at, finished_at
    """
    table = f"{slug}_job_run"  # slug 은 내부 규약값(사용자 입력 아님)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO {table} (job_type, status) VALUES (?, 'running')",
            (job_type,),
        )
        run_id = cur.lastrowid
    try:
        rows = fn() or 0
        with get_conn() as conn:
            conn.execute(
                f"""UPDATE {table} SET status='success', rows_processed=?,
                    finished_at=datetime('now') WHERE run_id=?""",
                (rows, run_id),
            )
        return run_id
    except Exception as e:
        with get_conn() as conn:
            conn.execute(
                f"""UPDATE {table} SET status='failed', error_msg=?,
                    finished_at=datetime('now') WHERE run_id=?""",
                (str(e), run_id),
            )
        raise
