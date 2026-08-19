"""서버 공용 미들웨어 — 요청 로깅 + 이미지 엔드포인트 rate limit.

단일 워커 전제의 인메모리 고정윈도 — 멀티 워커/분산 배포 시 외부 스토어로 교체 필요.

설정(`config/common.yml`): `RATE_LIMIT_PER_MIN`(도메인 선언 경로 한정, 0 이면 비활성)·
`RATE_LIMIT_ALL_PER_MIN`(모든 API 경로 상한, 0 이면 비활성)·`TRUST_PROXY`(XFF 신뢰)·
`CORS_ORIGINS`.
"""

import json
import logging
import time
import uuid
from urllib.parse import parse_qsl, urlencode

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from svkit.loader import conf

_log = logging.getLogger('ops')

_SKIP_LOG = ('/health', '/docs', '/openapi.json', '/favicon.ico', '/views')

_WINDOW_SEC = 60
_MAX_IPS = 10000
# config 를 못 읽거나 값이 망가졌을 때의 최후 방어선 — 운영값의 자리는 config/common.yml.
_FALLBACK_PER_MIN = 30


class RateLimiter:
    """고정윈도 카운터 — 순수 로직(검증 용이하게 미들웨어와 분리)."""

    def __init__(self, per_min: int, window: float = _WINDOW_SEC):
        self.per_min = int(per_min)
        self.window = float(window)
        self._hits: dict[str, tuple[float, int]] = {}  # ip → (윈도시작, 카운트)

    @property
    def enabled(self) -> bool:
        return self.per_min > 0

    def allow(self, ip: str, now: float | None = None) -> bool:
        if not self.enabled:
            return True
        now = time.time() if now is None else now
        start, cnt = self._hits.get(ip, (now, 0))
        if now - start >= self.window:
            start, cnt = now, 0
        cnt += 1
        self._hits[ip] = (start, cnt)
        if len(self._hits) > _MAX_IPS:
            # 만료 윈도 정리 (단일 워커 — 단순 sweep 충분)
            self._hits = {k: v for k, v in self._hits.items()
                          if now - v[0] < self.window}
        return cnt <= self.per_min


def rate_limit_from_conf() -> RateLimiter:
    try:
        per_min = conf.get_int('RATE_LIMIT_PER_MIN', _FALLBACK_PER_MIN)
    except ValueError:
        per_min = _FALLBACK_PER_MIN
    return RateLimiter(per_min)


def global_rate_limit_from_conf() -> RateLimiter:
    """전 API 공통 상한. 미설정(0)이면 비활성이라 기존 배포는 그대로다."""
    try:
        per_min = conf.get_int('RATE_LIMIT_ALL_PER_MIN', 0)
    except ValueError:
        per_min = 0
    return RateLimiter(per_min)


def client_ip(request) -> str:
    """호출자 IP. 프록시 뒤(`TRUST_PROXY`)면 XFF 첫 홉을 쓴다 — 안 그러면 전원이 한 IP 로 묶인다."""
    if conf.get_bool('TRUST_PROXY', False):
        xff = request.headers.get('x-forwarded-for', '')
        first = xff.split(',')[0].strip()
        if first:
            return first
    return request.client.host if request.client else 'unknown'


