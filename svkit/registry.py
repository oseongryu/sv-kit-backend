"""도메인 레지스트리 — domains/<slug>/ 를 자동 탐색해 단일 Flask 앱에 통합.

각 도메인 패키지(domains/<slug>/__init__.py)는 모듈 전역 `DOMAIN` dict 를 노출한다:
    DOMAIN = {
        "slug":   "<slug>",              # URL/테이블 접두 규약
        "title":  "표시명",
        "bp":     <flask.Blueprint>,     # url_prefix=/api/<slug>
        "schema": "<CREATE TABLE ...>",  # 멱등 스키마 SQL (선택)
        "seed":   callable(conn) | None, # 샘플 데이터 시드 (선택)
        "collect":callable() | None,     # 실외부 수집 1회 (선택)
    }

'_' 로 시작하는 디렉토리(_template 등)는 건너뛴다.
아직 DOMAIN 이 없거나 import 되지 않는 도메인은 경고 후 스킵(부분 기동 허용).
"""
import importlib
import logging
import pkgutil

log = logging.getLogger("app.registry")

DOMAINS = []


def _enabled_filter():
    """APP_ENABLED_DOMAINS env(쉼표 구분) — 설정 시 그 도메인만 로드. 미설정=전부."""
    import os
    raw = os.environ.get("APP_ENABLED_DOMAINS", "").strip()
    if not raw:
        return None
    return {s.strip() for s in raw.split(",") if s.strip()}


def _iter_slugs():
    """domains/ 아래 '_' 로 시작하지 않는 하위 패키지 slug 를 나열."""
    # 지연 import — create_app(root) 가 프로젝트 루트를 sys.path 에 넣은 뒤에야
    # 호출 프로젝트의 top-level `domains` 패키지를 찾을 수 있다 (svkit 은
    # site-packages 에 있으므로 상대 탐색이 불가능).
    import domains as _domains_pkg
    allow = _enabled_filter()
    for m in pkgutil.iter_modules(_domains_pkg.__path__):
        if m.ispkg and not m.name.startswith("_"):
            if allow is not None and m.name not in allow:
                log.info("domain disabled by APP_ENABLED_DOMAINS: %s", m.name)
                continue
            yield m.name


def load_domains():
    """모든 도메인 모듈을 import 하여 DOMAINS 를 채운다."""
    DOMAINS.clear()
    for slug in sorted(_iter_slugs()):
        try:
            mod = importlib.import_module(f"domains.{slug}")
        except ModuleNotFoundError as e:
            # 도메인 내부의 실제 의존성 누락은 감추지 않는다
            if e.name in (f"domains.{slug}", "domains"):
                log.warning("domain not importable, skipping: %s", slug)
                continue
            raise
        dom = getattr(mod, "DOMAIN", None)
        if dom is None:
            log.error("domains.%s has no DOMAIN dict — skipping", slug)
            continue
        DOMAINS.append(dom)
    return DOMAINS

