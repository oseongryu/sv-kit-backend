# sv-kit-backend (svkit)

도메인 레지스트리 기반 통합 플랫폼 프레임워크. `sv-agent-team` 스켈레톤의
백엔드 코어(`common/` + `_base/` + registry + app 팩토리)를 pip 패키지로 분리한 것.

## 어느 키트를 고르는가 — 스택으로 고른다

백엔드 키트는 **두 계보**다. 둘 다 현역이고, 프레임워크가 다를 뿐이다.

| 쓰는 프레임워크 | 키트 | 저장소 |
|---|---|---|
| Flask (+ SQLite) | `svkit` | 이 저장소 — `https://github.com/oseongryu/sv-kit-backend` |
| FastAPI (+ SQLAlchemy async) | `svkit2` | `https://github.com/oseongryu/sv-kit-backend-v2` |

svkit2 는 svkit 의 대체가 아니다. 도메인 레지스트리·`/api/<slug>`·`{ok,data}` 응답
규약은 같지만 프레임워크 전제가 서로 달라 한쪽이 다른 쪽을 흡수할 수 없다
(그 중립화를 시도했다가 되돌린 기록이 svkit2 CONTRACT 의 「설계 원칙」에 있다).
**Flask 로 짜면 svkit, FastAPI 로 짜면 svkit2** — 고르는 기준은 그것 하나다.

프론트 공통(@sv/kit-ui)은 `sv-kit-frontend` 저장소에 있다 (구 `sv-kit` 통합
저장소에서 분리). 소비자는 GitHub 태그 tarball 로 버전을 고정해 설치한다:

```
# requirements.txt
svkit @ https://github.com/oseongryu/sv-kit-backend/archive/refs/tags/svkit-v0.2.3.tar.gz
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
  requirements.txt  # svkit @ https://github.com/.../tags/svkit-v<버전>.tar.gz (+ gunicorn)
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
2. `examples/minimal/requirements.txt` 의 태그 URL 갱신 — 예제도 소비자다.
   여기를 빼먹으면 저장소가 자기 옛 버전을 설치하는 예제를 배포하게 된다
3. `git tag svkit-v<버전>` → `git push origin main --tags` (태그 push 가 곧 배포)
4. 소비자 requirements 의 tarball URL 태그 갱신 (git-worktree-web)

### 태그 형식

태그는 `svkit-v<버전>` 이다 — 예: `svkit-v0.2.3` (프론트의 `ui-v…` 와 같은 꼴 — 한 사람이
여러 키트를 오갈 때 태그만 보고 어느 패키지인지 알기 위해서다).

접두사 없이 나간 `v0.1.0`·`v0.2.0`·`v0.2.1` 은 **그대로 둔다.** 옮기지도 지우지도 않는다 —
소비자 requirements 가 그 URL 을 가리키고 있어서 지금 URL 은 계속 동작한다.
날짜 버전으로 나간 `svkit-v20260804.1.0` 도 마찬가지다 — 버전 체계를 semver 로
되돌렸어도 이미 발행된 태그는 그 번호 그대로 남는다.

### 태그 없는 main 커밋을 남기지 않는다

main 에 올라간 것은 태그로 봉인될 때까지 **아무 소비자도 받지 못한다.**
소비 채널이 태그 tarball 하나뿐이라, 태그 없이 push 된 커밋은 저장소에서는
보이는데 설치물에는 없는 상태로 남는다. 실제로 그런 어긋남이 한 번 났다 —
`examples/minimal/requirements.txt` 는 main 에 있지만 `v0.2.1` tarball 에는 없다.

그러니 main 에 push 하는 단위를 릴리스 단위로 맞춘다. 문서만 고친 커밋이라
버전을 올릴 일이 아니면, 다음 버전 태그에 함께 실릴 것을 알고 남긴다.