def rate_limited_prefixes() -> tuple:
    """도메인이 `DOMAIN["rate_limited"]` 로 선언한 경로 목록."""
    from svkit.web import app as web

    out = []
    for dom in web.DOMAINS:
        out.extend(dom.get('rate_limited') or [])
    return tuple(out)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """도메인이 선언한 엔드포인트 한정 분당 요청 제한.

    대상 경로는 첫 요청 때 모은다 — 미들웨어 등록이 도메인 로드보다 먼저여도 되게.
    """

    def __init__(self, app, limiter: RateLimiter | None = None,
                 prefixes: tuple | None = None,
                 global_limiter: RateLimiter | None = None):
        super().__init__(app)
        self.limiter = limiter or rate_limit_from_conf()
        self.global_limiter = global_limiter or global_rate_limit_from_conf()
        self._prefixes = prefixes

    async def dispatch(self, request, call_next):
        if self._prefixes is None:
            self._prefixes = rate_limited_prefixes()
        path = request.url.path
        ip = client_ip(request)
        strict = (request.method == 'POST' and self._prefixes
                  and path.startswith(self._prefixes))
        if strict and not self.limiter.allow(ip):
            return self._too_many(ip, path)
        # 선언 밖 경로(CRUD·크롤 프록시 등)도 공통 상한으로 막는다
        if (not strict and self.global_limiter.enabled and path.startswith('/api')
                and not self.global_limiter.allow(ip)):
            return self._too_many(ip, path)
        return await call_next(request)

    @staticmethod
    def _too_many(ip: str, path: str) -> JSONResponse:
        _log.info('제한 %s %s', ip, path)
        return JSONResponse(
            status_code=429,
            content={'success': False,
                     'error': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'})


class RequestLogMiddleware(BaseHTTPMiddleware):
    """요청ID 부여 + 한 줄 액세스 로그."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith(_SKIP_LOG):
            return await call_next(request)
        rid = uuid.uuid4().hex[:8]
        t0 = time.time()
        response = await call_next(request)
        response.headers['X-Request-ID'] = rid
        _log.info('%s %s %s %d %dms', rid, request.method, path,
                  response.status_code, int((time.time() - t0) * 1000))
        return response


def cors_config() -> dict:
    """`CORS_ORIGINS`(콤마 구분). '*'면 credentials 비허용.

    ['*'] + allow_credentials=True 조합은 origin echo 로 사실상 무제한
    credential 허용이 되므로 금지 — 특정 origin 목록일 때만 credentials 허용.
    """
    raw = conf.get_str('CORS_ORIGINS').strip()
    origins = [o.strip() for o in raw.split(',') if o.strip()] or ['*']
    wildcard = '*' in origins
    return {
        'allow_origins': ['*'] if wildcard else origins,
        'allow_credentials': not wildcard,
        'allow_methods': ['*'],
        'allow_headers': ['*'],
    }


def camel_api_prefixes() -> tuple:
    """도메인이 `DOMAIN["camel_api"]` 로 선언한 경로 목록."""
    from svkit.web import app as web

    out = []
    for dom in web.DOMAINS:
        out.extend(dom.get('camel_api') or [])
    return tuple(out)


class CasingMiddleware(BaseHTTPMiddleware):
    """선언한 경로에서만 바깥 camelCase 와 안쪽 snake_case 를 오간다.

    요청은 JSON 본문·쿼리스트링의 **키**를 snake 로 바꾸고, 응답은 규약 봉투의
    `data` 만 camel 로 바꾼다(`ok`·`error`·`meta` 는 그대로). 값은 손대지 않는다.

    대상 경로는 첫 요청 때 모은다 — 미들웨어 등록이 도메인 로드보다 먼저여도 되게.
    **선언이 하나도 없으면 아무 것도 하지 않는다.**
    """

    def __init__(self, app, prefixes: tuple | None = None):
        super().__init__(app)
        self._prefixes = prefixes

    async def dispatch(self, request, call_next):
        if self._prefixes is None:
            self._prefixes = camel_api_prefixes()
        if not self._prefixes or not request.url.path.startswith(self._prefixes):
            return await call_next(request)

        await self._request_to_snake(request)
        response = await call_next(request)
        return await self._response_to_camel(response)

    @staticmethod
    async def _request_to_snake(request) -> None:
        from svkit.web.casing import camel_to_snake, keys_to_snake

        if request.scope.get('query_string'):
            pairs = parse_qsl(request.scope['query_string'].decode('utf-8'))
            request.scope['query_string'] = urlencode(
                [(camel_to_snake(k), v) for k, v in pairs]).encode('utf-8')

        if request.headers.get('content-type', '').startswith('application/json'):
            raw = await request.body()
            if raw:
                try:
                    payload = json.loads(raw)
                except ValueError:
                    return
                body = json.dumps(keys_to_snake(payload), ensure_ascii=False).encode('utf-8')
                request._body = body

                async def receive():
                    return {'type': 'http.request', 'body': body, 'more_body': False}

                request._receive = receive

    @staticmethod
    async def _response_to_camel(response):
        from svkit.web.casing import keys_to_camel

        if not response.headers.get('content-type', '').startswith('application/json'):
            return response
        raw = b''.join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(raw)
        except ValueError:
            return Response(content=raw, status_code=response.status_code,
                            headers=dict(response.headers))
        if isinstance(payload, dict) and 'data' in payload:
            payload['data'] = keys_to_camel(payload['data'])
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {k: v for k, v in response.headers.items() if k.lower() != 'content-length'}
        return Response(content=raw, status_code=response.status_code, headers=headers,
                        media_type='application/json')
