# svkit 공개 계약 (CONTRACT)

svkit 를 고치는 사람(사람이든 에이전트든)을 위한 경계 선언이다.
**공개 계약**을 바꾸면 소비자가 깨진다. **내부**는 계약만 지키면 자유다.

> **2.0.0 은 새 루트다.** 공개 범위를 다시 그으면서 이력을 재시작했고, 공개 영역은
> `loader`·`web`·`db`·`infra` 넷이다. 이전 판의 계약은 여기 남기지 않는다 — 지금 코드와
> 정면으로 배치돼 다음 사람을 오도하기 때문이다.

## 설계 원칙

1. **FastAPI 전용이다.** 프레임워크 중립층을 만들지 않는다 — 0.x 에서 시도했다가
   코드가 2배가 되고 FastAPI 의 강점(response 스키마·`Depends`·BackgroundTasks)을
   구조적으로 포기하게 됐다.
2. **핸들러는 동기 `def` 가 기본이다.** subprocess·sqlite 가 전부 동기라 FastAPI 가
   스레드풀로 내려 주는 쪽이 맞다. async 를 어중간하게 섞지 않는다.
3. **커널은 도메인 지식을 갖지 않는다.** 업무 용어·테이블 이름·외부 서비스 이름이
   코드에 드러나면 그것은 앱 것이다. 이 리포에 들어오면 안 된다.
   **"여러 모듈이 공유한다"는 근거가 되지 못한다** — 앱 안에서 공유되는 것과 어느 앱이든
   쓰는 것은 다르다. 후자만 킷이다.
4. **그 외의 결합은 주입으로 끊고 킷에 남긴다.** 설정 이름·응답 형식·경로·정책 때문에
   범용 기계를 앱으로 내리지 않는다 — 내리면 같은 것을 두 번 만들게 된다. 실제로 한 번
   내렸다가(`web.middleware`·`infra.timez`) 이 원칙을 세우고 되가져왔다.
5. **커널은 앱을 import 하지 않는다 — 문자열로도 가리키지 않는다.** 지연 import 경로를
   문자열에 적으면 정적 검사를 빠져나가지만 그 모듈이 없는 배포에서는 똑같이 깨진다.
6. **주입 창구는 `hooks` 하나다.** 앱 전역에 걸리는 값만 여기 둔다 — `app_root`·
   `nav_seeder`·`timezone`·`log_dir`. **한 컴포넌트의 동작 차이는 생성자 인자로 받는다**
   (`RateLimitMiddleware(app, body=…)`·`Registry(name, job_cls=…)`). 전역으로 올리면
   그 값을 쓰지 않는 소비처까지 함께 바뀐다.
7. **이 리포는 조각 하나다.** 소비 앱은 같은 `svkit` 이름공간에 자기 조각을 더 얹을 수
   있다(`__path__` 가 리스트라서). 그래서 **영역 이름은 조각 간 소유 선언**이다.
   이 리포가 갖는 것: `loader`·`web`·`db`·`infra`·`hooks`.
   **`automation`·`browser`·`term` 은 이 커널을 만든 쪽의 비공개 조각이 쓰는 예약어**라
   여기 없어도 새로 만들지 않는다. 영역을 더할 때는 두 목록 어느 쪽과도 안 겹치는지 본다.
8. **영역이 곧 의존 등급이다.** `loader`+`web` 은 fastapi 하나로 돌고, `db`(postgres)·
   `infra`(boto3·cryptography·opencv…)는 extra 로 갈린다. 영역을 넘어 의존을 만들 때는
   그 등급이 오르지 않는지 본다 — 오르면 그것을 안 쓰던 배포까지 무거워진다.
   `web`·`db` 가 `infra` 에서 부르는 것이 `logger`·`errors` 둘뿐인 것도 이 규율이다.
9. **무거운 의존은 지연 해석한다.** sqlite 전용 배포에 sqlalchemy 가 딸려오면 안 된다 —
   `db/__init__.py` 의 `__getattr__` 이 postgres 심볼만 늦게 푼다. 이 성질을 깨지 말 것.

## 공개 계약 (바꾸면 소비자가 깨진다)

