# Changelog

svkit 의 모든 소비자 영향 변경을 기록한다. 형식은 Keep a Changelog, 버전은 semver(0.x).
태그는 `svkit-v<버전>` 이다. 0.2.1 까지는 접두사 없이 `v<버전>` 으로 나갔고,
한 판(`20260804.1.0`)은 날짜 기반(CalVer)으로 나갔다가 0.2.3 부터 semver 로 돌아왔다.
**어느 형식으로 나갔든 이미 push 한 태그는 옮기지 않는다**(소비자 requirements 가
그 URL 을 가리킨다).

항목은 **무엇을 왜** 로 적는다. "무엇" 만 남으면 다음 사람이 그 결정을 되돌려도 되는지
판단할 수 없다 — 아래 0.2.0·0.1.0 이 그렇게 남아 있다(소급해 지어내지 않고 그대로 둔다).

## 0.3.0

**svkit2(FastAPI 계보)와 공유하는 `svkit.base` 를 도입하고, 두 판의 표면을 맞췄다.**
언젠가 두 저장소를 합칠 때 소비 프로젝트가 고쳐야 할 줄을 줄이는 것이 목적이다.
**전부 additive** — 기존 공개 이름·시그니처·응답 모양은 하나도 바꾸지 않았다.

- **`svkit/base.py` 신설.** 프레임워크·DB·async 를 모르는 층을 여기로 모았다:
  env 파싱(`BaseConfig`)·실패 타입(`ApiError` 계열)·응답 본문·`Page`·`BaseJobState`·
  `BaseDomain`·스토리지 백엔드·JWT/비밀번호·스케줄 spec·배치 진행 문구·지표와
  프로메테우스 본문·SSE 프레임·로그 포맷. **이 파일은 sv-kit-backend-v2 에 같은
  내용으로 들어 있다** — 합치면 한 파일이 되고, 나머지는 프레임워크 어댑터로 남는다
- **라우팅 중립층은 만들지 않았다.** 그 구조는 v1 에서 한 번 만들었다가 되돌렸고
  (코드 2배·프레임워크 강점 포기), base 는 라우팅을 다루지 않는다. 두 판이 나누는
  것은 *규약*이지 *라우팅*이 아니다
- `svkit.errors` 신설 — `ApiError`/`NotFound`/`Conflict`/`Unauthorized`/`Forbidden`.
  `create_app` 이 핸들러를 등록하므로 도메인이 `raise ApiError('없음', 404)` 만 해도
  `{ok:false, error}` 로 나간다. 기존 `return err(...)` 도 그대로 동작한다
- `create_app` 인자를 svkit2 와 맞췄다 — `title`·`infra`·`expose_error_detail`·
  `root_route`(+이 판 전용 `wrap_http_errors`). 기본값도 같다. `infra=False` 는
  DB·잡을 프로젝트가 이미 가진 경우로, 큐/스케줄러 bp·워커·스키마 생성을 건너뛴다
- `queue.JobState` 신설 — **dict 이면서 속성으로도 읽고 쓴다.** `state['progress']` 로
  쓰던 핸들러와 svkit2 표기(`state.report(...)`·`state.should_stop`)가 같은 값을 본다
- `page_args()` 가 `Page(limit, offset)` NamedTuple 을 반환한다(튜플이라 기존
  `limit, offset = page_args()` 는 그대로)
- `registry.Domain` 클래스 + `registry.register(app)`, `make_blueprint(slug, prefix,
  tags, auto_ok)` — `auto_ok=True` 면 핸들러가 알맹이만 반환해도 규약으로 감싼다
  (svkit2 의 `OkRoute` 와 같은 역할, 기본은 off)
- 이름 별칭(양쪽에서 같은 문장을 쓰기 위한 것): `make_router`·`db.conn`/`read`·
  `db.fetch_all`/`fetch_one`/`scalar`/`insert_id`/`exists`·`etl.get_json`/`fetch_retry`·
  `queue.metrics`·`queue.start_workers`·`scheduler.start`/`tick`·`sse.EventStream`·
  `auth.require_user`/`current_user`/`User`·`storage.BACKEND`
- `config` 에 `ENABLED_DOMAINS`·`STATIC_DIR`·`CORS_ORIGINS` 추가(전에는 코드 곳곳에서
  env 를 직접 읽던 값). CORS 는 `APP_CORS_ORIGINS` 미설정 시 기존대로 전체 허용
- 부수 변경 두 가지: 불리언 env 가 `1/true/yes/on` 을 모두 받는다(전에는 `1` 만),
  error 레벨 로그가 stderr 로 나간다(전에는 stdout — svkit2 와 맞췄다)

