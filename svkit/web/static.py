"""정적 SPA(Next static export) 서빙 — 커널의 단일 구현.

프론트 빌드 산출물을 백엔드와 같은 오리진에서 서빙한다. catch-all(`/{path:path}`)을
붙이므로 **반드시 맨 마지막**이다 — 먼저 등록되면 그 뒤에 추가되는 디버그 뷰어·health
라우트가 전부 가려진다.

산출물이 없으면 아무것도 하지 않는다 — 프론트를 빌드하지 않아도 API 는 뜬다.
"""

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def mount_spa(app, static_dir: str) -> bool:
    """정적 SPA 를 마운트한다. index.html 이 없으면 False 를 돌려주고 아무것도 안 한다.

    경로 해석 순서 — `{dir}/{path}` 실제 파일 → `{dir}/{path}.html`(trailingSlash 를 끈
    계보) → `{dir}/{path}/index.html`(trailingSlash 계보). 셋 다 없으면 404 다:
    static export 는 모든 라우트가 실제 파일이라 index 로 폴백할 경로가 없고, 폴백을 두면
    GET 으로 부른 POST 전용 API 까지 200 + HTML 이 되어 호출부가 실패를 성공으로 읽는다.
    """
    from fastapi.responses import FileResponse
    from starlette.staticfiles import StaticFiles

    from svkit.web.errors import ApiError

    root_dir = Path(static_dir).resolve()
    if not (root_dir / 'index.html').is_file():
        log.info('대시보드 미빌드 — 정적 서빙 생략')
        return False

    no_cache = {'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache', 'Expires': '0'}

    def resolve(rel: str):
        """root_dir 안의 실제 파일만 돌려준다 (`..` 탈출 차단)."""
        try:
            target = (root_dir / rel).resolve()
        except (OSError, ValueError):
            return None
        if not target.is_relative_to(root_dir):
            return None
        return target if target.is_file() else None

    # 해시 파일명이라 장기 캐시가 안전
    assets = root_dir / '_next' / 'static'
    if assets.is_dir():
        app.mount('/_next/static', StaticFiles(directory=str(assets)), name='next-static')

    @app.get('/{path:path}', include_in_schema=False)
    def spa(path: str = ''):
        # API 는 SPA 대상이 아니다. 없는 API 를 HTML 로 답하면 호출부가 200 을 받고
        # JSON 파싱에서야 깨져서 원인을 찾기 어렵다.
        if path.startswith('api/'):
            raise ApiError('없는 경로', 404)
        rel = path.strip('/')
        hit = (resolve(rel or 'index.html') or resolve(f'{rel}.html')
               or resolve(f'{rel}/index.html' if rel else 'index.html'))
        if hit:
            return FileResponse(hit, headers=no_cache)
        notfound = resolve('404.html')
        if notfound:
            return FileResponse(notfound, status_code=404, headers=no_cache)
        raise ApiError('없는 경로', 404)

    log.info('대시보드 서빙: %s', root_dir)
    return True
