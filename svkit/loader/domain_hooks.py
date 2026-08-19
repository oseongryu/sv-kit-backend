"""도메인 선택 훅 로더 — 공용층이 도메인 이름을 모르게 하는 장치.

각 도메인은 `module_<패키지>/<훅이름>.py` 를 선택적으로 둔다. 공용층은 그 이름을
모른 채 로드된 도메인만 순회해 훅을 가져온다. 훅 모듈이 없으면 건너뛰고, 훅 안의
다른 import 실패는 감추지 않는다(도메인 버그를 조용히 삼키지 않기 위함).

탐색 대상은 slug 가 아니라 **패키지명**이다 — slug 에 하이픈을 쓴 모듈이 있어
slug 로는 모듈 경로를 만들 수 없다.
"""

import importlib
import logging
import os
import sys

from svkit.loader.editions import MODULE_PREFIX

log = logging.getLogger(__name__)


def domain_names() -> list[str]:
    """훅 탐색 대상 도메인 패키지명 — 이미 로드된 것 ∪ APP_DOMAIN_PACKAGES.

    `module_` 접두는 `removeprefix` 로 뗀다 — 이름 안에 밑줄이 있는 모듈이 있어
    구분자로 자르면 잘못된 이름이 나온다.
    """
    allow = {s.strip().removeprefix(MODULE_PREFIX)
             for s in os.environ.get('APP_DOMAIN_PACKAGES', '').split(',') if s.strip()}
    loaded = {n.removeprefix(MODULE_PREFIX) for n in list(sys.modules)
              if n.startswith(MODULE_PREFIX) and '.' not in n}
    return sorted(allow | loaded)


def load(hook: str) -> list[tuple[str, object]]:
    """`(도메인패키지명, 훅모듈)` 목록을 패키지명 사전순으로 반환."""
    found = []
    for name in domain_names():
        target = f'{MODULE_PREFIX}{name}.{hook}'
        try:
            found.append((name, importlib.import_module(target)))
        except ModuleNotFoundError as e:
            if e.name == f'{MODULE_PREFIX}{name}':
                log.warning('도메인부재: %s', name)
            elif e.name != target:
                raise
    return found
