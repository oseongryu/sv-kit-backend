"""작업 큐 공통 포맷 — SQLite 기반 백그라운드 작업(레인·재시도·하트비트·리퍼).

Redis/Celery 없이 queue_job 테이블 하나로 다중 프로세스 안전 큐를 재현한다.
도메인은 핸들러를 등록(register)하고 enqueue 로 작업을 넣는다. 실행은
인프로세스 워커(config.RUN_WORKER, 개발/단일 컨테이너) 또는 전용 워커
프로세스(worker.py)가 담당한다.

  from svkit import queue
  queue.register('<slug>.collect', fn, lane='crawl')   # fn(state, params)
  queue.enqueue('<slug>.collect', {'x': 1}, label='전체')

핸들러 규약: fn(state, params). state dict 로 진행을 보고한다:
  state['progress']=str, state['current']/state['total']=int
  state['should_stop'] 이 True 면 즉시 중단(협조적 취소), state['error']=bool

레인: env QUEUE_LANES(쉼표 구분, 기본 'default'). 레인별 워커 스레드가 동시
소비하고 레인 내부는 직렬. 핸들러 등록 시 lane 을 지정한다.

운영 API(/api/queue): jobs / status / metrics / stream(SSE) / stop / retry.
신뢰성: 재시도(JOB_MAX_ATTEMPTS), 하트비트(JOB_HEARTBEAT_TIMEOUT) 기반
고아 작업 리퍼, 백오프(JOB_RETRY_BACKOFF). 실패 확정 시 alerts.notify.
"""
import json
import os
import threading
import time
import traceback
from datetime import datetime, timedelta

from flask import request

from svkit.api import make_blueprint
from svkit.sse import stream_response
from svkit import alerts, logger
from svkit.auth import require_admin, require_auth
from svkit.db import get_conn
from svkit.response import err, ok

SCHEMA = '''
CREATE TABLE IF NOT EXISTS queue_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    params TEXT DEFAULT '',
    label TEXT DEFAULT '',
    queue TEXT DEFAULT 'default',
    status TEXT DEFAULT 'queued',
    progress TEXT DEFAULT '',
    current INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    error INTEGER DEFAULT 0,
    stop_requested INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 1,
    heartbeat_at REAL DEFAULT 0,
    run_at REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_queue_job_status ON queue_job(status, queue);
'''

LANES = [ln.strip() for ln in os.environ.get('QUEUE_LANES', 'default').split(',') if ln.strip()]

MAX_ATTEMPTS = int(os.environ.get('JOB_MAX_ATTEMPTS', '3'))
HEARTBEAT_TIMEOUT = float(os.environ.get('JOB_HEARTBEAT_TIMEOUT', '60'))
RETRY_BACKOFF = float(os.environ.get('JOB_RETRY_BACKOFF', '30'))
REAPER_INTERVAL = float(os.environ.get('JOB_REAPER_INTERVAL', '30'))
BACKUP_AFTER_JOB = os.environ.get('QUEUE_BACKUP_AFTER_JOB', 'false').lower() == 'true'

# kind -> (fn, lane). 도메인 etl 이 import 시점에 등록한다
_HANDLERS = {}

# 실행 중 작업의 라이브 상태(job_id -> state dict). 같은 프로세스 내 즉시 중지용
_running = {}
_worker_started = False
_lock = threading.Lock()


def register(kind, fn, lane=None):
    """작업 핸들러 등록. fn(state, params). lane 미지정 시 첫 레인"""
    _HANDLERS[kind] = (fn, lane or LANES[0])


def lane_for(kind):
    h = _HANDLERS.get(kind)
    return h[1] if h else LANES[0]


def handler_for(kind):
    """등록된 핸들러 함수 반환(없으면 None). 배치(svkit.batch)가 인라인 실행에 사용"""
    h = _HANDLERS.get(kind)
    return h[0] if h else None


def registered_kinds():
    return sorted(_HANDLERS.keys())


def has_active(kind):
    """같은 kind 의 대기/실행중 작업 존재 여부(스케줄러 중복 방지용)"""
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM queue_job WHERE kind=? AND status IN ('queued','running') LIMIT 1",
            (kind,)).fetchone() is not None


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ── 진행 보고 헬퍼(핸들러에서 사용) ──