### 응답 봉투
- 성공 `{"ok": true, "data": …, "meta"?: …}` / 실패 `{"ok": false, "error": …}`
- 라우트 클래스가 자동으로 감싼다 — 호출부가 손으로 `ok()` 를 부르지 않는다.
- 프론트 킷(`@sv/kit-ui`)이 같은 형태를 판정한다. 한쪽만 바꾸지 않는다.

### env 이름
`APP_DOMAIN_PACKAGES` · `APP_DB_PATH` · `APP_STATIC_DIR` · `APP_CONFIG_DIR` ·
`SVKIT_APP_ROOT` · `EDITION`(구 `FLAVOR`) · `AUTH_ENABLED` · `APP_LOG_LEVEL` ·
`APP_LOG_DIR`(파일 로깅 자리 — 없으면 앱 루트 밑 `logs/`).
기존 DB·compose·배포 스크립트가 이 이름들을 물고 있다.

### 인증 — 자리는 하나, 출처가 셋

`Authorization: Bearer <토큰>` 한 줄이고, 받는 쪽은 출처를 구분하지 않고 `role` 만 본다.

| 주체 | 발급 | role | 지문 | 만료 |
|---|---|---|---|---|
| 사람 | `POST /api/auth/login`(아이디·비번) | `admin`·`viewer` | 없다 | `JWT_TTL` |
| 앱 | `POST /api/auth/device`(공유 시크릿 `APP_DEVICE_SECRET`) | `app` | device_id+UA | `APP_TOKEN_TTL` |
| 기계 | 설정 고정값(`ADMIN_API_KEY`·`ADMIN_TOKEN`) | — | 없다 | 없다 |

- 게이트(`AuthGateMiddleware`)의 축은 **경로 접두**다 — `admin` 접두는 role=admin 만
  지나간다. 관리 동작을 `/api/<slug>/` 아래 두면 앱 토큰이 그것을 지나간다.
- 옛 헤더 `X-Admin-Key`·`X-Admin-Token` 은 **계속 받는다**(운영 스크립트 무중단).
  새로 쓰는 쪽은 Bearer 하나다.
- **지문이 어긋나도 즉시 막지 않는다** — 첫 요청에서 끊으면 무엇이 걸렸는지 드러나
  UA 만 바꿔 맞출 수 있다. 기기마다 다른 유예 뒤 확률적으로 막고, 램프를 다 지나면
  확정 차단한다(`APP_TOKEN_GRACE_MIN`~`MAX`·`APP_TOKEN_DECAY_HITS`). 판정은
  `device_id`+횟수 해시라 서버는 재현할 수 있고 밖에서는 무작위로 보인다.
- **거절 문구는 무토큰과 같다**(`인증 필요`). 사유는 서버 로그만 갖는다 — 오탐(정상
  사용자의 UA 변경)과 실제 도용을 운영자가 구분할 수 있어야 한다.
- **IP 는 지문에 넣지 않는다** — 모바일은 셀↔WiFi 전환·캐리어 NAT 로 수시로 바뀐다.
- 지문의 클라이언트 값은 **`X-App-Client` 가 먼저이고 없으면 UA** 다. UA 는 OS·웹뷰가
  좌우해 앱이 통제할 수 없다 — 그것으로 지문을 잡으면 OS 업데이트 한 번에 전 사용자가
  걸린다. 앱은 그 헤더에 **버전을 담지 않은 고정 문자열**을 보낸다.
- 표 `auth_user`(사람)·`auth_device`(기기)는 커널 소유다 — 도메인이 `tables` 로 선언하지 않는다.

### 부팅 순서
`setup_env()`(APP_* env 주입) → `create_app()` → `run_dev()`. env 는 **함수 안에서**
읽는다 — 모듈 로드 시점에 굳으면 이 순서가 깨진다.

