"""스케줄러 공통 포맷 — 등록된 큐 kind 를 주기 자동 실행(매일 HH:MM / N분 간격).

스케줄은 DB(queue_schedule)에 저장되어 API 로 관리한다. 워커와 함께 도는
스케줄러 스레드가 due 스케줄을 원자적으로 클레임해 큐에 넣는다.
중복 방지: BEGIN IMMEDIATE 클레임(다중 프로세스) + 동일 kind 의 활성
작업(대기/실행중)이 있으면 이번 회차는 스킵.

spec 형식: 'daily HH:MM'(매일 지정 시각, 서버 TZ) | 'interval N'(N분 간격)
컨테이너에서 로컬 시각 기준 실행이 필요하면 TZ env(예: Asia/Seoul)를 설정한다.

기본 스케줄은 도메인이 DOMAIN['schedules'] 로 선언하면 부팅 시 등록된다:
  'schedules': [{'name': 'catalog-daily', 'kind': 'batch.catalog_daily',
                 'spec': 'daily 00:00'}]
이미 존재하는 이름은 덮어쓰지 않는다(사용자의 수정값 유지).

운영 API(/api/schedule): list / save / toggle / run(즉시 실행) / delete.
"""
import json
import os
import threading
import time
from datetime import datetime

from flask import request

from svkit.api import make_blueprint
from svkit import logger
from svkit.auth import require_admin, require_auth
from svkit.base import SPEC_HELP, compute_next
from svkit.db import connect, get_conn
from svkit.response import err, ok

SCHEMA = '''
CREATE TABLE IF NOT EXISTS queue_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,
    params TEXT DEFAULT '{}',
    spec TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run_at TEXT,
    next_run_at REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
'''

ENABLED = os.environ.get('SCHEDULER_ENABLED', 'true').lower() == 'true'
TICK = float(os.environ.get('SCHEDULER_TICK', '20'))

_started = False
_lock = threading.Lock()


def ensure(name, kind, spec, params=None, enabled=1):
    """기본 스케줄 등록(이미 있으면 사용자 수정값 유지)"""
    with get_conn() as conn:
        if conn.execute('SELECT 1 FROM queue_schedule WHERE name=?', (name,)).fetchone():
            return
        conn.execute(
            'INSERT INTO queue_schedule (name, kind, params, spec, enabled, next_run_at) VALUES (?,?,?,?,?,?)',
            (name, kind, json.dumps(params or {}, ensure_ascii=False), spec, enabled, compute_next(spec)))


def retire(names):
    """더 이상 쓰지 않는 스케줄 삭제(구조 변경 시 낡은 스케줄 정리). 멱등"""
    if not names:
        return
    with get_conn() as conn:
        conn.executemany('DELETE FROM queue_schedule WHERE name=?', [(n,) for n in names])


def init_defaults():
    """도메인 DOMAIN['schedules'] 등록 + DOMAIN['retire_schedules'] 정리(db.init_all 이 호출).

    retire 를 먼저 처리해 이름을 재사용(같은 이름, 다른 kind)하는 경우에도 새 정의로 갱신되게 한다.
    """
    from svkit import registry
    for dom in registry.DOMAINS:
        try:
            retire(dom.get('retire_schedules'))
        except Exception as e:
            logger.error('scheduler', '폐기실패', err=str(e))
    for dom in registry.DOMAINS:
        for s in dom.get('schedules') or []:
            try:
                ensure(s['name'], s['kind'], s['spec'], s.get('params'), s.get('enabled', 1))
            except Exception as e:
                logger.error('scheduler', '기본등록실패', name=s.get('name'), err=str(e))


