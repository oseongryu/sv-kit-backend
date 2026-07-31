"""통합 서비스 설정 — 모든 환경 의존값의 단일 소스.

CLAUDE.md 절대 규칙: 보안/환경 의존값에 silent fallback 금지. 단, 도메인
컨벤션(디렉토리/파일명)은 env 와 무관한 상수. 여기서는 로컬/도커 양쪽 실행
편의를 위해 명시적 기본값을 두되 출처를 분명히 한다.
"""
import os

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
API_HOST = os.environ.get("APP_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("APP_API_PORT", "5000"))

# --- 부팅 동작 ---
# 시드(샘플) 데이터 적재 — 데모/스모크용으로 기본 활성.
SEED_ON_START = os.environ.get("APP_SEED_ON_START", "1") == "1"
# 실외부 수집 시도(1) 여부. 외부 소스는 가용성에 따라 실패할 수 있어 기본 off.
COLLECT_ON_START = os.environ.get("APP_COLLECT_ON_START", "0") == "1"

# 외부 HTTP 타임아웃(초)
HTTP_TIMEOUT = int(os.environ.get("APP_HTTP_TIMEOUT", "20"))

# --- 작업 큐 ---
# 인프로세스 워커(개발/단일 컨테이너). 전용 워커 컨테이너 분리 시 false 로 두고
# 같은 이미지에서 `python worker.py` 를 별도 프로세스로 띄운다.
RUN_WORKER = os.environ.get("RUN_WORKER", "true").lower() == "true"