### 모듈 훅 — 켜진 모듈만 이름으로 발견한다
`domain_hooks.load("<훅>")` 이 `APP_DOMAIN_PACKAGES` 의 모듈에서 `module_<x>/<훅>.py` 를
찾는다. 커널이 읽는 훅은 둘이다 — `service_lifecycle`(`on_startup`/`on_shutdown`,
`create_service_app` 의 lifespan 이 돌린다)과 `service_asgi`(`MOUNT_PATH` + `build_app()` —
도메인 라우터가 아닌 **독립 ASGI 앱 모듈**을 그 접두에 마운트하고, mount 는 하위 lifespan
을 돌리지 않으므로 호스트 lifespan 에 잇는다). 이 둘이 "나눠 배포하거나 합쳐 배포하거나"
를 성립시키는 면이다 — 모듈은 edition 배선 없이 `MODULES` 목록만으로 선다.

### 선언 읽기는 AST 로
`editions.declared_modules()` · `domain_meta.read()` · `conf._capability_names()` 는 대상 파일을
**import 하지 않는다**. env 가 깔리기 전에 돌아야 하고, 한 인터프리터에 edition 을 둘
로드하지 않기 위해서다. 그래서 `MODULES`·`DOMAIN` 은 **리터럴만** 쓴다.

### 설정 창구의 공개 면 넷
`get_*`/`require` · `expand(text, values=None, use_env=True)` ·
`all_values(on_conflict=None)` · `as_env(values)`. 새 소비처는 이 넷 중 하나를 부른다.
우선순위는 `os.environ` > `local.yml` > `<edition>.yml` > `<기능>.yml` > `common.yml`.

### 정적 SPA 서빙 — 구현은 `web/static.py:mount_spa` 하나다

`APP_STATIC_DIR` 이 가리키는 Next static export 를 같은 오리진에서 서빙한다. 커널
`create_app(static=True)` 이 이것을 부르고, 커널 catch-all 을 끈 배포는 자기
`create_app` 맨 마지막에 직접 부른다 — **두 벌로 두지 않는다**(규칙이 한쪽에만 빠져
`/login/` 직접 진입이 루트 문서를 받는 결함이 났다).

- 해석 순서는 `{p}` 실제 파일 → `{p}.html`(trailingSlash 를 끈 계보) →
  `{p}/index.html`(trailingSlash 계보). **세 계보를 한 구현이 다 받는다.**
- **없는 경로는 404 다** — index 폴백을 두지 않는다. static export 는 동적 세그먼트까지
  `generateStaticParams` 로 전부 파일이 되므로 폴백으로 살릴 경로가 없고, 두면 GET 으로
  부른 POST 전용 API 까지 200 + HTML 이 되어 호출부가 실패를 성공으로 읽는다.
- `index.html` 이 없으면 `False` 를 돌려주고 아무것도 등록하지 않는다 — 프론트를 빌드하지
  않아도 API 는 뜬다. 호출부는 그 반환으로 대체 루트를 단다.

### DB 배럴
`db` 는 커넥션 진입점(`connect`·`get_conn`·`get_db`·`DB_PATH`·`table_counts`)과 엔진
선택(`SqliteDB`, postgres 지연 해석)만 노출한다. **표에 없는 이름은 반드시
`AttributeError`** — 서브모듈 import 가 그 폴백 경로다.

**`get_db()` 는 `connect()` 의 동의어이고 새 소비처는 쓰지 않는다** — 같은 뜻의 이름이
둘이면 소비가 갈리고, 뜻이 다른 `get_conn()`(commit/close 컨텍스트)과 혼동된다.
기존 외부 소비처를 위해 공개 면에만 남긴다.

**`DB_PATH` 는 접근 시점에 풀린다** — `APP_DB_PATH` 가 단일 소스라는 말의 뜻이 그것이다.
모듈 상수로 굳히면 `svkit.db` 를 먼저 import 한 쪽이 이겨, 그 뒤에 env 를 세워도 무시된
채 엉뚱한 파일을 문다(계약 테스트가 공유 `db/app.db` 를 물어 상태를 누적시킨 적이 있다).
그래서 **값을 이름으로 가져가 두지 않는다**: `from svkit.db import DB_PATH` 는 그 순간을
고정하므로 `from svkit import db` 후 `db.DB_PATH` 로 읽고, 커널 안에서는 함수
`svkit.db.base.db_path()` 를 부른다(함수 안 전역 조회는 모듈 `__getattr__` 을 타지 않는다).
배럴도 값을 `globals()` 에 캐시하지 않는다.

