"""정적 SPA(Next static export) 서빙.

`frontend/` 빌드 산출물(`backend/views`)을 백엔드와 같은 오리진에서 서빙한다.
catch-all(`/{path:path}`)을 붙이므로 **반드시 맨 마지막**이다 — 먼저 등록되면
그 뒤에 추가되는 디버그 뷰어·health 라우트가 전부 가려진다. 그래서 edition 의
create_app 맨 마지막에 이걸 부른다.

산출물이 없으면 아무것도 하지 않는다 — 프론트를 빌드하지 않아도 API 는 뜬다.
"""

import logging
import os

log = logging.getLogger(__name__)


def mount_spa(app, static_dir: str) -> bool:
    """정적 SPA 를 마운트한다. 산출물이 없으면 False 를 반환하고 넘어간다.

    1. `{dir}/{path}` 파일이 있으면 그대로
    2. `{dir}/{path}/index.html` 이 있으면 서빙 (trailingSlash 페이지)
    3. 없으면 index.html (SPA 폴백)
    """
    from fastapi.responses import FileResponse, JSONResponse
    from starlette.staticfiles import StaticFiles

    root_dir = os.path.abspath(static_dir)
    index = os.path.join(root_dir, 'index.html')
    if not os.path.isfile(index):
        log.info('대시보드 미빌드 — 정적 서빙 생략')
        return False

    no_cache = {'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache', 'Expires': '0'}
    _notfound = os.path.join(root_dir, '404.html')

    # 해시 파일명이라 장기 캐시가 안전
    assets = os.path.join(root_dir, '_next', 'static')
    if os.path.isdir(assets):
        app.mount('/_next/static', StaticFiles(directory=assets), name='next-static')

    @app.get('/', include_in_schema=False)
    async def spa_index():
        return FileResponse(index, headers=no_cache)

    @app.get('/{path:path}', include_in_schema=False)
    async def spa_proxy(path: str):
        # API 는 SPA 폴백 대상이 아니다. 없는 API·잘못된 메서드를 대시보드 HTML 로 답하면
        # 호출부가 200 을 받고 JSON 파싱에서야 깨져서 원인을 찾기 어렵다.
        # (POST API 는 애초에 여기 오지 않는다 — catch-all 은 GET 만 등록한다)
        if path.startswith('api/'):
            return JSONResponse({'ok': False, 'error': 'Not Found'}, status_code=404)
        direct = os.path.join(root_dir, path)
        if os.path.isfile(direct):
            return FileResponse(direct, headers=no_cache)
        page = os.path.join(direct, 'index.html')
        if os.path.isfile(page):
            return FileResponse(page, headers=no_cache)
        # index.html 로 폴백하지 않는다. static export 는 모든 페이지가 실제 파일이라
        # 클라이언트 라우팅 폴백이 필요 없고, 폴백을 두면 **POST 전용 API 를 GET 으로 부른
        # 경우까지 200 + HTML** 이 되어 호출부가 실패를 성공으로 오해한다(catch-all 이
        # 405 를 흡수한다). 없는 경로는 없다고 답한다.
        if os.path.isfile(_notfound):
            return FileResponse(_notfound, status_code=404, headers=no_cache)
        return JSONResponse({'ok': False, 'error': 'Not Found'}, status_code=404)

    log.info('대시보드 서빙: %s', root_dir)
    return True
