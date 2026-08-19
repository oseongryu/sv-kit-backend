"""리버스 프록시 — `<prefix>/*` 를 upstream 으로 HTTP 스트리밍 중계하는 ASGI 미들웨어.

화면 하나가 서비스 둘의 API 를 부를 때, 화면이 아는 같은 오리진 접두를 다른 서비스로
넘긴다. **응답은 청크 단위로 중계한다** — 통째로 읽어 넘기면 SSE 가 끝날 때까지 아무것도
나가지 않는다. 클라이언트가 끊으면 업스트림도 함께 닫는다.

의존은 ASGI 규약과 `requests` 뿐이라 프레임워크를 모른다.
"""
import asyncio
import functools

import requests

from svkit.infra.logger import get_logger

log = get_logger(__name__)

#: 한 번에 중계하는 바이트. SSE 는 이보다 훨씬 작은 단위로 도착하고, 그때그때 나간다.
_CHUNK = 64 * 1024

# 프록시가 그대로 넘기면 안 되는 연결 단위 헤더 (RFC 9110 7.6.1)
_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})
#: 응답에서 걷어낼 헤더. 연결 단위 헤더에 더해 **우리 쪽 ASGI 서버가 자기 것을 붙이는
#: 헤더**를 뺀다 — 그대로 넘기면 `date` 가 두 줄 나간다. `content-length` 는 본문을
#: 손대지 않고 흘리므로(디코딩 없음) 업스트림 값이 그대로 맞아 남긴다.
_DROP_FROM_RESPONSE = _HOP_BY_HOP | {"date", "server"}


class HttpProxy:
    """`<prefix>/*` 를 `upstream` 으로 중계하는 ASGI 미들웨어 (HTTP 스트리밍)."""

    def __init__(self, app, *, prefix: str, upstream: str, connect_timeout: float = 10.0):
        self.app = app
        self.prefix = "/" + prefix.strip("/")
        self.upstream = upstream.rstrip("/")
        self.connect_timeout = connect_timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rest = self._strip(scope["path"])
        if rest is None:
            await self.app(scope, receive, send)
            return
        await self._relay(scope, receive, send, rest)

    def _strip(self, path: str) -> str | None:
        """접두를 뗀 나머지 경로. 이 프록시 소관이 아니면 `None`."""
        if path == self.prefix:
            return "/"
        if path.startswith(self.prefix + "/"):
            return path[len(self.prefix):]
        return None

    async def _relay(self, scope, receive, send, rest: str) -> None:
        query = scope.get("query_string") or b""
        url = f"{self.upstream}{rest}" + (f"?{query.decode()}" if query else "")
        headers = {k: v for k, v in _decode(scope["headers"])
                   if k not in _HOP_BY_HOP and k != "host"}
        body = await _read_body(receive)

        try:
            # read timeout 을 두지 않는다 — SSE 는 다음 이벤트까지 몇 분이 비어 있어도
            # 정상이다. 연결만 시간을 재고, 끊는 판단은 클라이언트에게 맡긴다.
            res = await asyncio.to_thread(functools.partial(
                requests.request, scope["method"], url,
                headers=headers, data=body or None, stream=True,
                allow_redirects=False, timeout=(self.connect_timeout, None)))
        except requests.RequestException as exc:
            log.warning("프록시 연결 실패 %s: %s", url, exc)
            await _plain(send, 502, b"upstream unreachable")
            return

        out = [(k.lower(), v) for k, v in res.headers.items()
               if k.lower() not in _DROP_FROM_RESPONSE]
        await send({"type": "http.response.start", "status": res.status_code,
                    "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in out]})

        # 클라이언트가 먼저 끊으면(탭 닫기·SSE 취소) 업스트림도 닫아 준다 — 안 그러면
        # 다음 청크를 기다리는 스레드가 스트림이 끝날 때까지 남는다.
        watcher = asyncio.create_task(_close_on_disconnect(receive, res))
        chunks = res.raw.stream(_CHUNK, decode_content=False)
        try:
            while True:
                chunk = await asyncio.to_thread(next, chunks, None)
                if chunk is None:
                    break
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        except (OSError, requests.RequestException) as exc:
            log.info("프록시 스트림 중단 %s: %s", url, exc)
        finally:
            watcher.cancel()
            await asyncio.to_thread(res.close)


async def _read_body(receive) -> bytes:
    """요청 본문을 모은다. 업로드는 이미지 한 장 단위라 통째로 들고 있어도 된다."""
    parts = []
    while True:
        msg = await receive()
        if msg["type"] == "http.disconnect":
            break
        parts.append(msg.get("body", b""))
        if not msg.get("more_body"):
            break
    return b"".join(parts)


async def _close_on_disconnect(receive, res) -> None:
    while True:
        msg = await receive()
        if msg["type"] == "http.disconnect":
            await asyncio.to_thread(res.close)
            return


def _decode(raw_headers) -> list:
    return [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in raw_headers]


async def _plain(send, status: int, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
