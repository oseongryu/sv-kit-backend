"""웹 커널 — 앱 조립·도메인 레지스트리·내장 인증.

  - `DOMAINS`·`load_domains()`·`routers_of()` — env `APP_DOMAIN_PACKAGES` 의 패키지에서
    `DOMAIN` dict 를 모으는 레지스트리 (없는 항목은 공용 라이브러리로 건너뛴다)
  - 해시(pbkdf2$salt$dk)·토큰(HS256 JWT) — **형식 불변이라 기존 DB 의 해시가 그대로 검증된다**
  - 내장 인증 — `AUTH_ENABLED=true` 일 때만. 계정 도메인이 없는 배포용
  - `create_app()` — CORS·에러 핸들러·도메인 migrate·라우터 등록·메타 라우트·SPA 서빙

env 는 함수 안에서 읽는다 — env 가 깔리기 전에 이 모듈이 import 돼도 계약이
어긋나지 않게 하기 위함이다.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from svkit.web.errors import ApiError
from svkit.infra.logger import get_logger
from svkit.web.middleware import CasingMiddleware
from svkit.web.reqctx import RequestContextMiddleware
from svkit.web.lifecycle import add_lifespan, domain_lifespan
from svkit.web.response import install_error_handlers
# 호출부 계약 유지를 위한 재수출.
from svkit.web.security import (  # noqa: F401
    PBKDF_ITER, create_token, hash_password, verify_password, verify_token,
)
from svkit.loader import conf

log = get_logger(__name__)


def auth_enabled() -> bool:
    return conf.get_bool("AUTH_ENABLED")


def _extract_token(request: Request, token: str = "") -> str:
    """Authorization: Bearer → 쿼리 `?token=` 순.

    쿼리 폴백은 브라우저 WebSocket 이 헤더를 못 실어서 있는 경로다.
    """
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return token


def _guard(admin_only: bool):
    def dependency(request: Request, token: str = Query("")) -> dict | None:
        if not auth_enabled():
            return None
        payload = verify_token(_extract_token(request, token))
        if not payload:
            raise ApiError("인증 필요", 401)
        if admin_only and payload.get("role") != "admin":
            raise ApiError("권한 없음", 403)
        request.state.user = payload
        return payload

    return dependency


require_auth = Depends(_guard(False))
require_admin = Depends(_guard(True))


def current_user(request: Request) -> dict | None:
    """가드가 실어 둔 인증 주체. 가드를 안 건 경로에서는 None."""
    return getattr(request.state, "user", None)


AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'viewer',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def seed_users() -> None:
    """auth_user 가 비면 env(ADMIN_USER/ADMIN_PASSWORD 등)로 초기 계정 시드."""
    from svkit import db

    with db.get_conn() as conn:
        conn.executescript(AUTH_SCHEMA)
        n = conn.execute("SELECT COUNT(*) FROM auth_user").fetchone()[0]
        if n:
            return
        for user_env, pw_env, role in (("ADMIN_USER", "ADMIN_PASSWORD", "admin"),
                                       ("VIEWER_USER", "VIEWER_PASSWORD", "viewer")):
            u, p = os.environ.get(user_env), os.environ.get(pw_env)
            if u and p:
                conn.execute(
                    "INSERT INTO auth_user (username, password_hash, role) VALUES (?,?,?)",
                    (u, hash_password(p), role))
                log.info("계정 시드: %s(%s)", u, role)


# 모듈 스코프여야 한다 — `from __future__ import annotations` 아래에서 함수 안 클래스로
# 두면 FastAPI 가 문자열 어노테이션을 못 풀어 body 를 쿼리 파라미터로 오인한다(422).
from pydantic import BaseModel as _BaseModel


class LoginIn(_BaseModel):
    username: str = ""
    password: str = ""


class DeviceIn(_BaseModel):
    device_id: str = ""
    secret: str = ""


def _auth_router():
    from svkit.web.api import make_router
    from svkit import db

    router = make_router("auth")

    @router.post("/login")
    def login(body: LoginIn):
        # 구성 오류는 여기서 한 번만 말한다 — 게이트는 401 로 리다이렉트 동선만 지킨다.
        if not conf.get_str("JWT_SECRET").strip():
            raise ApiError("JWT_SECRET 미설정 — 서버 설정(config/local.yml)을 채우고 재기동하라", 503)
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT username, password_hash, role FROM auth_user WHERE username=?",
                (body.username,)).fetchone()
        if not row or not verify_password(body.password, row["password_hash"]):
            raise ApiError("아이디 또는 비밀번호가 올바르지 않다", 401)
        return {"token": create_token(row["username"], row["role"]),
                "username": row["username"], "role": row["role"]}

    @router.get("/me")
    def me(request: Request, token: str = Query("")):
        payload = verify_token(_extract_token(request, token))
        if not payload:
            return {"auth": False}
        return {"auth": True, "username": payload.get("sub"),
                "role": payload.get("role")}

    @router.post("/device")
    def device_issue(body: DeviceIn, request: Request):
        """앱 최초 실행용 토큰 발급 — 공유 시크릿을 제시해야 한다.

        지문의 클라이언트 값은 `X-App-Client` 를 먼저 보고 없으면 UA 로 떨어진다.
        앱은 그 헤더에 **고정 문자열**을 보낸다 — UA 는 OS 가 좌우해 업데이트 한 번에
        전 사용자가 지문 불일치로 걸린다.
        """
        from svkit.web import device as dev

        client = dev.client_id(request.headers.get(dev.CLIENT_HEADER, ""),
                               request.headers.get("User-Agent", ""))
        token, device_id = dev.issue(body.device_id, client, body.secret)
        return {"token": token, "device_id": device_id, "role": dev.ROLE_APP}

    return router


DOMAINS: list = []


def routers_of(dom) -> list:
    """도메인이 노출하는 라우터들. 단수 키(`router`)도 받는다."""
    routers = list(dom.get("routers") or [])
    one = dom.get("router")
    if one is not None and one not in routers:
        routers.append(one)
    return routers


def load_domains() -> list:
    """env `APP_DOMAIN_PACKAGES` 의 패키지에서 DOMAIN 을 모은다 (멱등)."""
    if DOMAINS:
        return DOMAINS
    names = [n for n in os.environ.get("APP_DOMAIN_PACKAGES", "").split(",") if n]
    for name in names:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name == name:
                log.warning("도메인 패키지 없음, 건너뜀: %s", name)
                continue
            raise
        dom = getattr(mod, "DOMAIN", None)
        if dom is None:
            continue  # 공용 라이브러리
        DOMAINS.append(dom)
    DOMAINS.sort(key=lambda d: d.get("slug") or "")
    return DOMAINS


def _owns_root(doms) -> bool:
    """도메인 중 하나가 이미 `/` 를 서빙하는가.

    이미 서빙하면 커널 폴백을 걸지 않는다 — 겹치면 등록 순서에만 기대는 상태가 된다.
    """
    for dom in doms:
        for router in routers_of(dom):
            prefix = getattr(router, "prefix", "") or ""
            for route in getattr(router, "routes", []):
                if prefix + (getattr(route, "path", "") or "") == "/":
                    return True
    return False


def create_app(title: str = "svkit",
               expose_error_detail: bool = True, static: bool = True) -> FastAPI:
    """env `APP_DOMAIN_PACKAGES` 에서 도메인을 발견해 앱을 조립한다.

    `expose_error_detail=False` 면 500 응답이 예외 상세를 감춘다 — 인터넷에 직접 노출되는
    배포(auth)가 쓰던 갈래다.
    """
    return create_service_app(title, None, expose_error_detail=expose_error_detail,
                              static=static)


def create_service_app(title: str = "svkit", domains: list | None = None, *,
                       expose_error_detail: bool = True,
                       static: bool = True) -> FastAPI:
    """도메인 등록·스키마 초기화·SPA 서빙까지.

    `domains` 를 주면 그 목록을 그대로 싣고, 생략하면 env 에서 발견한다(=`create_app`).
    `static=False` 는 SPA·루트 폴백 등록을 건너뛴다 — 라우트를 더 얹은 뒤 edition 이
    직접 catch-all 을 맨 마지막에 달아야 하는 배포용 (등록 순서가 곧 매칭 순서다).
    """
    from svkit import db

    doms = load_domains() if domains is None else list(domains)

    app = FastAPI(title=title)

    app.add_middleware(RequestContextMiddleware)
    # 도메인이 `camel_api` 로 선언한 경로에서만 동작한다 (선언 없으면 통과).
    app.add_middleware(CasingMiddleware)

    # CORS 전체 허용 — 인증이 쿠키가 아니라 Authorization 헤더라 credentials 가 불필요하다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    install_error_handlers(app, expose_detail=expose_error_detail)

    # 도메인이 선언한 기동/정리 훅 (module_<x>/service_lifecycle.py)
    add_lifespan(app, domain_lifespan)

    # 스키마 초기화 — 도메인 migrate 훅 (멱등). **도메인마다 커넥션을 새로 연다** —
    # 하나로 전부 돌리면 미커밋 쓰기가 잠금을 쥔 채 다음 도메인으로 넘어간다.
    for dom in doms:
        migrate = dom.get("migrate")
        if callable(migrate):
            with db.get_conn() as conn:
                migrate(conn)

    if auth_enabled():
        from svkit.web import device

        seed_users()
        device.ensure_schema()
        app.include_router(_auth_router())

    for dom in doms:
        routers = routers_of(dom)
        if not routers:
            log.warning("라우터 없는 도메인 건너뜀: %s", dom.get("slug"))
            continue
        for router in routers:
            app.include_router(router)
        log.info("도메인 등록: %-12s -> %s", dom["slug"],
                 routers[0].prefix or "(라우트 절대경로)")

    @app.get("/api/health")
    def health():
        return {"ok": True, "data": {"status": "up",
                                     "domains": [d["slug"] for d in doms]}}

    @app.get("/api/domains")
    def list_domains():
        return {"ok": True, "data": [
            {"slug": d["slug"], "title": d.get("title", d["slug"]),
             "prefix": (routers_of(d)[0].prefix if routers_of(d) else None)
                       or f"/api/{d['slug']}"}
            for d in doms]}

    if static:
        static_dir = os.environ.get("APP_STATIC_DIR")
        if static_dir and os.path.isdir(static_dir):
            _register_spa_routes(app, static_dir)
        elif not _owns_root(doms):
            @app.get("/")
            def root():
                return {"ok": True, "data": {"service": title}}

    return app


def _register_spa_routes(app: FastAPI, static_dir: str) -> None:
    """APP_STATIC_DIR 의 정적 SPA 서빙 — 파일이 있으면 그대로, 없으면 index.html.

    catch-all 이라 **맨 마지막에 등록해야** 한다 (FastAPI 는 등록 순서로 매칭한다).
    `/api/*` 는 여기서 404 로 끊는다 — 안 그러면 없는 API 가 index.html 을 200 으로
    돌려주고, 프론트는 JSON 파싱 실패라는 엉뚱한 증상만 본다.
    """
    from fastapi.responses import FileResponse

    root_dir = Path(static_dir).resolve()

    def _resolve(rel: str) -> Path | None:
        """root_dir 안의 실제 파일만 돌려준다 (`..` 탈출 차단)."""
        try:
            target = (root_dir / rel).resolve()
        except (OSError, ValueError):
            return None
        if not target.is_relative_to(root_dir):
            return None
        return target if target.is_file() else None

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str = ""):
        if path.startswith("api/"):
            raise ApiError("없는 경로", 404)
        hit = _resolve(path or "index.html") or _resolve(f"{path}.html")
        if hit:
            return FileResponse(hit)
        index = _resolve("index.html")
        if not index:
            raise ApiError("정적 산출물이 없다", 404)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
