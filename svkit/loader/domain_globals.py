"""도메인 상수 집결 — 모듈이 저마다 둔 `globals.py` 를 한 자리에서 본다.

각 모듈은 `module_<이름>/globals.py` 에 자기 어휘를 둔다. 여기는 그것을 **이름으로**
거둬 오므로, 새 모듈을 더할 때 목록을 고칠 곳이 없다 — 파일 하나를 두면 합류한다.

상수만 본다(대문자 이름). 소문자·`_` 접두는 그 파일의 내부 사정이고, 함수·클래스는
상수가 아니라 층의 일이다.
"""
from __future__ import annotations

from typing import Any

from svkit.loader import domain_hooks

HOOK = "globals"


def _constants(mod) -> dict[str, Any]:
    return {k: v for k, v in vars(mod).items()
            if k.isupper() and not k.startswith("_")}


def all_globals() -> dict[str, dict[str, Any]]:
    """`{모듈이름: {상수이름: 값}}` — 켜진 모듈만, 패키지명 사전순.

    이름이 겹쳐도 막지 않는다. 모듈별로 갈려 있으니 충돌이 아니고, 같은 어휘를 여럿이
    쓰는지 보는 것은 `owners()` 의 일이다.
    """
    return {name: _constants(mod) for name, mod in domain_hooks.load(HOOK)}


def owners(const: str) -> list[str]:
    """그 이름의 상수를 가진 모듈들 — 같은 어휘가 어디에 흩어져 있는지 본다."""
    return [name for name, consts in all_globals().items() if const in consts]


def flat() -> dict[str, dict[str, Any]]:
    """`{상수이름: {모듈: 값}}` — 이름 기준 조망. 한 모듈만 가진 이름도 그대로 담긴다."""
    out: dict[str, dict[str, Any]] = {}
    for name, consts in all_globals().items():
        for key, value in consts.items():
            out.setdefault(key, {})[name] = value
    return out


__all__ = ["all_globals", "owners", "flat", "HOOK"]
