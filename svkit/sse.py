"""SSE 공통 포맷 — 폴링 대체 실시간 스트림.

snapshot_fn() 이 반환한 dict 를 1초마다 비교해 변화가 있을 때만 push 한다.
프론트는 lib/hooks.ts 의 useEventStream 으로 소비한다(끊기면 폴링 폴백).

사용:
  from svkit.sse import stream_response
  @bp.get('/stream')
  def stream():
      return stream_response(lambda: {'status': ..., 'jobs': ...})
"""
import json
import time

from flask import Response


def stream_response(snapshot_fn, interval=1.0, ping_every=15):
    """변화 시에만 data 이벤트, 무변화 지속 시 주기적 ping(연결 유지)"""
    def gen():
        last = None
        ticks = 0
        while True:
            s = json.dumps(snapshot_fn(), ensure_ascii=False)
            if s != last:
                last = s
                yield f'data: {s}\n\n'
            else:
                ticks += 1
                if ticks % ping_every == 0:
                    yield ': ping\n\n'
            time.sleep(interval)
    return Response(gen(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
