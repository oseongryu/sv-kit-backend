"""svkit — 도메인 레지스트리 기반 통합 플랫폼 프레임워크 (Flask 계보).

sv-agent-team 스켈레톤의 백엔드 코어(`common/` + `_base/` + registry)를
pip 패키지로 분리한 것. 규약은 스켈레톤과 동일:

- 1 아이디어 = 1 도메인 모듈 (`domains/<slug>/`, etl/api 분리)
- 테이블은 `<slug>_` 접두, 응답은 ok()/err()
- 인프라(auth·storage·logger·alerts·queue·sse·batch·scheduler)는 env 로 켜는 opt-in

사용:
    from svkit import create_app
    app = create_app(__file__)

FastAPI 계보는 `svkit2`(sv-kit-backend-v2) 다. 두 판은 **`base` 모듈을 공유**한다
— 실패 타입·응답 본문 모양·페이징·잡 상태·스케줄 spec·지표·SSE 프레임·JWT 가
같은 코드에서 나오고, 최상위 이름도 같은 것을 내보낸다. 프레임워크에 매인
것(라우팅·DB·async)만 판마다 다르다. 무엇이 같고 무엇이 다른지는 CONTRACT 참조.
"""

__version__ = "0.3.0"

from svkit import (alerts, base, batch, config, db, etl, logger, queue,
                   registry, scheduler, storage)
from svkit.api import Page, make_blueprint, make_router, page_args
from svkit.app import create_app, run
from svkit.auth import (User, current_user, optional_user, require_admin,
                        require_auth, require_user)
from svkit.base import (ApiError, Conflict, Forbidden, NotFound, Unauthorized,
                        WithMeta)
from svkit.queue import JobState
from svkit.registry import Domain
from svkit.response import envelope, err, ok
from svkit.sse import EventStream

__all__ = [
    "__version__",
    # 앱
    "create_app", "run",
    # 라우팅
    "make_blueprint", "make_router", "page_args", "Page",
    # 응답·실패
    "ok", "err", "envelope", "WithMeta", "EventStream",
    "ApiError", "NotFound", "Conflict", "Unauthorized", "Forbidden",
    # 인증
    "require_auth", "require_user", "require_admin", "current_user",
    "optional_user", "User",
    # DB·도메인
    "db", "Domain",
    # 인프라
    "queue", "JobState", "scheduler", "batch", "etl", "storage",
    "alerts", "logger", "config", "registry", "base",
]