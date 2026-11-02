"""앱 고유값 주입 창구 — **킷이 앱을 알아야 하는 유일한 통로다.**

킷은 앱을 import 하지 않고 문자열로도 가리키지 않는다. 그런데도 앱마다 달라지는 값이
있다 — 앱 루트가 어디인가, nav 를 무엇이 시드하는가, 운영 타임존은 무엇인가. 그것을
여기 한 곳에서 받는다.

    from svkit import hooks
    hooks.register(app_root=BACKEND_ROOT, nav_seeder=seed_nav_pages)

**등록은 부팅에서 한 번, 한 곳에서 한다.** 값을 안 주면 킷 기본값으로 떨어지고, 기본이
있을 수 없는 것(`app_root`)만 실패한다 — 조용히 엉뚱한 디렉토리를 가리키면 빈 설정·빈
DB 로 떠서 한참 뒤에 드러난다.

**부르는 자리는 앱의 모듈 하나면 된다.** 값이 필요한데 아직 등록이 없으면 이 창구가
`SVKIT_BOOTSTRAP`(기본 `svkit_bootstrap`) 모듈을 **한 번** import 한다 — 진입점
(웹·pytest·`python -m`·스트림릿·워커)마다 등록을 되풀이하면 언젠가 하나를 빠뜨리고,
그 진입점만 빈 설정으로 돈다. 킷이 아는 것은 그 **이름 하나**이고 내용은 모른다.

새 훅을 더할 때 지킬 것: **앱 전역에 걸리는 값만 여기 둔다.** 한 컴포넌트의 동작 차이는
그 생성자 인자로 받는다(`RateLimitMiddleware(app, body=…)`) — 전역으로 올리면 그 값을
쓰지 않는 다른 소비처까지 함께 바뀐다.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any, Callable

_values: dict[str, Any] = {}

#: 앱 부트스트랩 모듈 이름을 담는 env. 빈 값이면 지연 로드를 하지 않는다.
BOOTSTRAP_ENV = "SVKIT_BOOTSTRAP"
DEFAULT_BOOTSTRAP = "svkit_bootstrap"

_loaded = False


def _autoload() -> None:
    """앱 부트스트랩을 한 번 import 한다. 없으면 조용히 넘어간다 — 값을 직접 등록한
    앱과 env 로만 주는 앱이 모두 성립해야 한다.

    플래그를 import **전에** 세운다 — 부트스트랩이 등록 중에 다시 이 창구를 부르므로
    (설정을 읽어 값을 만든다) 그러지 않으면 무한 재귀가 된다.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    name = os.environ.get(BOOTSTRAP_ENV, DEFAULT_BOOTSTRAP)
    if not name:
        return
    try:
        importlib.import_module(name)
    except ImportError:
        pass


def register(**values: Any) -> None:
    """훅 등록(멱등, 덮어쓰기). 부팅에서 한 번 부른다."""
    _values.update({k: v for k, v in values.items() if v is not None})


def get(name: str, default: Any = None) -> Any:
    if name not in _values:
        _autoload()
    return _values.get(name, default)


# ─── 개별 접근자 — 소비처는 이 이름만 안다 ──────────────────────────

def app_root() -> Path:
    """앱 패키지 루트. config 탐색·배선 발견·선언 읽기·DB 경로 폴백의 기준이다.

    킷은 pip 로 깔려 `__file__` 로 앱을 도출할 수 없다. env `SVKIT_APP_ROOT` 로도 준다.
    미설정이면 RuntimeError.
    """
    value = get("app_root") or os.environ.get("SVKIT_APP_ROOT")
    if not value:
        raise RuntimeError(
            "앱 루트 미설정 — svkit.hooks.register(app_root=…) 를 부팅에서 부르거나 "
            f"env {BOOTSTRAP_ENV}/SVKIT_APP_ROOT 를 준다")
    return Path(value).resolve()


def nav_seeder() -> Callable | None:
    """`(conn, nav) -> None`. 없으면 nav 선언은 시드되지 않는다 — 표는 앱 것이다."""
    return get("nav_seeder")


def timezone() -> str:
    """운영 타임존 이름. 없으면 env `SVKIT_TZ`, 그것도 없으면 UTC."""
    return str(get("timezone") or os.environ.get("SVKIT_TZ") or "UTC")


def log_dir() -> Path:
    """파일 로깅 디렉토리. 없으면 env `APP_LOG_DIR`, 그것도 없으면 앱 루트 밑 `logs/`.

    env 갈래가 있는 이유는 앱 루트가 리포 안이기 때문이다 — 로그가 리포와 함께 지워지지
    않게 배포가 자기 데이터 자리를 넘긴다(컨테이너는 볼륨 지점을 넘긴다).
    """
    value = get("log_dir") or os.environ.get("APP_LOG_DIR")
    return Path(value) if value else app_root() / "logs"


__all__ = ["register", "get", "app_root", "nav_seeder", "timezone", "log_dir"]