### SQL 선언 매퍼 — `db/mapper.py` + `loader/domain_queries.py`

앱이 SQL 을 XML 로 빼 두면 커널이 그것을 읽어 `(sql, binds)` 를 만든다. **커널은 그
SQL 이 무엇을 뜻하는지 모른다** — 태그 문법과 렌더 규칙만 갖는다.

- 문법은 MyBatis 부분집합이다: `<sql>`·`<include refid>`·`<if test>`·`<choose/when/
  otherwise>`·`<where>`·`<set>`·`<trim>`·`<foreach>`. 최상위는 `<sql>` 과 문장 넷
  (`select`·`insert`·`update`·`delete`)뿐이고 `<mapper namespace>` 가 이름공간이다.
- **`#{name}` 은 바인드, `${name}` 은 치환**이다. 치환은 식별자 모양만 통과한다 —
  SQL 조각을 그리로 실어 나르면 인젝션 통로가 되므로, 조각은 `<include>` 로 적는다.
- **`<include>` 는 지점마다 `<property name value>` 로 값을 준다** — 한 문장이 같은
  조각을 다른 식으로 여럿 끼울 때 쓴다(MyBatis 와 같다). 값은 그 include 를 렌더하는
  동안만 살고, `${}` 식별자 가드는 property 값에도 그대로 걸린다.
- **`<foreach>` 는 Mapping 을 (키, 값) 으로 돈다** — `index` 가 위치가 아니라 키다
  (MyBatis 와 같다). 목록이면 `index` 는 그대로 정수 위치다. 컬럼 **수·이름**이 사전에서
  나오는 집계가 이것으로 펴진다.
- **`test` 는 파이썬 부분집합**이다(비교·논리·`in`·`null`→None). 호출·속성·구독은
  파싱 단계에서 `MapperError` 다. `null` 만 MyBatis 어휘를 받아 준다.
- **파일 목록도 mtime 도 호출 시점에 다시 본다.** 목록을 굳히면 늦게 로드된 모듈의
  선언이 통째로 빠지고, mtime 을 안 보면 선언을 고쳐도 프로세스를 다시 띄우기 전까지
  옛 SQL 이 돈다.
- `domain_queries` 는 **켜진 모듈의 `feature/feature_query_*.xml` 을 이름으로 거둔다** —
  `domain_globals` 와 같은 방식이라 새 모듈을 더할 때 고칠 목록이 없다. 모듈 위치는
  `find_spec` 으로 얻고 **import 하지 않는다**(선언 실행은 로더의 일이 아니다).
- 자기 자산 하나만 읽는 모듈은 레지스트리를 거치지 않고 `SqlMapper([경로])` 를 직접
  만든다 — 모듈 자산의 앵커는 그 모듈이 갖는다는 규약 그대로다.

### 호스트 파이썬 경로

`loader` 영역(+`hooks`·패키지 `__init__`)은 **컨테이너 밖 호스트에서도 도는 경로**다 —
소비 앱의 `.env` 생성이 호스트 파이썬으로 설정 창구를 부르는데, 그 파이썬은 3.10 미만일
수 있다. 그래서 이 넷은 **3.10 전용 런타임 문법을 쓰지 않는다**:

- 모듈 수준 주석이 로드 시점에 평가되지 않게 `from __future__ import annotations` 를 둔다
  (`_CACHE: dict | None = None` 이 그대로 평가돼 `TypeError` 로 죽은 적이 있다)
- `match` 문·`isinstance(x, A | B)` 처럼 **주석이 아닌 자리**의 신문법을 쓰지 않는다
- import 는 stdlib 과 `svkit.hooks` 까지다 — 여기서 다른 영역을 끌면 그 의존이 호스트로 번진다

다른 영역(`web`·`db`·`infra`)은 이미지 안에서만 도므로 그대로 3.10+ 다.
`requires-python` 은 pip 설치 기준이라 `>=3.10` 을 유지한다.

## 내부 (자유롭게 고쳐도 되는 것)

`_` 접두 함수, 로그 문구, 예외 메시지, 파일 안 배치. 단 공개 면의 시그니처와 위
계약들은 그대로 둔다.
