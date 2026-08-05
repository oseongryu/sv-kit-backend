"""svkit 계보 공통 기반 — Flask 판(svkit)과 FastAPI 판(svkit2)이 함께 상속하는 층.

이 파일은 두 저장소에 **같은 내용**으로 들어간다. 언젠가 둘을 합치면 이 파일
하나만 남고 나머지 모듈은 각자의 프레임워크 어댑터로 남는다. 그래서 여기에
들어갈 수 있는 것의 조건은 하나다 — **프레임워크·DB·async 를 모르는 코드.**
Flask/FastAPI/SQLAlchemy 를 import 하는 순간 그건 base 가 아니라 어댑터다.

라우팅은 여기서 다루지 않는다. 라우트를 데이터로 모아 어댑터가 실체화하는
중립층은 v1 이 한 번 만들었다가 되돌린 구조다(코드 2배, 프레임워크 강점 포기).
**규약을 공유하되 라우팅은 각자 프레임워크의 것을 그대로 쓴다** — 이 파일이
지키는 선이 그것이다.

담는 것:
  · env 파싱과 설정 기반(`BaseConfig`)
  · 실패 표현(`ApiError` 계열)
  · 응답 본문 모양(`{ok, data, meta?}` / `{ok:false, error}`)과 페이징(`Page`)
  · 잡 상태(`BaseJobState`)·핸들러 등록(`Registered`)
  · 도메인 선언(`BaseDomain`)
  · 스토리지 백엔드(local/S3)
  · JWT·비밀번호 해시·`User`
  · 스케줄 spec 계산, 배치 진행 문구, 지표·프로메테우스 본문, SSE 프레임, 로그 포맷
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Iterator, NamedTuple, Sequence

# ── env ───────────────────────────────────────────────────
# 설정값은 env 로 읽는다. 문서화된 env 이름은 계약이고, 파싱 방식은 여기 하나다.

TRUE_WORDS = ("1", "true", "t", "yes", "y", "on")


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_WORDS


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def env_list(name: str) -> list[str]:
    """쉼표 구분 목록. 빈 항목은 버린다."""
    return [s.strip() for s in os.environ.get(name, "").split(",") if s.strip()]


def env_set(name: str) -> set[str]:
    return set(env_list(name))


def resolve_root(root: str | None) -> str:
    """진입점의 root 인자 정규화 — 파일 경로면 그 디렉터리, 없으면 cwd."""
    if not root:
        return os.getcwd()
    root = os.path.abspath(root)
    return os.path.dirname(root) if os.path.isfile(root) else root


class BaseConfig:
    """설정 기반 — 하위 클래스는 **기본값만** 바꾼다.

    값을 클래스 정의 시점이 아니라 `load()` 시점에 읽는 이유는, 클래스 속성으로
    읽으면 하위 클래스가 기본값을 바꿀 수 없기 때문이다.

    각 패키지의 `config.py` 는 `load()` 결과를 **모듈 상수로 풀어 놓는다** —
    소비자가 보는 이름(`config.API_PORT`)이 계약이라 그 모양을 유지해야 한다.
    """

    API_PORT_DEFAULT = 8000
    SEED_DEFAULT = False
    COLLECT_DEFAULT = False
    RUN_WORKER_DEFAULT = True
    HTTP_TIMEOUT_DEFAULT = 20.0

    @classmethod
    def load(cls) -> dict[str, Any]:
        return {
            "API_HOST": env_str("APP_API_HOST", "0.0.0.0"),
            "API_PORT": env_int("APP_API_PORT", cls.API_PORT_DEFAULT),
            "CORS_ORIGINS": env_list("APP_CORS_ORIGINS"),
            "SEED_ON_START": env_flag("APP_SEED_ON_START", cls.SEED_DEFAULT),
            "COLLECT_ON_START": env_flag("APP_COLLECT_ON_START", cls.COLLECT_DEFAULT),
            "RUN_WORKER": env_flag("RUN_WORKER", cls.RUN_WORKER_DEFAULT),
            "ENABLED_DOMAINS": env_set("APP_ENABLED_DOMAINS"),
            "STATIC_DIR": env_str("APP_STATIC_DIR", ""),
            "HTTP_TIMEOUT": env_float("APP_HTTP_TIMEOUT", cls.HTTP_TIMEOUT_DEFAULT),
        }


# ── 실패 ──────────────────────────────────────────────────
# 도메인은 `raise ApiError('없음', 404)` 하나만 쓴다. 어느 판에서든 같은 문장이
# 같은 `{ok:false, error}` 로 나가도록 예외 타입을 공유한다.


class ApiError(Exception):
    """규약 실패 응답으로 변환되는 예외."""

    __slots__ = ("message", "status")

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r}, status={self.status})"


class NotFound(ApiError):
    """404 단축형 — 조회 실패가 가장 흔한 실패라서 이름을 준다."""

    def __init__(self, message: str = "대상 없음") -> None:
        super().__init__(message, 404)


class Conflict(ApiError):
    """409 — 이미 실행 중인 작업, 중복 이름 등."""

    def __init__(self, message: str = "충돌") -> None:
        super().__init__(message, 409)


class Unauthorized(ApiError):
    def __init__(self, message: str = "인증 필요") -> None:
        super().__init__(message, 401)


class Forbidden(ApiError):
    def __init__(self, message: str = "권한 없음") -> None:
        super().__init__(message, 403)


# ── 응답 본문 ─────────────────────────────────────────────
# 프론트 @sv/kit-ui 가 기대하는 모양. 직렬화는 각 프레임워크가 하고,
# **본문 dict 를 만드는 자리는 여기 하나다.**


@dataclass
class WithMeta:
    """`{ok, data, meta}` 를 만들고 싶을 때 반환한다."""

    data: Any
    meta: Any


def ok_body(data: Any = None, meta: Any = None) -> dict:
    body: dict[str, Any] = {"ok": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    return body


def error_body(message: str) -> dict:
    return {"ok": False, "error": message}


def is_wrapped(value: Any) -> bool:
    return isinstance(value, dict) and value.get("ok") is True and "data" in value


def envelope(value: Any, passthrough: tuple[type, ...] = ()) -> Any:
    """핸들러 반환값을 규약 모양으로. 이미 규약이면 손대지 않는다.

    passthrough 에는 각 프레임워크의 Response 타입을 넘긴다 — 파일·스트림
    응답을 dict 로 감싸면 안 되기 때문이고, 그 타입 이름을 base 가 알 수는 없다.
    """
    if passthrough and isinstance(value, passthrough):
        return value
    if isinstance(value, WithMeta):
        return ok_body(value.data, value.meta)
    if is_wrapped(value):
        return value
    return ok_body(value)


class Page(NamedTuple):
    """페이징 파라미터. 튜플이라 `limit, offset = page` 도 그대로 된다."""

    limit: int
    offset: int


def clamp_page(limit: int | None, offset: int | None, default_limit: int = 50,
               max_limit: int = 500) -> Page:
    """`?limit=&offset=` 정규화. 상한을 두어 화면 실수 하나가 전량 조회가 되는 일을 막는다."""
    lim = default_limit if limit is None else int(limit)
    off = 0 if offset is None else int(offset)
    return Page(min(max(lim, 1), max_limit), max(off, 0))


# ── 잡 상태 ───────────────────────────────────────────────


class BaseJobState:
    """실행 중 작업의 살아있는 상태. 핸들러가 진행을 보고하고 중지를 확인한다.

    핸들러 규약은 양쪽이 같다 — `fn(state, params)`.
    표면(`progress`·`current`·`total`·`error`·`should_stop`·`job_id`·`report()`)이
    계약이라, 큐 핸들러는 어느 판에서든 같은 문장으로 진행을 보고한다.
    """

    def __init__(self, progress: str = "시작", current: int = 0, total: int = 0,
                 error: bool = False, should_stop: bool = False,
                 job_id: int | None = None) -> None:
        self.progress = progress
        self.current = current
        self.total = total
        self.error = error
        self.should_stop = should_stop
        self.job_id = job_id

    def report(self, progress: str | None = None, current: int | None = None,
               total: int | None = None) -> None:
        """한 번에 보고하는 단축형."""
        if progress is not None:
            self.progress = progress
        if current is not None:
            self.current = current
        if total is not None:
            self.total = total

    def __repr__(self) -> str:
        return (f"{type(self).__name__}(job_id={self.job_id}, progress={self.progress!r}, "
                f"{self.current}/{self.total}, error={self.error}, stop={self.should_stop})")


@dataclass
class Registered:
    """등록된 큐 핸들러 — 함수와 레인."""

    fn: Callable
    lane: str


# ── 도메인 선언 ───────────────────────────────────────────


class BaseDomain(dict):
    """DOMAIN 선언의 클래스 형태. dict 를 상속하므로 기존 dict 선언과 섞여 돈다.

        DOMAIN = Domain(slug="catalog", title="카탈로그", bp=bp)      # svkit
        DOMAIN = Domain(slug="catalog", title="카탈로그", router=r)   # svkit2

    dict 로 쓰던 코드를 고칠 필요는 없다 — registry 는 여전히 dict 로 읽는다.
    클래스를 두는 이유는 **마운트 키 이름이 판마다 다르다**는 차이를 한 곳
    (`MOUNT_KEYS`)에 가두기 위해서다. 합칠 때 바뀌는 건 그 한 줄이다.
    """

    #: 라우터/블루프린트가 들어 있는 키 — 하위 클래스가 정한다(단수, 복수 순).
    MOUNT_KEYS: tuple[str, ...] = ()

    def __init__(self, slug: str, title: str | None = None, **fields: Any) -> None:
        super().__init__(slug=slug, title=title or slug,
                         **{k: v for k, v in fields.items() if v is not None})

    @property
    def slug(self) -> str:
        return str(self["slug"])

    @property
    def title(self) -> str:
        return str(self.get("title") or self["slug"])

    def mounts(self) -> list:
        return mounts_of(self, self.MOUNT_KEYS)


def mounts_of(domain: dict, keys: Sequence[str]) -> list:
    """DOMAIN 에서 마운트 대상을 모은다(단수 키 + 복수 키). 없으면 빈 목록.

    svkit 은 `("bp", "bps")`, svkit2 는 `("router", "routers")` 를 넘긴다.
    도메인 쪽 선언 모양(단수 하나 또는 복수 목록)은 두 판이 같다.
    """
    found: list = []
    for key in keys:
        value = domain.get(key)
        if value is None:
            continue
        found.extend(value if isinstance(value, (list, tuple)) else [value])
    return found


def domain_prefix(slug: str) -> str:
    """도메인 주소 규약 — 양쪽 모두 `/api/<slug>`."""
    return f"/api/{slug}"


# ── 스토리지 ──────────────────────────────────────────────
# 파일 이동/업로드는 어느 판에서든 같은 블로킹 I/O 다. async 판은 이 클래스를
# 스레드풀에서 호출한다 — 클래스 자체는 공유한다.


class BaseStorage:
    """저장소 백엔드 인터페이스. `save` 는 참조(경로/URI)를 반환한다."""

    def save(self, src_path: str, key: str) -> str:
        raise NotImplementedError

    def delete(self, ref: str) -> None:
        raise NotImplementedError


class BaseLocalStorage(BaseStorage):
    """로컬 디스크 저장. save 반환값 = 로컬 경로."""

    def __init__(self, root: str) -> None:
        self.root = root

    def save(self, src_path: str, key: str) -> str:
        dst = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(dst) or self.root, exist_ok=True)
        if os.path.abspath(src_path) != os.path.abspath(dst):
            shutil.move(src_path, dst)
        return dst

    def delete(self, ref: str) -> None:
        if ref and os.path.exists(ref):
            try:
                os.remove(ref)
            except OSError:
                pass


class BaseS3Storage(BaseStorage):
    """S3 호환 저장(MinIO 등). save 반환값 = `s3://bucket/key`. boto3 필요."""

    def __init__(self) -> None:
        import boto3

        self._bucket = os.environ["S3_BUCKET"]
        self._client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT") or None,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
            region_name=os.environ.get("S3_REGION", "us-east-1"))
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """버킷 없으면 생성(MinIO 자동 프로비저닝)."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except Exception:
                pass

    def save(self, src_path: str, key: str) -> str:
        self._client.upload_file(src_path, self._bucket, key)
        try:
            os.remove(src_path)
        except OSError:
            pass
        return f"s3://{self._bucket}/{key}"

    def delete(self, ref: str) -> None:
        if ref and ref.startswith("s3://"):
            _, _, rest = ref.partition("s3://")
            bucket, _, key = rest.partition("/")
            self._client.delete_object(Bucket=bucket, Key=key)


