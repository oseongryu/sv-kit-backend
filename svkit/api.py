"""API 공통 포맷 — 모든 도메인 `api/` 계층이 공유하는 서빙 헬퍼.

응답 규약(ok/err)은 common.response 를, blueprint/페이징은 이 모듈을 쓴다.

- make_blueprint: `/api/<slug>` prefix blueprint 를 생성 (라우트는 상대경로로 선언)
- page_args:      ?limit=&offset= 파싱 (상한 가드 포함)
"""
from flask import Blueprint, request


def make_blueprint(slug: str) -> Blueprint:
    """`/api/<slug>` prefix 를 가진 blueprint 생성.

    이후 라우트는 `@bp.get("/items")` 처럼 상대경로로 선언한다.
    """
    return Blueprint(slug, __name__, url_prefix=f"/api/{slug}")


def page_args(default_limit: int = 50, max_limit: int = 500):
    """페이징 파라미터 파싱. 반환: (limit, offset). limit 은 max_limit 로 상한."""
    limit = request.args.get("limit", default=default_limit, type=int)
    offset = request.args.get("offset", default=0, type=int)
    limit = min(max(limit, 1), max_limit)
    offset = max(offset, 0)
    return limit, offset
