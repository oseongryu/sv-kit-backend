"""svkit 앱 팩토리 — 도메인 레지스트리 기반 Flask 앱 생성.

호출 프로젝트(생성물 backend/)는 이것만 쓴다:

    from svkit import create_app
    app = create_app(__file__)          # 프로젝트 루트 = app.py 가 있는 디렉토리

    if __name__ == "__main__":
        from svkit import run
        run(app)

create_app 이 하는 일 (기존 스켈레톤 backend/app.py 를 그대로 흡수):
1. 프로젝트 루트를 sys.path 에 추가 → top-level `domains` 패키지 탐색 가능
2. registry.load_domains() — domains/<slug>/ 자동 등록
3. 스키마 초기화(migrate 훅 → 도메인 schema → 공통 인프라 schema)
4. blueprint 마운트 (auth/queue/scheduler 공통 + 도메인)
5. 시드/수집(env 옵션) + 인프로세스 워커/스케줄러(RUN_WORKER)
6. 메타 라우트: /api/health · /api/domains · /metrics · /api/backup · /

**인자는 svkit2 의 create_app 과 맞춰 뒀다** — `title`·`infra`·
`expose_error_detail`·`root_route`. 인자 기본값도 같다(특히 `infra=True`).
그래서 두 판 사이에서 `app.py` 는 import 줄 말고는 고칠 것이 없다.
"""
import logging
import os
import sys

from flask import Flask, Response, jsonify
from flask_cors import CORS

from svkit.base import resolve_root as _resolve_root

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("svkit.app")


def create_app(root: str | None = None, title: str = "svkit", infra: bool = True,
               expose_error_detail: bool = False, root_route: bool = True,
               wrap_http_errors: bool = False) -> Flask:
    """프로젝트 루트(`domains/` 가 있는 디렉토리)에서 Flask 앱을 조립한다.

    root 에는 관례상 `__file__` 을 넘긴다 (파일 경로면 부모 디렉토리 사용).

    infra=False 는 **DB·잡을 프로젝트가 이미 관리하는 경우**를 위한 것이다.
    큐·스케줄러 blueprint 를 얹지 않고, 워커도 띄우지 않고, 스키마도 만들지
    않는다. 남는 것은 라우팅 규약(`/api/<slug>`·`{ok,data}`)과 도메인 레지스트리
    · 메타 라우트뿐이다. 이미 자기 잡 테이블이 있는 프로젝트에 `queue_job` 을
    새로 만들어 주는 것은 도움이 아니라 침범이라 기본값이 아니라 선택으로 뒀다.

    root_route=False 는 프로젝트가 `/` 를 직접 쓰는 경우(리다이렉트·자체 화면).
    wrap_http_errors 는 이 판에만 있는 인자다 — 설명은 response 모듈 참조.
    """
    root = _resolve_root(root)
    if root not in sys.path:
        sys.path.insert(0, root)

    from svkit import auth, config, db, queue, registry, scheduler
    from svkit.response import install_error_handlers

    registry.load_domains()

    app = Flask(title)
    app.config["JSON_AS_ASCII"] = False  # 한글 응답
    app.config["SVKIT_TITLE"] = title
    app.config["SVKIT_INFRA"] = infra

    CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}})
    install_error_handlers(app, expose_detail=expose_error_detail,
                           wrap_http_errors=wrap_http_errors)

    # 1) 스키마 초기화 (멱등: 마이그레이션 훅 → 도메인/공통 스키마)
    if infra:
        db.init_all()
        if auth.AUTH_ENABLED:
            auth.seed_users()

    # 2) blueprint 등록 (공통: auth/queue/schedule + 도메인)
    # auth 는 활성일 때만 마운트 — 비활성 앱이 자체 /api/auth/* 를 정의할 수 있게
    if auth.AUTH_ENABLED and infra:
        app.register_blueprint(auth.bp)
    if infra:
        app.register_blueprint(queue.bp)
        app.register_blueprint(scheduler.bp)
    registry.register(app)

    # 3) 시드 / 수집
    if infra and config.SEED_ON_START:
        _run_seeds()
    if infra and config.COLLECT_ON_START:
        _run_collectors()

    # 4) 인프로세스 워커+스케줄러(개발/단일 컨테이너; 전용 워커 분리 시 RUN_WORKER=false)
    if infra and config.RUN_WORKER:
        queue.start_worker_thread()
        scheduler.start_thread()

    _register_meta_routes(app, title=title, infra=infra, root_route=root_route)
    return app


