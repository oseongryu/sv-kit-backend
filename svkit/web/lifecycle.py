"""도메인 수명주기 훅 — 기동/정리를 도메인이 선언하고 커널이 돌린다.

각 도메인은 `module_<패키지>/service_lifecycle.py` 를 선택적으로 두고
`on_startup()` · `on_shutdown()` 중 필요한 것만 정의한다 (동기·비동기 모두 가능).

계약:
- 기동 훅이 실패해도 앱은 뜬다 — 크롤 인덱스 같은 부가 준비 때문에 서비스 전체가
  죽으면 안 된다. 대신 경고 로그를 남긴다(조용히 삼키지 않는다).
- 정리 훅은 등록 역순으로 돈다. 실패해도 나머지 정리는 계속한다.
- 라우터의 `on_event` 는 쓰지 않는다 — deprecated 인 데다 모듈마다 흩어진다.
"""

from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager

from svkit.loader import domain_hooks

log = logging.getLogger(__name__)

HOOK = 'service_lifecycle'


async def _run(fn) -> None:
    result = fn()
    if inspect.isawaitable(result):
        await result


def _hooks(name: str) -> list[tuple[str, object]]:
    out = []
    for domain, mod in domain_hooks.load(HOOK):
        fn = getattr(mod, name, None)
        if callable(fn):
            out.append((domain, fn))
    return out


@asynccontextmanager
async def domain_lifespan(_app=None):
    """도메인 기동 훅 → yield → 정리 훅(역순)."""
    started = _hooks('on_startup')
    for domain, fn in started:
        try:
            await _run(fn)
        except Exception:
            log.warning('기동 훅 실패: %s', domain, exc_info=True)
    try:
        yield
    finally:
        for domain, fn in reversed(_hooks('on_shutdown')):
            try:
                await _run(fn)
            except Exception:
                log.warning('정리 훅 실패: %s', domain, exc_info=True)


def add_lifespan(app, factory) -> None:
    """기존 lifespan 을 덮지 않고 안쪽에 잇는다 (바깥이 먼저 뜨고 나중에 닫힌다)."""
    prev = app.router.lifespan_context

    @asynccontextmanager
    async def _combined(a):
        async with prev(a):
            async with factory(a):
                yield

    app.router.lifespan_context = _combined


__all__ = ['HOOK', 'domain_lifespan', 'add_lifespan']
