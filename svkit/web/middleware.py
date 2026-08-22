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


def camel_opaque_keys() -> frozenset:
    """도메인이 `DOMAIN["camel_opaque"]` 로 선언한 **값이 데이터인 키**.

    그 키의 하위 트리는 변환하지 않는다 — 사람이 이름을 짓는 dict(잡 파라미터·자동화
    파라미터·지표 attrs)까지 바꾸면 저장된 값이 바뀐다. 목록은 앱이 갖는다.
    """
    from svkit.web import app as web

    out = set()
    for dom in web.DOMAINS:
        out.update(dom.get('camel_opaque') or [])
    return frozenset(out)


class CasingMiddleware(BaseHTTPMiddleware):
    """선언한 경로에서만 바깥 camelCase 와 안쪽 snake_case 를 오간다.

    요청은 JSON 본문·쿼리스트링의 **키**를 snake 로 바꾸고, 응답은 규약 봉투의
    `data` 만 camel 로 바꾼다(`ok`·`error`·`meta` 는 그대로). 값은 손대지 않는다.

    대상 경로는 첫 요청 때 모은다 — 미들웨어 등록이 도메인 로드보다 먼저여도 되게.
    **선언이 하나도 없으면 아무 것도 하지 않는다.**
    """

    def __init__(self, app, prefixes: tuple | None = None, opaque=None):
        super().__init__(app)
        self._prefixes = prefixes
        self._opaque = opaque

    async def dispatch(self, request, call_next):
        if self._prefixes is None:
            self._prefixes = camel_api_prefixes()
            self._opaque = camel_opaque_keys() if self._opaque is None else self._opaque
        if not self._prefixes or not request.url.path.startswith(self._prefixes):
            return await call_next(request)

        await self._request_to_snake(request, self._opaque or frozenset())
        response = await call_next(request)
        return await self._response_to_camel(response, self._opaque or frozenset())

    @staticmethod
    async def _request_to_snake(request, opaque) -> None:
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
                body = json.dumps(keys_to_snake(payload, opaque),
                                  ensure_ascii=False).encode('utf-8')
                request._body = body

                async def receive():
                    return {'type': 'http.request', 'body': body, 'more_body': False}

                request._receive = receive

    @staticmethod
    async def _response_to_camel(response, opaque):
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
            payload['data'] = keys_to_camel(payload['data'], opaque)
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {k: v for k, v in response.headers.items() if k.lower() != 'content-length'}
        return Response(content=raw, status_code=response.status_code, headers=headers,
                        media_type='application/json')


class AuthGateMiddleware:
    """보호 접두 아래 HTTP 요청을 토큰 하나로 지키는 ASGI 게이트.

    자리는 `Authorization: Bearer <토큰>` 하나이고 출처가 셋이다 — 사람(로그인 JWT
    role=admin) · 앱(발급 JWT role=app, 지문 바인딩) · 기계(설정 고정값). 받는 쪽은
    출처를 구분하지 않고 role 만 본다.

    - `AUTH_ENABLED` 꺼짐 → 전부 통과 (기존 배포 무영향).
    - `admin` 접두는 role=admin 만 (기계 고정키는 서버간 채널이라 통과).
    - role=app 토큰은 요청 UA 로 지문을 다시 계산해 대조한다. **어긋나도 즉시 막지
      않는다**(`svkit.web.device`) — 유예 뒤 확률적으로 막고, 거절 문구는 무토큰과 같다.
    - `JWT_SECRET` 미설정도 401 이다 — 화면이 로그인으로 리다이렉트하는 동선을 지키고
      (구성 오류 문구를 위젯마다 흘리지 않는다), 상세는 로그인 시도가 503 으로 말한다.
    - 경로의 뜻은 앱이 안다 — 보호·예외·관리 접두는 인자로 받는다.
    - 옛 헤더(`X-Admin-Key`·`X-Admin-Token`)도 계속 받는다 — 이미 도는 운영 스크립트가
      깨지지 않게. 새로 쓰는 쪽은 Bearer 하나다.
    """

    def __init__(self, app, protect: tuple = ("/api/",),
                 exempt: tuple = ("/api/auth/", "/api/health", "/api/domains"),
                 admin: tuple = ("/api/admin/",)):
        self.app = app
        self.protect = tuple(protect)
        self.exempt = tuple(exempt)
        self.admin = tuple(admin)

    def _needs_auth(self, path: str) -> bool:
        if not any(path.startswith(p) for p in self.protect):
            return False
        return not any(path == e.rstrip("/") or path.startswith(e)
                       for e in self.exempt)

    def _is_admin_path(self, path: str) -> bool:
        return any(path == a.rstrip("/") or path.startswith(a) for a in self.admin)

    @staticmethod
    def _header(scope, name: str) -> str:
        for k, v in scope.get("headers") or []:
            if k.decode("latin-1").lower() == name:
                return v.decode("latin-1")
        return ""

    @classmethod
    def _token_of(cls, scope) -> str:
        auth = cls._header(scope, "authorization")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        from urllib.parse import parse_qs

        qs = parse_qs((scope.get("query_string") or b"").decode("latin-1"))
        return (qs.get("token") or [""])[0]

    @staticmethod
    async def _deny(send, status: int, message: str) -> None:
        import json as _json

        body = _json.dumps({"ok": False, "error": message},
                           ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not self._needs_auth(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        from svkit.loader import conf

        if not conf.get_bool("AUTH_ENABLED"):
            await self.app(scope, receive, send)
            return

        presented = self._token_of(scope)

        # 기계 채널 — 고정값은 Bearer 로도, 옛 헤더로도 받는다.
        fixed = {v for v in (conf.get_str("ADMIN_API_KEY").strip(),
                             conf.get_str("ADMIN_TOKEN").strip()) if v}
        if fixed and (presented in fixed
                      or self._header(scope, "x-admin-key").strip() in fixed
                      or self._header(scope, "x-admin-token").strip() in fixed):
            await self.app(scope, receive, send)
            return

        if not conf.get_str("JWT_SECRET").strip():
            await self._deny(send, 401, "인증 필요")
            return

        from svkit.web.security import verify_token

        payload = verify_token(presented)
        if not payload:
            await self._deny(send, 401, "인증 필요")
            return

        role = str(payload.get("role") or "")

        if self._is_admin_path(scope.get("path", "")) and role != "admin":
            await self._deny(send, 403, "권한 없음")
            return

        if role == "app":
            from svkit.web import device

            client = device.client_id(self._header(scope, "x-app-client"),
                                      self._header(scope, "user-agent"))
            if device.check(payload, client):
                # 사유는 로그가 갖는다 — 응답 문구는 무토큰과 같아야 무엇이 걸렸는지
                # 드러나지 않는다.
                delay = device.suspect_delay_sec()
                if delay:
                    import asyncio

                    await asyncio.sleep(delay)
                await self._deny(send, 401, "인증 필요")
                return

        await self.app(scope, receive, send)
