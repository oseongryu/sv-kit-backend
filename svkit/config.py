"""통합 서비스 설정 — 모든 환경 의존값의 단일 소스.

보안/환경 의존값에 silent fallback 금지. 단, 도메인 컨벤션(디렉토리/파일명)은
env 와 무관한 상수. 여기서는 로컬/도커 양쪽 실행 편의를 위해 명시적 기본값을
두되 출처를 분명히 한다.

공통 env(`APP_API_*`·`APP_SEED_ON_START`·`RUN_WORKER` 등)의 **파싱은
`base.BaseConfig` 하나**이고 여기서는 기본값만 정한다 — svkit2 도 같은 클래스를
상속하므로 두 판의 env 해석이 갈라지지 않는다. 소비자가 보는 이름
(`config.API_PORT` 등)은 계약이라 모듈 상수 모양을 그대로 유지한다.
"""
import os

from svkit.base import BaseConfig


class Config(BaseConfig):
    """Flask 판 기본값. 값 자체는 아래에서 모듈 상수로 풀어 놓는다."""

    API_PORT_DEFAULT = 5000
    #: 시드(샘플) 데이터 적재 — 데모/스모크용으로 이 판에서는 기본 활성
    SEED_DEFAULT = True


_C = Config.load()

# --- DB ---
# 컨테이너/로컬 공용. docker compose 에서는 DB 를 named volume 에 둔다(WAL 안정성).
# 기본은 실행 디렉토리(프로젝트 backend/) 기준 — svkit 은 site-packages 에 있어
# __file__ 기준을 쓰면 안 된다. 컨테이너에서는 APP_DB_DIR/APP_DB_PATH env 로 지정.
DB_DIR = os.environ.get("APP_DB_DIR", os.path.join(os.getcwd(), "data"))
DB_FILENAME = "app.db"
DB_PATH = os.environ.get("APP_DB_PATH") or os.path.join(DB_DIR, DB_FILENAME)
# 백업 디렉토리. 기본은 DB 옆이지만, DB 가 named volume 에 있으면 볼륨 삭제 시 백업도
# 함께 사라지므로 APP_BACKUP_DIR 로 호스트 바인드마운트를 가리키게 하는 것을 권장.
BACKUP_DIR = os.environ.get("APP_BACKUP_DIR") or os.path.join(os.path.dirname(DB_PATH), "backup")

# --- 서버 ---
API_HOST = _C["API_HOST"]
API_PORT = _C["API_PORT"]
#: 허용 오리진(쉼표 구분). 미설정이면 기존 동작대로 전체 허용.
CORS_ORIGINS = _C["CORS_ORIGINS"] or ["*"]

# --- 부팅 동작 ---
SEED_ON_START = _C["SEED_ON_START"]
# 실외부 수집 시도 여부. 외부 소스는 가용성에 따라 실패할 수 있어 기본 off.
COLLECT_ON_START = _C["COLLECT_ON_START"]

#: 특정 도메인만 로드(쉼표 구분). 미설정이면 전부.
ENABLED_DOMAINS = _C["ENABLED_DOMAINS"]
#: 정적 SPA 디렉토리(Next static export 등). 없으면 API 만.
STATIC_DIR = _C["STATIC_DIR"]

# 외부 HTTP 타임아웃(초)
HTTP_TIMEOUT = _C["HTTP_TIMEOUT"]

# --- 작업 큐 ---
# 인프로세스 워커(개발/단일 컨테이너). 전용 워커 컨테이너 분리 시 false 로 두고
# 같은 이미지에서 `python worker.py` 를 별도 프로세스로 띄운다.
RUN_WORKER = _C["RUN_WORKER"]

__all__ = [
    "DB_DIR", "DB_FILENAME", "DB_PATH", "BACKUP_DIR",
    "API_HOST", "API_PORT", "CORS_ORIGINS",
    "SEED_ON_START", "COLLECT_ON_START", "ENABLED_DOMAINS", "STATIC_DIR",
    "HTTP_TIMEOUT", "RUN_WORKER",
]