def tick():
    """due 스케줄을 클레임해 큐에 넣는다(svkit2 와 같은 이름·역할)."""
    from svkit import queue
    now = time.time()
    conn = connect()
    conn.isolation_level = None
    try:
        # due 스케줄을 원자 클레임(next_run_at 선갱신 → 다중 프로세스 중복 방지)
        conn.execute('BEGIN IMMEDIATE')
        due = [dict(r) for r in conn.execute(
            'SELECT * FROM queue_schedule WHERE enabled=1 AND next_run_at>0 AND next_run_at<=?',
            (now,)).fetchall()]
        for r in due:
            conn.execute('UPDATE queue_schedule SET next_run_at=?, last_run_at=? WHERE id=?',
                         (compute_next(r['spec']), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), r['id']))
        conn.execute('COMMIT')
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        conn.close()
    for r in due:
        if queue.has_active(r['kind']):
            logger.info('scheduler', '스킵-중복', name=r['name'])
            continue
        queue.enqueue(r['kind'], json.loads(r['params'] or '{}'), label=f"자동 {r['name']}")
        logger.info('scheduler', '실행', name=r['name'], kind=r['kind'])


#: 옛 이름(내부용) — 기존 호출부 보호
_tick = tick


def _loop():
    while True:
        try:
            tick()
        except Exception as e:
            logger.error('scheduler', '오류', err=str(e))
        time.sleep(TICK)


def start_thread():
    """스케줄러 스레드 시작(워커 프로세스와 함께 배선). 중복 시작 방지"""
    global _started
    if not ENABLED:
        return
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, daemon=True).start()
    logger.info('scheduler', '시작', tick=TICK)


#: svkit2 와 이름을 맞춘 별칭(그쪽은 태스크, 여기는 스레드)
start = start_thread


# ── 운영 API (/api/schedule) ──

bp = make_blueprint('schedule')


@bp.get('/list')
@require_auth
def api_list():
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM queue_schedule ORDER BY id').fetchall()]
    return ok({'schedules': rows})


@bp.post('/save')
@require_admin
def api_save():
    """생성/수정. body: {id?, name, kind, spec, params?, enabled?}"""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    kind = (data.get('kind') or '').strip()
    spec = (data.get('spec') or '').strip()
    if not name or not kind or not spec:
        return err('name/kind/spec 필수', 400)
    try:
        next_at = compute_next(spec)
    except (ValueError, IndexError):
        return err(SPEC_HELP, 400)
    params = json.dumps(data.get('params') or {}, ensure_ascii=False)
    enabled = 1 if data.get('enabled', 1) else 0
    with get_conn() as conn:
        if data.get('id'):
            conn.execute(
                'UPDATE queue_schedule SET name=?, kind=?, params=?, spec=?, enabled=?, next_run_at=? WHERE id=?',
                (name, kind, params, spec, enabled, next_at, data['id']))
        else:
            conn.execute(
                'INSERT INTO queue_schedule (name, kind, params, spec, enabled, next_run_at) VALUES (?,?,?,?,?,?)',
                (name, kind, params, spec, enabled, next_at))
    return ok({'message': '저장'})


@bp.post('/<int:sid>/toggle')
@require_admin
def api_toggle(sid):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM queue_schedule WHERE id=?', (sid,)).fetchone()
        if row is None:
            return err('스케줄 없음', 404)
        enabled = 0 if row['enabled'] else 1
        next_at = compute_next(row['spec']) if enabled else 0
        conn.execute('UPDATE queue_schedule SET enabled=?, next_run_at=? WHERE id=?',
                     (enabled, next_at, sid))
    return ok({'enabled': bool(enabled)})


@bp.post('/<int:sid>/run')
@require_admin
def api_run(sid):
    """즉시 1회 실행(스케줄 주기와 무관). body.params 로 오버라이드 가능"""
    from svkit import queue
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM queue_schedule WHERE id=?', (sid,)).fetchone()
    if row is None:
        return err('스케줄 없음', 404)
    params = json.loads(row['params'] or '{}')
    params.update((request.get_json(silent=True) or {}).get('params') or {})
    if queue.has_active(row['kind']):
        return err('같은 작업이 이미 대기/실행 중', 409)
    job_id = queue.enqueue(row['kind'], params, label=f"수동 {row['name']}")
    return ok({'message': '실행 등록', 'job_id': job_id})


@bp.post('/<int:sid>/delete')
@require_admin
def api_delete(sid):
    with get_conn() as conn:
        conn.execute('DELETE FROM queue_schedule WHERE id=?', (sid,))
    return ok({'message': '삭제'})