def update_progress(state, msg):
    if state is not None:
        state['progress'] = msg


def set_current(state, current):
    if state is not None:
        state['current'] = current


def set_total(state, total):
    if state is not None:
        state['total'] = total


def should_stop(state):
    return bool(state and state.get('should_stop'))


# ── 큐 조작 ──

def enqueue(kind, params=None, label='', max_attempts=None):
    """작업 대기열 등록. 반환: job_id"""
    ma = MAX_ATTEMPTS if max_attempts is None else max_attempts
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO queue_job (kind, params, label, queue, status, progress, max_attempts) "
            "VALUES (?, ?, ?, ?, 'queued', '대기 중', ?)",
            (kind, json.dumps(params or {}, ensure_ascii=False), label, lane_for(kind), ma))
        return cur.lastrowid


def retry(job_id):
    """기존 작업을 같은 파라미터로 재등록"""
    with get_conn() as conn:
        row = conn.execute('SELECT kind, params, label FROM queue_job WHERE id=?', (job_id,)).fetchone()
    if row is None:
        return None
    return enqueue(row['kind'], json.loads(row['params'] or '{}'), row['label'])


def request_stop(job_id):
    """특정 작업 중지(대기중이면 취소, 실행중이면 중지 요청)"""
    with get_conn() as conn:
        row = conn.execute('SELECT status FROM queue_job WHERE id=?', (job_id,)).fetchone()
        if row is None:
            return False
        if row['status'] == 'queued':
            conn.execute("UPDATE queue_job SET status='stopped' WHERE id=?", (job_id,))
        elif row['status'] == 'running':
            conn.execute('UPDATE queue_job SET stop_requested=1 WHERE id=?', (job_id,))
    st = _running.get(job_id)
    if st is not None:
        st['should_stop'] = True
    return True


def stop_all():
    """대기열 비우고 실행중 작업 중지"""
    with get_conn() as conn:
        conn.execute("UPDATE queue_job SET status='stopped' WHERE status='queued'")
        conn.execute("UPDATE queue_job SET stop_requested=1 WHERE status='running'")
    for st in list(_running.values()):
        st['should_stop'] = True


# ── 조회 ──

def current_status():
    """대표 실행중 작업 + 레인별 상태"""
    with get_conn() as conn:
        running = conn.execute(
            "SELECT * FROM queue_job WHERE status='running' ORDER BY started_at DESC, id DESC").fetchall()
        queued = conn.execute("SELECT COUNT(*) FROM queue_job WHERE status='queued'").fetchone()[0]
        last = conn.execute('SELECT * FROM queue_job ORDER BY id DESC LIMIT 1').fetchone()

    lanes = {}
    for lane in LANES:
        jr = next((r for r in running if r['queue'] == lane), None)
        lanes[lane] = {
            'running': jr is not None,
            'kind': jr['kind'] if jr else None,
            'progress': jr['progress'] if jr else '',
            'current': jr['current'] if jr else 0,
            'total': jr['total'] if jr else 0,
            'stopping': bool(jr['stop_requested']) if jr else False,
            'error': bool(jr['error']) if jr else False,
        }

    ref = running[0] if running else last
    if ref is None:
        base = {'running': False, 'kind': None, 'progress': '', 'stopping': False,
                'current': 0, 'total': 0, 'error': False}
    else:
        base = {
            'running': len(running) > 0,
            'kind': ref['kind'],
            'progress': ref['progress'],
            'stopping': bool(ref['stop_requested']) if running else False,
            'current': ref['current'],
            'total': ref['total'],
            'error': bool(ref['error']),
        }
    base['queued'] = queued
    base['lanes'] = lanes
    return base


