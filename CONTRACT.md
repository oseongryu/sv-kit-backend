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
`SVKIT_APP_ROOT` · `EDITION`(구 `FLAVOR`) · `AUTH_ENABLED` · `APP_LOG_LEVEL`.
기존 DB·compose·배포 스크립트가 이 이름들을 물고 있다.

### 부팅 순서
`setup_env()`(APP_* env 주입) → `create_app()` → `run_dev()`. env 는 **함수 안에서**
읽는다 — 모듈 로드 시점에 굳으면 이 순서가 깨진다.

### 선언 읽기는 AST 로
`editions.declared_modules()` · `domain_meta.read()` · `conf._capabilities()` 는 대상 파일을
**import 하지 않는다**. env 가 깔리기 전에 돌아야 하고, 한 인터프리터에 edition 을 둘
로드하지 않기 위해서다. 그래서 `MODULES`·`CAPABILITIES`·`DOMAIN` 은 **리터럴만** 쓴다.

### 설정 창구의 공개 면 넷
`get_*`/`require` · `expand(text, values=None, use_env=True)` ·
`all_values(on_conflict=None)` · `as_env(values)`. 새 소비처는 이 넷 중 하나를 부른다.
우선순위는 `os.environ` > `local.yml` > `<edition>.yml` > `<기능>.yml` > `common.yml`.

### DB 배럴
`db` 는 커넥션 진입점(`connect`·`get_conn`·`get_db`·`DB_PATH`·`table_counts`)과 엔진
선택(`SqliteDB`, postgres 지연 해석)만 노출한다. **표에 없는 이름은 반드시
`AttributeError`** — 서브모듈 import 가 그 폴백 경로다.

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
