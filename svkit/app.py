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
"""
import logging
import os
import sys

from flask import Flask, Response, jsonify
from flask_cors import CORS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("svkit.app")


def _resolve_root(root: str | None) -> str:
    """root 인자 정규화 — 파일 경로면 그 디렉토리, 없으면 cwd."""
    if not root:
        return os.getcwd()
    root = os.path.abspath(root)
    if os.path.isfile(root):
        return os.path.dirname(root)
    return root


def create_app(root: str | None = None) -> Flask:
    """프로젝트 루트(`domains/` 가 있는 디렉토리)에서 Flask 앱을 조립한다.

    root 에는 관례상 `__file__` 을 넘긴다 (파일 경로면 부모 디렉토리 사용).
    """
    root = _resolve_root(root)
    if root not in sys.path:
        sys.path.insert(0, root)

    from svkit import auth, config, db, queue, registry, scheduler

    registry.load_domains()

    app = Flask("svkit")
    app.config["JSON_AS_ASCII"] = False  # 한글 응답

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # 1) 스키마 초기화 (멱등: 마이그레이션 훅 → 도메인/공통 스키마)
    db.init_all()
    if auth.AUTH_ENABLED:
        auth.seed_users()

    # 2) blueprint 등록 (공통: auth/queue/schedule + 도메인)
    # auth 는 활성일 때만 마운트 — 비활성 앱이 자체 /api/auth/* 를 정의할 수 있게
    if auth.AUTH_ENABLED:
        app.register_blueprint(auth.bp)
    app.register_blueprint(queue.bp)
    app.register_blueprint(scheduler.bp)
    for dom in registry.DOMAINS:
        # 단일 "bp" 또는 복수 "bps" (기존 앱의 라우트 파일별 bp 를 그대로 수용)
        bps = [b for b in [dom.get("bp"), *(dom.get("bps") or [])] if b is not None]
        for bp in bps:
            app.register_blueprint(bp)
            log.info("registered domain: %-16s -> %s", dom["slug"],
                     bp.url_prefix or "(라우트 절대경로)")

    # 3) 시드 / 수집
    if config.SEED_ON_START:
        _run_seeds()
    if config.COLLECT_ON_START:
        _run_collectors()

    # 4) 인프로세스 워커+스케줄러(개발/단일 컨테이너; 전용 워커 분리 시 RUN_WORKER=false)
    if config.RUN_WORKER:
        queue.start_worker_thread()
        scheduler.start_thread()

    _register_meta_routes(app)
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


def _register_meta_routes(app: Flask) -> None:
    from svkit import auth, db, queue, registry
    from svkit.response import ok

    @app.get("/api/health")
    def health():
        return ok({"status": "up", "domains": [d["slug"] for d in registry.DOMAINS]})

    @app.get("/api/domains")
    def domains():
        return ok([
            {"slug": d["slug"], "title": d.get("title", d["slug"]),
             "prefix": d["bp"].url_prefix if d.get("bp") else None}
            for d in registry.DOMAINS
        ])

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

    static_dir = os.environ.get("APP_STATIC_DIR")
    if static_dir:
        _register_spa_routes(app, static_dir)
    else:
        @app.get("/")
        def root():
            return jsonify({"service": "integrated platform",
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
