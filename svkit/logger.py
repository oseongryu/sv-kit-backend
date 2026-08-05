"""공통 구조화 로깅 — LOG_FORMAT=json 이면 한 줄 JSON, 아니면 사람용 텍스트.

사용: `logger.info('worker', '시작', lanes='crawl')`. 이벤트명은 짧은 한국어.
포맷은 `base.format_log` 하나라 svkit2 와 로그 모양이 같다.
"""
import os
import sys

from svkit.base import format_log

LOG_FORMAT = os.environ.get('LOG_FORMAT', 'text').lower()


def log(comp, event, level='info', **fields):
    stream = sys.stderr if level == 'error' else sys.stdout
    print(format_log(comp, event, level, fields, LOG_FORMAT == 'json'),
          file=stream, flush=True)


def info(comp, event, **fields):
    log(comp, event, level='info', **fields)


def error(comp, event, **fields):
    log(comp, event, level='error', **fields)


__all__ = ['log', 'info', 'error', 'LOG_FORMAT']