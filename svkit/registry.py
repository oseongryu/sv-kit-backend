"""도메인 레지스트리 — domains/<slug>/ 를 자동 탐색해 단일 Flask 앱에 통합.

각 도메인 패키지(domains/<slug>/__init__.py)는 모듈 전역 `DOMAIN` dict 를 노출한다:
    DOMAIN = {
        "slug":   "<slug>",              # URL/테이블 접두 규약
        "title":  "표시명",
        "bp":     <flask.Blueprint>,     # url_prefix=/api/<slug>
        "bps":    [<Blueprint>, ...],    # 파일을 나눠 쓸 때(선택)
        "schema": "<CREATE TABLE ...>",  # 멱등 스키마 SQL (선택)
        "seed":   callable(conn) | None, # 샘플 데이터 시드 (선택)
        "collect":callable() | None,     # 실외부 수집 1회 (선택)
        "migrate":callable(conn) | None, # 스키마 생성 전 훅 (선택)
        "schedules"/"retire_schedules":  # 기본 스케줄 (선택)
    }

`Domain` 클래스로 선언해도 되고(dict 상속이라 완전히 호환), 기존 dict 를
그대로 둬도 된다. 키 이름·의미·호출 순서는 계약이다.

'_' 로 시작하는 디렉토리(_template 등)는 건너뛴다.
아직 DOMAIN 이 없거나 import 되지 않는 도메인은 경고 후 스킵(부분 기동 허용).
"""
import importlib
import logging
import pkgutil

from svkit import config
from svkit.base import BaseDomain, mounts_of

log = logging.getLogger("svkit.registry")

DOMAINS = []


class Domain(BaseDomain):
    """Flask 판 도메인 선언 — 마운트 대상은 `bp`(단수) / `bps`(복수).

        DOMAIN = Domain(slug="hello", title="헬로", bp=bp, schema=SCHEMA, seed=seed)

    svkit2 의 Domain 과 다른 것은 `MOUNT_KEYS` 한 줄뿐이다.
    """

    MOUNT_KEYS = ("bp", "bps")


def bps_of(domain):
    """DOMAIN 에서 blueprint 를 모은다(단수 `bp` + 복수 `bps`)."""
    return mounts_of(domain, Domain.MOUNT_KEYS)


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
    allow = (config.ENABLED_DOMAINS or None) or _enabled_filter()
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


def register(app) -> None:
    """탐색한 도메인의 blueprint 를 앱에 마운트한다(svkit2 와 같은 이름·역할)."""
    for dom in DOMAINS:
        bps = bps_of(dom)
        if not bps:
            log.warning("domain %s has no blueprint — skipping", dom.get("slug"))
            continue
        for bp in bps:
            app.register_blueprint(bp)
        log.info("registered domain: %-16s -> %s", dom["slug"],
                 bps[0].url_prefix or "(라우트 절대경로)")
    log.info("domains %d: %s", len(DOMAINS), ", ".join(d["slug"] for d in DOMAINS))


__all__ = ["DOMAINS", "Domain", "load_domains", "register", "bps_of", "mounts_of"]