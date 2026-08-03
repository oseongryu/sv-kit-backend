# sv-kit-backend (svkit)

도메인 레지스트리 기반 통합 플랫폼 프레임워크. `sv-agent-team` 스켈레톤의
백엔드 코어(`common/` + `_base/` + registry + app 팩토리)를 pip 패키지로 분리한 것.

프론트 공통(@sv/kit-ui)은 `sv-kit-frontend` 저장소에 있다 (구 `sv-kit` 통합
저장소에서 분리). 소비자는 GitHub 태그 tarball 로 버전을 고정해 설치한다:

```
# requirements.txt
svkit @ https://github.com/oseongryu/sv-kit-backend/archive/refs/tags/v0.2.1.tar.gz
```

단독 실행 예제: [`examples/minimal`](examples/minimal) — 파일 3개로 API 서버 기동.

> **수정 전 필독**: [CONTRACT.md](CONTRACT.md) — 공개 계약(깨면 소비자 파손)과
> 내부(자유 변경)의 경계, additive 변경 규율.

## 왜

스켈레톤 복사(fork) 방식은 스켈레톤을 개선해도 기존 생성물이 못 받는다.
패키지 + 버전 핀이면 업그레이드 = 핀 한 줄이고, 프레임워크 코드가
site-packages 에 있어 에이전트/개발자가 실수로 수정할 수 없다.

## 사용 (프로젝트 쪽)

```
backend/
  app.py            # 아래 몇 줄이 전부
  worker.py
  requirements.txt  # svkit @ https://github.com/.../tags/v<버전>.tar.gz (+ gunicorn)
  domains/<slug>/   # 비즈니스 코드는 여기만
```

```python
# app.py
from svkit import create_app
app = create_app(__file__)

if __name__ == "__main__":
    from svkit import run
    run(app)
```

```python
# worker.py (전용 워커 컨테이너 분리 시)
from svkit.worker import main
main(__file__)
```

도메인 규약(etl/api 분리, `<slug>_` 테이블 접두, DOMAIN dict, ok/err 응답)은
sv-agent-team 의 `skeletons/SKELETON.md`(구조) + `SKELETON_IMPL.md`(API 상세)가 스펙.

## 모듈

| import | 역할 |
|---|---|
| `svkit.create_app` / `run` | 앱 팩토리 (registry 로드·스키마 init·bp 마운트·시드·워커) |
| `svkit.db` | 공유 SQLite (`get_conn`, `executescript`, `backup`) |
| `svkit.response` | `ok()` / `err()` 응답 규약 |
| `svkit.api` | `make_blueprint(slug)` → `/api/<slug>`, `page_args()` |
| `svkit.etl` | `RateLimiter`·`throttle`·`http_get_json`·`fetch_with_retry`·`run_job` |
| `svkit.queue` | SQLite 작업 큐 (레인·재시도·취소·운영 API·prometheus) |
| `svkit.scheduler` / `batch` / `sse` | 주기 실행 / 배치 파이프라인 / SSE 스트림 |
| `svkit.auth` / `storage` / `logger` / `alerts` | JWT 인증 / local↔S3 / 구조화 로깅 / Slack 알림 |

전부 env 로 켜는 opt-in — 기본은 무동작/로컬 (`APP_*`, `AUTH_ENABLED`,
`STORAGE_BACKEND`, `RUN_WORKER` 등, 상세는 `svkit/config.py`).

## 릴리스

버전은 semver. 브레이킹 체인지 시 minor(0.x 동안) 승격 + 아래 동기화 필수:

1. `pyproject.toml` + `svkit/__init__.__version__` + CHANGELOG
2. `git tag v<버전>` → `git push origin main --tags` (태그 push 가 곧 배포)
3. 소비자 requirements 의 tarball URL 태그 갱신 (스켈레톤 base 포함)
4. sv-agent-team `SKELETON_IMPL.md` 를 같은 내용으로 갱신 (에이전트용 스펙)