def recent_jobs(limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT id, kind, label, queue, status, progress, current, total, error,
                      attempts, max_attempts, created_at, started_at, finished_at
               FROM queue_job ORDER BY id DESC LIMIT ?''', (limit,)).fetchall()
        return [dict(r) for r in rows]


# ── 운영 지표 ──

def _cutoff(**kw):
    return (datetime.now() - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')


def metrics_collect():
    """queue_job 테이블에서 운영 지표 집계(추가 인프라 없이 SQLite)"""
    with get_conn() as conn:
        by_status = {r['status']: r['n'] for r in
                     conn.execute('SELECT status, COUNT(*) n FROM queue_job GROUP BY status').fetchall()}
        lanes = {ln: {'queued': 0, 'running': 0} for ln in LANES}
        for r in conn.execute(
                "SELECT queue, status, COUNT(*) n FROM queue_job "
                "WHERE status IN ('queued','running') GROUP BY queue, status").fetchall():
            if r['queue'] in lanes:
                lanes[r['queue']][r['status']] = r['n']

        c1h = _cutoff(hours=1)
        c24 = _cutoff(hours=24)
        done_1h = conn.execute("SELECT COUNT(*) FROM queue_job WHERE status='done' AND finished_at>=?", (c1h,)).fetchone()[0]
        done_24 = conn.execute("SELECT COUNT(*) FROM queue_job WHERE status='done' AND finished_at>=?", (c24,)).fetchone()[0]
        err_24 = conn.execute("SELECT COUNT(*) FROM queue_job WHERE status='error' AND finished_at>=?", (c24,)).fetchone()[0]
        avg_dur = conn.execute(
            "SELECT AVG((julianday(finished_at)-julianday(started_at))*86400) FROM queue_job "
            "WHERE status='done' AND finished_at>=? AND started_at IS NOT NULL", (c24,)).fetchone()[0]
        retried = conn.execute('SELECT COUNT(*) FROM queue_job WHERE attempts>1').fetchone()[0]

    total_24 = done_24 + err_24
    return {
        'by_status': {s: by_status.get(s, 0) for s in ['queued', 'running', 'done', 'error', 'stopped']},
        'by_lane': lanes,
        'queue_depth': by_status.get('queued', 0),
        'running': by_status.get('running', 0),
        'done_1h': done_1h,
        'done_24h': done_24,
        'error_24h': err_24,
        'failure_rate_24h': round(err_24 / total_24, 3) if total_24 else 0.0,
        'avg_duration_sec_24h': round(avg_dur, 1) if avg_dur else 0.0,
        'retried': retried,
    }


def prometheus_text():
    """Prometheus 텍스트 포맷(/metrics 스크레이프용)"""
    m = metrics_collect()
    lines = []

    def g(name, value, help_text):
        lines.append(f'# HELP {name} {help_text}')
        lines.append(f'# TYPE {name} gauge')
        lines.append(f'{name} {value}')

    for status, n in m['by_status'].items():
        lines.append(f'jobs_total{{status="{status}"}} {n}')
    for lane, d in m['by_lane'].items():
        lines.append(f'jobs_lane{{lane="{lane}",state="queued"}} {d["queued"]}')
        lines.append(f'jobs_lane{{lane="{lane}",state="running"}} {d["running"]}')
    g('jobs_queue_depth', m['queue_depth'], 'Queued jobs')
    g('jobs_running', m['running'], 'Running jobs')
    g('jobs_done_1h', m['done_1h'], 'Jobs done in last hour')
    g('jobs_done_24h', m['done_24h'], 'Jobs done in last 24h')
    g('jobs_error_24h', m['error_24h'], 'Jobs errored in last 24h')
    g('jobs_failure_rate_24h', m['failure_rate_24h'], 'Failure rate last 24h')
    g('jobs_avg_duration_seconds_24h', m['avg_duration_sec_24h'], 'Avg job duration last 24h')
    g('jobs_retried_total', m['retried'], 'Jobs retried at least once')
    return '\n'.join(lines) + '\n'


# ── 워커 ──

def _claim_next(lane):
    """해당 레인의 대기 작업 1건을 원자적으로 running 전환(다중 워커 안전)"""
    # contextmanager 대신 명시 트랜잭션(BEGIN IMMEDIATE)으로 원자 클레임
    from svkit.db import connect
    conn = connect()
    conn.isolation_level = None
    try:
        conn.execute('BEGIN IMMEDIATE')
        now = time.time()
        row = conn.execute(
            "SELECT * FROM queue_job WHERE status='queued' AND queue=? AND run_at<=? ORDER BY id LIMIT 1",
            (lane, now)).fetchone()
        if row is None:
            conn.execute('COMMIT')
            return None
        conn.execute(
            "UPDATE queue_job SET status='running', started_at=?, heartbeat_at=?, attempts=attempts+1 WHERE id=?",
            (_now(), now, row['id']))
        conn.execute('COMMIT')
        return dict(row)
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _flush(job_id, state, final_status=None):
    with get_conn() as conn:
        if final_status:
            conn.execute(
                'UPDATE queue_job SET status=?, progress=?, current=?, total=?, error=?, finished_at=? WHERE id=?',
                (final_status, state.get('progress', ''), state.get('current', 0), state.get('total', 0),
                 1 if state.get('error') else 0, _now(), job_id))
        else:
            conn.execute(
                'UPDATE queue_job SET progress=?, current=?, total=?, error=? WHERE id=?',
                (state.get('progress', ''), state.get('current', 0), state.get('total', 0),
                 1 if state.get('error') else 0, job_id))


def _finalize_or_retry(job_id, state):
    """오류 종료 시 시도 여유가 있으면 백오프 후 재큐, 없으면 오류 확정"""
    with get_conn() as conn:
        row = conn.execute('SELECT attempts, max_attempts FROM queue_job WHERE id=?', (job_id,)).fetchone()
    attempts = row['attempts'] if row else 1
    max_a = row['max_attempts'] if row else 1
    if attempts < max_a:
        with get_conn() as conn:
            conn.execute(
                "UPDATE queue_job SET status='queued', run_at=?, stop_requested=0, error=0, progress=? WHERE id=?",
                (time.time() + RETRY_BACKOFF, f'재시도 대기 ({attempts}/{max_a})', job_id))
        logger.info('worker', '재시도예약', job_id=job_id, attempts=attempts, max=max_a)
    else:
        _flush(job_id, state, final_status='error')
        alerts.notify(f"작업 실패 (id {job_id}): {state.get('progress', '')}")


def _run_job(row):
    job_id = row['id']
    params = json.loads(row['params'] or '{}')
    handler = _HANDLERS.get(row['kind'])
    state = {'should_stop': False, 'progress': '시작', 'current': 0, 'total': 0, 'error': False}
    _running[job_id] = state

    if handler is None:
        state['error'] = True
        state['progress'] = f"핸들러 없음: {row['kind']}"
        _flush(job_id, state, final_status='error')
        _running.pop(job_id, None)
        return

    stop_monitor = threading.Event()

    def monitor():
        while not stop_monitor.is_set():
            with get_conn() as conn:
                r = conn.execute('SELECT stop_requested FROM queue_job WHERE id=?', (job_id,)).fetchone()
                if r and r['stop_requested']:
                    state['should_stop'] = True
                # 하트비트 + 진행 반영(워커 생존 신호)
                conn.execute(
                    'UPDATE queue_job SET progress=?, current=?, total=?, error=?, heartbeat_at=? WHERE id=?',
                    (state.get('progress', ''), state.get('current', 0), state.get('total', 0),
                     1 if state.get('error') else 0, time.time(), job_id))
            stop_monitor.wait(1)

    mon = threading.Thread(target=monitor, daemon=True)
    mon.start()
    status = 'done'
    try:
        handler[0](state, params)
        if state.get('should_stop'):
            status = 'stopped'
    except Exception as e:
        traceback.print_exc()
        state['error'] = True
        state['progress'] = f"[{row['kind']}] 오류: {e}"
        status = 'error'
    finally:
        stop_monitor.set()
        mon.join(timeout=2)
        if status == 'error':
            _finalize_or_retry(job_id, state)
        else:
            _flush(job_id, state, final_status=status)
        _running.pop(job_id, None)
        if BACKUP_AFTER_JOB:
            try:
                from svkit.db import backup
                backup()
            except Exception as e:
                logger.error('worker', '백업오류', err=str(e))


def reap():
    """하트비트가 끊긴 고아 작업(죽은 워커) 회수: 재시도 여유 있으면 재큐, 없으면 오류"""
    now = time.time()
    threshold = now - HEARTBEAT_TIMEOUT
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, attempts, max_attempts FROM queue_job WHERE status='running' AND heartbeat_at < ?",
            (threshold,)).fetchall()
        for r in rows:
            if r['attempts'] < r['max_attempts']:
                conn.execute(
                    "UPDATE queue_job SET status='queued', run_at=?, stop_requested=0, progress='워커 중단, 재시도' WHERE id=?",
                    (now + RETRY_BACKOFF, r['id']))
                logger.info('reaper', '회수-재시도', job_id=r['id'])
            else:
                conn.execute(
                    "UPDATE queue_job SET status='error', error=1, progress='워커 중단' WHERE id=?", (r['id'],))
                logger.error('reaper', '회수-오류', job_id=r['id'])
                alerts.notify(f"워커 중단으로 작업 실패 (id {r['id']})")


def _lane_loop(lane):
    while True:
        try:
            row = _claim_next(lane)
        except Exception as e:
            logger.error('worker', '클레임오류', lane=lane, err=str(e))
            time.sleep(1)
            continue
        if row is None:
            time.sleep(1)
            continue
        logger.info('worker', '작업시작', job_id=row['id'], kind=row['kind'], lane=lane)
        _run_job(row)
        logger.info('worker', '작업종료', job_id=row['id'])


def _reaper_loop():
    while True:
        time.sleep(REAPER_INTERVAL)
        try:
            reap()
        except Exception as e:
            logger.error('reaper', '회수오류', err=str(e))


def worker_loop():
    """레인별 워커 스레드 + 리퍼 기동 후 대기(전용 워커 프로세스 엔트리)"""
    logger.info('worker', '시작', lanes=','.join(LANES))
    threading.Thread(target=_reaper_loop, daemon=True).start()
    threads = []
    for lane in LANES:
        t = threading.Thread(target=_lane_loop, args=(lane,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


def start_worker_thread():
    """인프로세스 워커(개발/단일 컨테이너용). 레인별 스레드 + 리퍼"""
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
    threading.Thread(target=_reaper_loop, daemon=True).start()
    for lane in LANES:
        threading.Thread(target=_lane_loop, args=(lane,), daemon=True).start()


# ── 운영 API (/api/queue) ──

bp = make_blueprint('queue')


@bp.get('/jobs')
@require_auth
def api_jobs():
    limit = min(max(1, request.args.get('limit', 20, type=int)), 100)
    return ok({'jobs': recent_jobs(limit)})


@bp.post('/jobs/<int:job_id>/stop')
@require_admin
def api_job_stop(job_id):
    if not request_stop(job_id):
        return err('작업 없음', 404)
    return ok({'message': '중지 요청'})


@bp.post('/jobs/<int:job_id>/retry')
@require_admin
def api_job_retry(job_id):
    new_id = retry(job_id)
    if new_id is None:
        return err('작업 없음', 404)
    return ok({'message': '재시도 등록', 'job_id': new_id})


@bp.post('/stop_all')
@require_admin
def api_stop_all():
    stop_all()
    return ok({'message': '중지 요청'})


@bp.get('/kinds')
@require_auth
def api_kinds():
    return ok({'kinds': registered_kinds()})


@bp.post('/enqueue')
@require_admin
def api_enqueue():
    """등록된 kind 를 임의 파라미터로 즉시 등록(배치 단계 재실행 등)"""
    data = request.get_json() or {}
    kind = data.get('kind', '')
    if kind not in _HANDLERS:
        return err(f'등록되지 않은 kind: {kind}', 400)
    job_id = enqueue(kind, data.get('params') or {}, data.get('label', ''))
    return ok({'message': '등록', 'job_id': job_id})


@bp.get('/status')
@require_auth
def api_status():
    return ok(current_status())


@bp.get('/metrics')
@require_auth
def api_metrics():
    return ok(metrics_collect())


@bp.get('/stream')
@require_auth
def api_stream():
    """SSE: 상태/메트릭/작업목록을 변화 시에만 푸시(폴링 대체)"""
    return stream_response(lambda: {
        'status': current_status(),
        'metrics': metrics_collect(),
        'jobs': recent_jobs(50),
    })
