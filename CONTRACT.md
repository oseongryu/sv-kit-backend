# sv-kit-backend 공개 계약 (CONTRACT)

이 문서는 svkit 을 고치는 사람(사람이든 에이전트든)을 위한 경계 선언이다.
**공개 계약**에 속하는 것을 바꾸면 소비자(git-worktree-web)가 깨진다.
**내부**에 속하는 것은 계약만 지키면 자유롭게 갈아치울 수 있다 — 라이브러리 교체 포함.

프론트 공통(@sv/kit-ui)은 `sv-kit-frontend` 저장소로 분리 — 그쪽 CONTRACT 참조.
FastAPI 계보인 svkit2 는 `sv-kit-backend-v2` 저장소다. 둘 다 현역이고
스택으로 고른다 — Flask 면 여기, FastAPI 면 그쪽.

svkit 자신의 실적은 0.1.0 → 0.2.1 세 판이다(CHANGELOG 기준).
0.2.0 은 전부 additive 였고 0.2.1 은 내부 정리라 공개 계약을 건드리지 않았다.
표면이 좁아서 지킨 게 아니라 위 규율로 지킨 것이고, 그걸 유지하는 것이 이 문서의 목적이다.

## 변경 규칙 (요약)

1. **additive 우선** — 새 기능은 새 서브패스/새 함수/새 옵션 props 로.
   기존 시그니처·키·기본 동작 변경은 breaking 이다.
2. **breaking 은 메이저 신호와 함께** — 계약을 깨야 하면 버전을 올리고
   README/CHANGELOG 에 마이그레이션을 적는다. 태그 tarball 고정 덕에 기존
   소비자는 조용히 깨지지 않는다 — 이 안전장치를 전제로 설계해도 된다.
3. **라이브러리 교체는 내부에서 흡수** — 계약 모양(함수 시그니처 등)을
   유지한 채 구현만 바꾼다.
4. **소비자가 import 하는 이름은 계약이다** — 소비 앱의 `app.py`·`worker.py`
   와 도메인 코드가 부르는 진입점·함수 이름을 없애지 않는다.

## 계보 공통 층 — `svkit.base`

0.3.0 부터 **프레임워크·DB·async 를 모르는 층**은 `svkit/base.py` 한 파일에 있고,
**같은 내용의 파일이 svkit2 에도 있다.** 합치면 이 파일 하나가 남고 나머지는
각 프레임워크 어댑터로 남는다. 목적은 하나다 — 합칠 때 소비 프로젝트가 고칠 줄을 줄인다.

base 에 들어갈 수 있는 것의 조건: **Flask/FastAPI/SQLAlchemy 를 import 하지 않는다.**
그 선을 넘는 순간 그건 base 가 아니라 어댑터다.

| base 가 정하는 것 | 두 판이 각자 하는 것 |
|---|---|
| 실패 타입(`ApiError` 계열), 응답 본문 `{ok,data,meta?}`/`{ok:false,error}` | 그 본문을 응답 객체로 만드는 방법 |
| `Page`·상한 계산, 잡 상태 표면(`JobState`), 도메인 선언(`Domain`) | 라우팅(Blueprint/APIRouter), 파라미터 주입 |
| JWT·비밀번호 해시, 스케줄 spec, 배치 진행 문구, 지표 키·프로메테우스 본문, SSE 프레임, 로그 포맷 | DB 접근(sqlite3 / SQLAlchemy), 동기/async |

**라우팅은 base 가 다루지 않는다.** 라우트를 데이터로 모아 어댑터가 실체화하는
중립층은 한 번 만들었다가 되돌린 구조다(코드 2배, 프레임워크 강점 포기 —
경위는 svkit2 CONTRACT 「설계 원칙 1」). 나누는 것은 *규약*이지 *라우팅*이 아니다.

**base 를 고칠 때는 양쪽을 같이 고친다.** 한쪽만 고치면 두 파일이 갈라지고,
그 순간 이 층을 둔 이유가 사라진다. 두 저장소의 `base.py` 는 **바이트 단위로 같아야 한다**
(`sha256`/`md5` 비교로 확인).

`base` 의 이름 중 **아래 「공개 계약」에 올라간 것만 계약**이다. 나머지(예: `env_int`,
`format_log`)는 두 판이 나눠 쓰는 내부 도구다 — 이름을 얼리면 구현을 바꿀 자유가 사라진다.

## svkit (백엔드 pip 패키지)

### 공개 계약 — 깨면 소비자 파손

- `create_app(root, title=..., infra=True, expose_error_detail=False, root_route=True)`
  / `run(app)` / `worker.main(root)` 진입점. **인자 기본값은 계약이다** — 특히
  `infra=True`. `infra=False` 는 DB·잡을 이미 가진 프로젝트가 명시적으로 고르는 값이고,
  이 인자 이름·의미는 svkit2 와 같다
- **DOMAIN dict 키**: `slug`, `title`, `bp`, `bps`, `schema`, `seed`,
  `collect`, `migrate(conn)` — 이름·의미·호출 순서(migrate → schema →
  공통 스키마)