## 0.2.3

**날짜 기반(CalVer) 버전 체계를 되돌리고 semver 로 돌아왔다.** 하루 만의 번복이다.
`20260804.1.0` 판은 실제로 배포됐으므로 아래 항목과 태그를 그대로 두고, **이 판부터**
다시 semver 다 — 그래서 되돌림인데도 번호는 뒤로 가지 않고 0.2.2 의 다음 patch 다.

되돌린 이유:

- **날짜는 호환성을 말해 주지 않는다.** semver 의 메이저 자리는 "이 판으로 올리면
  깨질 수 있다" 를 번호 하나로 전달하는데, `YYYYMMDD.N.0` 에는 그 자리가 없다.
  CalVer 로 가면서 그 신호를 CHANGELOG 항목으로 옮겼지만, 번호가 스스로 말하는 것과
  읽어야 아는 것은 다르다
- **마지막 `.0` 은 의미 없는 자리였다.** npm 이 `major.minor.patch` 두 자리를 거부해서
  붙인 자리 채움일 뿐, 아무것도 세지 않았다
- **날짜를 넣어 얻는 실익이 작다.** 소비자는 태그 URL 로 고정하고 그 URL 을 손으로
  올리므로, 언제 나온 판인지는 태그 목록과 이 문서로 이미 안다

- 코드 변경 없음 — 버전 문자열과 문서(README 릴리스 절차·CONTRACT 배포·버전 규약)뿐

## 20260804.1.0

**버전 체계를 semver 에서 날짜 기반(CalVer)으로 바꿨다.** 세 키트
(`svkit`·`svkit2`·`@sv/kit-ui`)가 같은 날 같은 값 `20260804.1.0` 으로 함께 넘어간다.

- 형식은 `YYYYMMDD.N.0` — 발행일 + 그날의 판 순번. 마지막 `.0` 은 npm 이 세 자리를
  강제해서 둔 자리 채움이고, 세 저장소를 같은 모양으로 두려고 파이썬 쪽도 맞췄다
- 0.x 를 쓰는 동안 minor 를 브레이킹 신호로 쓰기로 했는데, 실제로 올라간 판들은
  전부 additive 였다. 신호로 쓰인 적 없는 자리를 유지하는 대신 **언제 나온 판인지**를
  버전이 말하게 했다. breaking 판정은 CHANGELOG 항목이 맡는다
- 코드 변경 없음 — 버전 문자열과 문서(README 릴리스 절차·CONTRACT 배포·버전 규약)뿐

(이 결정은 다음 판 0.2.3 에서 되돌렸다. 그래도 이 판은 배포된 사실이라 그대로 둔다.)

## 0.2.2

`svkit-v` 접두사를 쓰는 첫 판이다(0.2.1 까지는 `v<버전>`).

- 문서 정비 — 소비자 목록을 실제(`git-worktree-web` 한 곳)로 바로잡고, 실체 없는
  배포 경로를 지웠다. 실증 근거로 적혀 있던 문장이 형제 저장소(kit-ui)의 실적이라
  자기 실적으로 바꿨다. "vendor 고정" 은 옛 채널명이라 "태그 tarball 고정" 으로
- `examples/minimal` 이 **배포물에 처음 들어간다.** 그 예제는 0.2.1 이후 태그 없이
  main 에만 있었고, 자기 requirements 는 `v0.2.1` 을 가리켰다 — 예제대로 설치하면
  그 예제가 없는 배포물을 받는 상태였다
- 공개 계약·코드 변경 없음(patch)

## 0.2.1

- 구조 정리 (내부 전용 — 공개 계약 변경 없음)
  - `__version__` 을 pyproject 와 동기화 (0.1.0 드리프트 수정), `__all__` 명시
  - PEP 561 `py.typed` 마커 추가 — 소비자 mypy/pyright 가 svkit 타입을 인식
  - pyproject 메타데이터 보강 (readme·license·classifiers), boto3 를 `svkit[s3]` extra 로 명시
  - 구 스켈레톤 잔재 표기 정리: `common.*`/`_base.*` 참조 문구, `app.registry` 로거 이름,
    `Flask("app")` 앱 이름 → svkit 기준으로 통일
  - `create_app` 의 미사용 import 제거

## 0.2.0

- bps 복수 등록·도메인 게이팅(`APP_ENABLED_DOMAINS`)·정적 SPA 서빙(`APP_STATIC_DIR`)·auth 조건 마운트

## 0.1.0

- sv-agent-team 스켈레톤 백엔드 코어(common/·_base/·registry·app 팩토리)를 pip 패키지로 분리