# ── 인증(토큰·비밀번호) ───────────────────────────────────
# 외부 의존성 없이 표준 라이브러리로 만든 JWT(HS256). 비밀키·TTL 은 각 패키지가
# env 로 읽어 인자로 넘긴다 — 그래야 base 가 env 이름까지 떠안지 않는다.

PBKDF_ITER = 200_000


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF_ITER)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF_ITER)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def create_token(username: str, role: str, secret: bytes, ttl: int) -> str:
    header = b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64e(json.dumps(
        {"sub": username, "role": role, "exp": int(time.time()) + ttl}).encode())
    seg = f"{header}.{payload}"
    return f"{seg}.{b64e(hmac.new(secret, seg.encode(), hashlib.sha256).digest())}"


def verify_token(token: str, secret: bytes) -> dict | None:
    """유효하면 payload, 아니면 None."""
    try:
        seg, sig = token.rsplit(".", 1)
        expected = b64e(hmac.new(secret, seg.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(b64d(seg.split(".")[1]))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except Exception:
        return None


def token_from(authorization: str = "", query_token: str = "") -> str:
    """`Authorization: Bearer <token>`, 없으면 `?token=`(SSE 등 헤더를 못 싣는 경우)."""
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return query_token or ""


@dataclass(frozen=True)
class User:
    """요청 사용자. 인증 비활성 시에는 admin 으로 취급한다."""

    sub: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @classmethod
    def from_payload(cls, payload: dict) -> "User":
        return cls(sub=str(payload.get("sub", "")), role=str(payload.get("role", "viewer")))


ANONYMOUS_ADMIN = User(sub="anonymous", role="admin")


# ── 스케줄 ────────────────────────────────────────────────


def compute_next(spec: str, now: datetime | None = None) -> float:
    """spec 에 따른 다음 실행 시각(epoch). 잘못된 spec 은 ValueError.

    spec: `daily HH:MM`(매일 지정 시각, 서버 TZ) | `interval N`(N분 간격)
    """
    now = now or datetime.now()
    parts = spec.strip().split()
    if len(parts) == 2 and parts[0] == "daily":
        hh, mm = parts[1].split(":")
        nxt = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        return nxt.timestamp()
    if len(parts) == 2 and parts[0] == "interval":
        return (now + timedelta(minutes=int(parts[1]))).timestamp()
    raise ValueError(f"지원하지 않는 spec: {spec}")


SPEC_HELP = "spec 형식: 'daily HH:MM' 또는 'interval N'"


# ── 배치 ──────────────────────────────────────────────────
# 실행(동기/async)은 각 판이 하고, **단계 순회와 진행 문구는 여기 하나다** —
# 화면에 뜨는 문장이 판마다 달라지지 않게.


def batch_stages(stages: Sequence[dict], from_stage: Any = 0) -> Iterator[tuple[int, int, dict]]:
    """`(1부터 센 단계 번호, 총 단계 수, 단계)` 를 차례로 낸다. from_stage 이전은 건너뛴다."""
    start = int(from_stage or 0)
    total = len(stages)
    for i, stage in enumerate(stages):
        if i < start:
            continue
        yield i + 1, total, stage


def batch_progress(name: str, index: int, total: int, kind: str) -> str:
    return f"[배치 {name}] {index}/{total} {kind} 시작"


def batch_stopped(name: str, index: int, total: int) -> str:
    return f"[배치 {name}] {index}/{total} 단계에서 중지"


def batch_done(name: str, total: int) -> str:
    return f"[배치 {name}] 완료 ({total}단계)"


# ── 지표 ──────────────────────────────────────────────────
# 집계 질의는 각 판의 DB 계층이 하고, **결과 dict 모양과 프로메테우스 본문은
# 여기 하나다** — 대시보드가 두 판을 같은 키로 읽는다.

JOB_STATUSES = ("queued", "running", "done", "error", "stopped")


def metrics_body(by_status: dict, by_lane: dict, done_1h: int, done_24h: int,
                 error_24h: int, retried: int, avg_duration_sec: float) -> dict:
    total_24 = done_24h + error_24h
    return {
        "by_status": {s: by_status.get(s, 0) for s in JOB_STATUSES},
        "by_lane": by_lane,
        "queue_depth": by_status.get("queued", 0),
        "running": by_status.get("running", 0),
        "done_1h": done_1h,
        "done_24h": done_24h,
        "error_24h": error_24h,
        "failure_rate_24h": round(error_24h / total_24, 3) if total_24 else 0.0,
        "avg_duration_sec_24h": round(avg_duration_sec, 1) if avg_duration_sec else 0.0,
        "retried": retried,
    }


def prometheus_text(metrics: dict) -> str:
    """Prometheus 텍스트 포맷(/metrics 스크레이프용)."""
    lines: list[str] = []

    def gauge(name: str, value: Any, help_text: str) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")

    for status, n in metrics["by_status"].items():
        lines.append(f'jobs_total{{status="{status}"}} {n}')
    for lane, d in metrics["by_lane"].items():
        lines.append(f'jobs_lane{{lane="{lane}",state="queued"}} {d["queued"]}')
        lines.append(f'jobs_lane{{lane="{lane}",state="running"}} {d["running"]}')
    gauge("jobs_queue_depth", metrics["queue_depth"], "Queued jobs")
    gauge("jobs_running", metrics["running"], "Running jobs")
    gauge("jobs_done_1h", metrics["done_1h"], "Jobs done in last hour")
    gauge("jobs_done_24h", metrics["done_24h"], "Jobs done in last 24h")
    gauge("jobs_error_24h", metrics["error_24h"], "Jobs errored in last 24h")
    gauge("jobs_failure_rate_24h", metrics["failure_rate_24h"], "Failure rate last 24h")
    gauge("jobs_avg_duration_seconds_24h", metrics["avg_duration_sec_24h"],
          "Avg job duration last 24h")
    gauge("jobs_retried_total", metrics["retried"], "Jobs retried at least once")
    return "\n".join(lines) + "\n"


# ── SSE ───────────────────────────────────────────────────

#: nginx 가 스트림을 버퍼링해 실시간성을 죽이는 것을 막는다
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
               "Connection": "keep-alive"}
SSE_PING = ": ping\n\n"


def sse_payload(value: Any) -> str:
    """스냅샷을 비교 가능한 한 줄 JSON 으로(변화 감지에 그대로 쓴다)."""
    return json.dumps(value, ensure_ascii=False, default=str)


def sse_data(payload: str) -> str:
    return f"data: {payload}\n\n"


# ── 로그 ──────────────────────────────────────────────────


def format_log(comp: str, event: str, level: str, fields: dict, json_format: bool) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if json_format:
        rec = {"ts": ts, "level": level, "comp": comp, "event": event}
        rec.update(fields)
        return json.dumps(rec, ensure_ascii=False)
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    return f"{ts} [{level}] {comp} {event} {extra}".rstrip()


__all__ = [
    # env·설정
    "TRUE_WORDS", "env_flag", "env_str", "env_int", "env_float", "env_list", "env_set",
    "resolve_root", "BaseConfig",
    # 실패
    "ApiError", "NotFound", "Conflict", "Unauthorized", "Forbidden",
    # 응답
    "WithMeta", "ok_body", "error_body", "is_wrapped", "envelope", "Page", "clamp_page",
    # 잡·도메인
    "BaseJobState", "Registered", "BaseDomain", "mounts_of", "domain_prefix",
    # 스토리지
    "BaseStorage", "BaseLocalStorage", "BaseS3Storage",
    # 인증
    "PBKDF_ITER", "b64e", "b64d", "hash_password", "verify_password",
    "create_token", "verify_token", "token_from", "User", "ANONYMOUS_ADMIN",
    # 스케줄·배치
    "compute_next", "SPEC_HELP",
    "batch_stages", "batch_progress", "batch_stopped", "batch_done",
    # 지표·SSE·로그
    "JOB_STATUSES", "metrics_body", "prometheus_text",
    "SSE_HEADERS", "SSE_PING", "sse_payload", "sse_data", "format_log",
]