- 도메인이 import 하는 모듈 표면:
  - `svkit.db` — `get_conn()`(컨텍스트 매니저), `executescript`, `backup`
  - `svkit.response` — `ok(data)`, `err(msg, status)` (+응답 JSON 모양
    `{ok, data, meta?}` / `{ok:false, error}`)
  - `svkit.api` — `make_blueprint(slug, prefix=None, tags=None, auto_ok=False)`
    (→ `/api/<slug>` prefix), `page_args()` → `Page(limit, offset)`.
    **네 인자 전부 계약이다** — 선택 인자를 나중에 뺄 수 없다
  - `svkit.ApiError`(+`NotFound`·`Conflict`·`Unauthorized`·`Forbidden`) 와
    그것이 `{ok:false, error}` 로 변환된다는 것. `return err(...)` 와
    `raise ApiError(...)` 는 **둘 다** 지원한다 — 어느 쪽도 없앨 수 없다
  - `svkit.queue.JobState` — 큐 핸들러의 첫 인자다(`fn(state, params)`).
    dict 표기(`state['progress']`)와 속성 표기(`state.progress`·`report()`·
    `should_stop`·`current`·`total`·`job_id`)가 **둘 다** 계약이다.
    한쪽만 남기면 그쪽 표기로 쓴 도메인이 전부 깨진다
  - `svkit.registry.Domain` — DOMAIN 선언의 클래스 형태(dict 상속).
    계약은 여전히 **DOMAIN dict 의 키**이고, 이 클래스는 그 위의 선택지다
  - `svkit.etl` / `svkit.queue` / `svkit.scheduler` / `svkit.auth` /
    `svkit.storage` / `svkit.sse` / `svkit.batch` / `svkit.logger` /
    `svkit.alerts` 의 공개 함수 시그니처
  - **svkit2 와 이름을 맞추려고 둔 별칭들**(`make_router`, `db.conn`/`read`,
    `etl.get_json`/`fetch_retry`, `queue.metrics`/`start_workers`,
    `scheduler.start`, `sse.EventStream`, `auth.require_user`,
    `storage.BACKEND` …)도 한 번 내보낸 이상 계약이다. 이름만 같고 **동기/async·
    반환 타입은 각 판의 것**이라는 점은 문서에 적힌 대로다
- **env 변수 이름**: `APP_DB_PATH`/`APP_DB_DIR`/`APP_BACKUP_DIR`,
  `APP_ENABLED_DOMAINS`, `APP_STATIC_DIR`, `AUTH_ENABLED`, `RUN_WORKER`,
  `SEED_ON_START`, `COLLECT_ON_START` 등 — env 는 문서화된 순간 계약이다
- 메타 라우트 경로: `/api/health`, `/api/domains`, `/metrics`, `/api/backup`
- 공통 테이블 접두: `auth_*`, `queue_*`, `etl_*` — 도메인 `<slug>_` 접두
  규약과의 충돌 회피선
- **전제(교체 불가)**: Flask 자체. 도메인 코드가 `flask.request`·Blueprint
  를 직접 쓰므로 Flask 는 계약의 일부다. 메이저 버전업 흡수는 svkit 책임,
  프레임워크 교체는 범위 밖.

### 내부 — 자유 변경

- SQLite 연결 재시도·WAL 설정, 큐/스케줄러 스레드 구현, 로그 포맷,
  backup 보관 개수, registry 탐색 구현 등 — 위 표면만 유지하면 전부.
- `base` 안에서 위 계약에 오르지 않은 이름(`env_int`·`format_log`·`batch_progress` 등)
  — 단, **고칠 때는 양쪽 저장소를 함께** 고친다(위 「계보 공통 층」).
- `config` 모듈의 파이썬 속성 이름은 계약이 아니다 — 계약은 **env 변수 이름**이다.

## 배포·버전 규약

| 축 | 배포물 | 소비자 반영 |
|---|---|---|
| svkit | GitHub 태그 `svkit-vX.Y.Z` (tarball) | requirements 의 태그 URL 갱신 |

- 버전은 **semver(0.x)** 다 — `20260804.1.0` 한 판만 날짜 기반이었고 0.2.3 에서 되돌렸다
  (경위는 CHANGELOG 0.2.3).
- 태그: **`svkit-vX.Y.Z`.** `git push origin main --tags` 가 곧 배포.
  접두사 없이 나간 `v0.1.0`·`v0.2.0`·`v0.2.1` 과 날짜 버전으로 나간
  `svkit-v20260804.1.0` 은 그 형식 그대로 두고 옮기지 않는다.
  소비자 requirements 의 지금 URL 은 계속 동작한다 (아래 태그 불변 규약).
  접두사를 붙이는 이유는 프론트 `ui-vX.Y.Z`·svkit2 `svkit2-vX.Y.Z` 와 나란히 놓고
  태그만 보고 어느 패키지인지 알기 위해서다
- **소비 채널은 GitHub 태그 고정 하나**: git-worktree-web 의 `requirements.txt` 가
  `svkit @ https://github.com/oseongryu/sv-kit-backend/archive/refs/tags/v0.2.1.tar.gz`
  로 고정 소비한다 (public 저장소 — 무인증, git 바이너리 불필요).
  거기서 svkit 을 import 하는 곳은 `app.py` 와 `domains/core/routes_core.py` 다
- 소비자는 태그 URL 로 버전이 고정된다 — kit 의 어떤 변경도 소비자가
  URL 태그를 올리기 전에는 도달하지 않는다. 이것이 breaking 변경의
  최종 방어선이다. **한 번 push 한 태그는 옮기지 않는다.** 옮기면 소비자가
  같은 URL 로 다른 코드를 받는다 — 고정의 의미가 사라진다
- 태그가 곧 배포물이라 **태그 없이 main 에만 있는 커밋은 아무에게도 도달하지
  않는다.** main push 단위를 릴리스 단위에 맞춘다 (README 「릴리스」 참조)
