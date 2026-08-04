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
2. **breaking 은 CHANGELOG 에 명시한다** — 날짜 버전에는 메이저 자리가 없어
   버전 문자열이 크기를 말해 주지 않는다. 계약을 깨야 하면 그 판의 CHANGELOG
   항목에 **깨지는 것과 마이그레이션**을 적어라. 소비자는 태그 URL 로 고정돼
   있어 자기가 태그를 올릴 때 그 항목을 읽고 알아챈다 — 조용히 도달하지 않는다.
   이 안전장치를 전제로 설계해도 되지만, **적지 않으면 안전장치가 없는 것과 같다.**
3. **라이브러리 교체는 내부에서 흡수** — 계약 모양(함수 시그니처 등)을
   유지한 채 구현만 바꾼다.
4. **소비자가 import 하는 이름은 계약이다** — 소비 앱의 `app.py`·`worker.py`
   와 도메인 코드가 부르는 진입점·함수 이름을 없애지 않는다.

## svkit (백엔드 pip 패키지)

### 공개 계약 — 깨면 소비자 파손

- `create_app(root)` / `run(app)` / `worker.main(root)` 진입점
- **DOMAIN dict 키**: `slug`, `title`, `bp`, `bps`, `schema`, `seed`,
  `collect`, `migrate(conn)` — 이름·의미·호출 순서(migrate → schema →
  공통 스키마)
- 도메인이 import 하는 모듈 표면:
  - `svkit.db` — `get_conn()`(컨텍스트 매니저), `executescript`, `backup`
  - `svkit.response` — `ok(data)`, `err(msg, status)` (+응답 JSON 모양
    `{ok, data, meta?}` / `{ok:false, error}`)
  - `svkit.api` — `make_blueprint(slug)`(→ `/api/<slug>` prefix), `page_args()`
  - `svkit.etl` / `svkit.queue` / `svkit.scheduler` / `svkit.auth` /
    `svkit.storage` / `svkit.sse` / `svkit.batch` / `svkit.logger` /
    `svkit.alerts` 의 공개 함수 시그니처
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

## 배포·버전 규약

| 축 | 배포물 | 소비자 반영 |
|---|---|---|
| svkit | GitHub 태그 `svkit-vYYYYMMDD.N.0` (tarball) | requirements 의 태그 URL 갱신 |

- 버전은 **날짜 기반(CalVer) `YYYYMMDD.N.0`** 이다 — 발행일 + 그날의 판 순번(1부터),
  마지막 `0` 은 자리 채움. `20260804.1.0` 부터 이 형식이고 그 전은 semver(0.x)였다.
  `.0` 을 붙이는 이유는 npm 이 `major.minor.patch` 세 자리를 강제하기 때문이고
  (파이썬은 두 자리도 받지만 세 키트의 형식을 하나로 두려고 맞췄다), 월·일을 붙여
  쓰는 이유는 npm 이 leading zero 를 거부하기 때문이다 — 상세는 CHANGELOG 머리말
- 태그: **`svkit-vYYYYMMDD.N.0`** (예: `svkit-v20260804.1.0`).
  `git push origin main --tags` 가 곧 배포.
  이미 나간 `v0.1.0`·`v0.2.0`·`v0.2.1`(접두사 없음)과 `svkit-v0.2.2`(semver)는
  그 형식 그대로 두고 옮기지 않는다. 소비자 requirements 의 지금 URL 은 계속
  동작한다 (아래 태그 불변 규약). 접두사를 붙이는 이유는 프론트 `ui-v…`·svkit2
  `svkit2-v…` 와 나란히 놓고 태그만 보고 어느 패키지인지 알기 위해서다
- **소비 채널은 GitHub 태그 고정 하나**: git-worktree-web 의 `requirements.txt` 가
  `svkit @ https://github.com/oseongryu/sv-kit-backend/archive/refs/tags/v0.2.1.tar.gz`
  로 고정 소비한다 (public 저장소 — 무인증, git 바이너리 불필요).
  거기서 svkit 을 import 하는 곳은 `app.py` 와 `domains/core/routes_core.py` 다
- 소비자는 태그 URL 로 버전이 고정된다 — kit 의 어떤 변경도 소비자가
  URL 태그를 올리기 전에는 도달하지 않는다. 이것이 breaking 변경의
  최종 방어선이고, 날짜 버전에서 메이저 자리를 대신하는 장치이기도 하다.
  **태그를 올리는 사람이 그 사이 판의 CHANGELOG 를 읽는다**는 전제라,
  breaking 을 CHANGELOG 에 적는 것이 규칙 2 다. **한 번 push 한 태그는 옮기지 않는다.** 옮기면 소비자가
  같은 URL 로 다른 코드를 받는다 — 고정의 의미가 사라진다
- 태그가 곧 배포물이라 **태그 없이 main 에만 있는 커밋은 아무에게도 도달하지
  않는다.** main push 단위를 릴리스 단위에 맞춘다 (README 「릴리스」 참조)
