"""공통 구조화 로깅 — LOG_FORMAT=json 이면 한 줄 JSON, 아니면 사람용 텍스트.

사용: logger.info('worker', '시작', lanes='crawl'). 이벤트명은 짧은 한국어.
"""
import json
import os
from datetime import datetime

LOG_FORMAT = os.environ.get('LOG_FORMAT', 'text').lower()


def log(comp, event, level='info', **fields):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if LOG_FORMAT == 'json':
        rec = {'ts': ts, 'level': level, 'comp': comp, 'event': event}
        rec.update(fields)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    else:
        extra = ' '.join(f'{k}={v}' for k, v in fields.items())
        print(f'{ts} [{level}] {comp} {event} {extra}'.rstrip(), flush=True)


def info(comp, event, **fields):
    log(comp, event, level='info', **fields)


def error(comp, event, **fields):
    log(comp, event, level='error', **fields)