def run(app: Flask) -> None:
    """개발 실행 헬퍼 — config 의 호스트/포트로 기동."""
    from svkit import config
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False)


def _run_seeds() -> None:
    from svkit import db, registry
    for dom in registry.DOMAINS:
        seed = dom.get("seed")
        if not callable(seed):
            continue
        try:
            with db.get_conn() as conn:
                seed(conn)
            log.info("seeded: %s", dom["slug"])
        except Exception as e:  # 시드는 데모 편의 — 개별 실패가 부팅을 막지 않게
            log.warning("seed failed for %s: %s", dom["slug"], e)


def _run_collectors() -> None:
    from svkit import registry
    for dom in registry.DOMAINS:
        collect = dom.get("collect")
        if not callable(collect):
            continue
        try:
            collect()
            log.info("collected: %s", dom["slug"])
        except Exception as e:  # 외부 소스 경계 — 방어적 허용
            log.warning("collect failed for %s: %s", dom["slug"], e)


def _register_meta_routes(app: Flask, title: str = "svkit", infra: bool = True,
                          root_route: bool = True) -> None:
    from svkit import auth, config, db, queue, registry
    from svkit.base import domain_prefix
    from svkit.response import ok

    @app.get("/api/health")
    def health():
        return ok({"status": "up", "backend": db.backend(),
                   "domains": [d["slug"] for d in registry.DOMAINS]})

    @app.get("/api/domains")
    def domains():
        def prefix_of(dom):
            # 도메인이 서브 blueprint 를 쓰는 경우에도 주소 규약은 /api/<slug> 다
            bps = registry.bps_of(dom)
            if bps and getattr(bps[0], "url_prefix", ""):
                return bps[0].url_prefix
            return domain_prefix(dom["slug"])

        return ok([
            {"slug": d["slug"], "title": d.get("title", d["slug"]), "prefix": prefix_of(d)}
            for d in registry.DOMAINS
        ])

    # /metrics·/api/backup 은 인프라(큐·DB)를 전제한다 — infra=False 면 얹지 않는다
    if infra:
        @app.get("/metrics")
        def prometheus_metrics():
            return Response(queue.prometheus_text(), mimetype="text/plain; version=0.0.4")

        @app.post("/api/backup")
        @auth.require_admin
        def backup():
            try:
                return ok({"message": "백업 완료", "path": db.backup()})
            except Exception as e:  # 백업 실패는 사용자에게 사유 전달
                from svkit.response import err
                return err(f"백업 실패: {e}", 500)

    static_dir = config.STATIC_DIR or os.environ.get("APP_STATIC_DIR")
    if static_dir:
        _register_spa_routes(app, static_dir)
    elif root_route:
        # 프로젝트가 `/` 를 직접 쓰는 경우(리다이렉트·자체 화면)에는 root_route=False.
        @app.get("/")
        def root():
            return jsonify({"service": title,
                            "domains": len(registry.DOMAINS),
                            "health": "/api/health"})


def _register_spa_routes(app: Flask, static_dir: str) -> None:
    """APP_STATIC_DIR — 정적 SPA(Next static export 등) 서빙.

    1. {dir}/{path} 파일이 있으면 그대로 (해시 파일명 _next/static/ 은 장기 캐시)
    2. {dir}/{path}/index.html 있으면 서빙 (trailingSlash 페이지)
    3. 없으면 index.html 반환 (SPA fallback)
    """
    from flask import send_from_directory

    root_dir = os.path.abspath(static_dir)
    if not os.path.isdir(root_dir):
        raise RuntimeError(f"APP_STATIC_DIR 디렉토리 없음: {root_dir}")

    def _no_cache(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/")
    def spa_index():
        return _no_cache(send_from_directory(root_dir, "index.html"))

    @app.get("/<path:path>")
    def spa_proxy(path: str):
        direct = os.path.join(root_dir, path)
        if os.path.isfile(direct):
            if path.startswith("_next/static/"):
                return send_from_directory(root_dir, path)
            return _no_cache(send_from_directory(root_dir, path))
        page_dir = os.path.join(root_dir, path)
        if os.path.isfile(os.path.join(page_dir, "index.html")):
            return _no_cache(send_from_directory(page_dir, "index.html"))
        return _no_cache(send_from_directory(root_dir, "index.html"))
