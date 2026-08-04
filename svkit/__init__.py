"""svkit — 도메인 레지스트리 기반 통합 플랫폼 프레임워크.

sv-agent-team 스켈레톤의 백엔드 코어(`common/` + `_base/` + registry)를
pip 패키지로 분리한 것. 규약은 스켈레톤과 동일:

- 1 아이디어 = 1 도메인 모듈 (`domains/<slug>/`, etl/api 분리)
- 테이블은 `<slug>_` 접두, 응답은 ok()/err()
- 인프라(auth·storage·logger·alerts·queue·sse·batch·scheduler)는 env 로 켜는 opt-in

사용:
    from svkit import create_app
    app = create_app(__file__)
"""

__version__ = "20260804.1.0"

from svkit.app import create_app, run

__all__ = ["__version__", "create_app", "run"]
