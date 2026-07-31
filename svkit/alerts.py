"""공통 실패 알림(Slack) — 설정 없으면 무동작. Webhook 또는 Bot토큰+채널 택1.

env: SLACK_ALERT_WEBHOOK 또는 SLACK_ALERT_TOKEN+SLACK_ALERT_CHANNEL,
     SLACK_ALERT_COOLDOWN(초, 중복 억제)
"""
import json
import os
import threading
import time
import urllib.request

from svkit import logger

SLACK_WEBHOOK = os.environ.get('SLACK_ALERT_WEBHOOK', '')
SLACK_TOKEN = os.environ.get('SLACK_ALERT_TOKEN', '')
SLACK_CHANNEL = os.environ.get('SLACK_ALERT_CHANNEL', '')
_COOLDOWN = float(os.environ.get('SLACK_ALERT_COOLDOWN', '60'))

_last = 0.0
_lock = threading.Lock()


def enabled():
    return bool(SLACK_WEBHOOK or (SLACK_TOKEN and SLACK_CHANNEL))


def notify(text):
    """실패 알림 전송(쿨다운 내 중복 억제). 미설정 시 무동작"""
    if not enabled():
        return
    global _last
    with _lock:
        now = time.time()
        if now - _last < _COOLDOWN:
            return
        _last = now
    try:
        if SLACK_WEBHOOK:
            data = json.dumps({'text': text}).encode('utf-8')
            req = urllib.request.Request(
                SLACK_WEBHOOK, data=data,
                headers={'Content-Type': 'application/json'})
        else:
            data = json.dumps({'channel': SLACK_CHANNEL, 'text': text}).encode('utf-8')
            req = urllib.request.Request(
                'https://slack.com/api/chat.postMessage', data=data,
                headers={'Content-Type': 'application/json; charset=utf-8',
                         'Authorization': f'Bearer {SLACK_TOKEN}'})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.error('alert', '전송실패', err=str(e))
