"""SSE 공통 포맷 — 폴링 대체 실시간 스트림.

snapshot_fn() 이 반환한 값을 주기적으로 비교해 변화가 있을 때만 push 한다.
프론트는 @sv/kit-ui hooks 의 useEventStream 으로 소비한다(끊기면 폴링 폴백).

사용:
  from svkit.sse import stream_response
  @bp.get('/stream')
  def stream():
      return stream_response(lambda: {'status': ..., 'jobs': ...})

프레임 모양과 헤더는 base 에서 온다 — svkit2 의 EventStream 과 바이트가 같다.
"""
import time

from flask import Response

from svkit.base import SSE_HEADERS, SSE_PING, sse_data, sse_payload


def stream_response(snapshot_fn, interval=1.0, ping_every=15):
    """변화 시에만 data 이벤트, 무변화 지속 시 주기적 ping(연결 유지)"""
    def gen():
        last = None
        ticks = 0
        while True:
            payload = sse_payload(snapshot_fn())
            if payload != last:
                last = payload
                ticks = 0
                yield sse_data(payload)
            else:
                ticks += 1
                if ticks % ping_every == 0:
                    yield SSE_PING
            time.sleep(interval)
    return Response(gen(), mimetype='text/event-stream', headers=dict(SSE_HEADERS))


#: svkit2 는 같은 것을 Response 클래스(`EventStream`)로 준다. 이름을 맞춰 둔다 —
#: Flask 판에서는 함수 호출이지만 도메인 코드의 `return EventStream(...)` 이 그대로 돈다.
EventStream = stream_response

__all__ = ['stream_response', 'EventStream', 'SSE_HEADERS']