# CHANGELOG

판은 semver. 브레이킹 체인지는 CONTRACT.md 의 **공개 계약**을 바꾸는 것을 말한다 —
내부(`_` 접두·로그 문구·파일 안 배치)는 판을 올리지 않는다.

## 2.3.0

상류(sv-platform `backend/svkit/`) 스냅샷 동기.

- **SQL 매퍼 확장** — `<include>` 가 지점별 `<property name value>` 를 받는다(값은 그
  include 렌더 동안만 살고 `${}` 식별자 가드가 property 값에도 걸린다).
  `<foreach>` 가 Mapping 을 (키, 값)으로 돈다 — `index` 가 위치가 아니라 키다.
  둘 다 MyBatis 와 같은 의미론이고 기존 선언은 무영향이다.

## 2.2.0

상류(sv-platform `backend/svkit/`) 스냅샷 동기.

- **SQL 선언 매퍼 신설** — `db/mapper.py`(MyBatis 부분집합 XML 을 읽어 `(sql, binds)` 를
  만든다. `#{}` 바인드 / `${}` 식별자 치환, `test` 는 파이썬 부분집합, mtime 재로드) +
  `loader/domain_queries.py`(켜진 모듈의 `feature/feature_query_*.xml` 을 이름으로 집결 —
  `find_spec` 만 쓰고 import 하지 않는다).
- **도메인 상수 집결 신설** — `loader/domain_globals.py`: 모듈별 `globals.py` 의 대문자
  상수를 한 자리에서 본다. 새 모듈은 파일 하나를 두면 합류한다.
- **앞단 프록시 등록 창구 신설** — `infra/edge.py`: 프록시 file provider 디렉토리를
  소유하고 `GET/PUT/DELETE /api/routes[/{name}]` 로 연다(라우트 하나 = 파일 하나).
  쓰기는 `EDGE_API_TOKEN` 필수 — 비면 등록을 받지 않는다(503).
- **인증 게이트 확장** — WebSocket 도 게이트를 탄다(타입으로 빼면 무인증 채널이 생긴다).
  사람 토큰 슬라이딩 갱신(`X-Auth-Token` 응답 헤더, `JWT_RENEW_BEFORE`)과 게이트 401
  표식(`X-Auth-Reject: gate`)을 더했고, `infra/proxy` 는 업스트림 응답의 같은 헤더를
  걷어낸다. `web/security.py` 에 `renew_token(payload, ttl)` 추가.
- **정적 SPA 서빙 단일화** — `web/static.py:mount_spa` 가 `{p}` 실제 파일 → `{p}.html` →
  `{p}/index.html` 세 계보를 한 구현으로 받고, **없는 경로는 404** 다(index 폴백 폐기 —
  GET 으로 부른 POST 전용 API 가 200 + HTML 이 되던 통로를 막았다).
- **라우터 발견 확장** — 모듈 루트의 `api*.py` 에 더해 `api/` 패키지 하위 `api_*.py` 도
  라우터로 거둔다(`loader/domain.py:_api_names`).
- `db/kernel.py` 에 `relocate(old, new)` — 커넥션이 열리기 전 DB 파일 자리 이동
  (WAL 사이드카 한 벌, 멱등, 새 자리에 파일이 있으면 손대지 않는다).
- `loader/{conf,domain_hooks}`·`web/{app,admin_key}` 상류 개선 반영(공개 계약 불변).
- CONTRACT.md — 인증(출처 셋: 사람·앱·기계), 모듈 훅(`service_lifecycle`·`service_asgi`),
  정적 SPA, SQL 매퍼, `get_db()` 동의어, `APP_LOG_DIR` 조항 추가.

## 2.1.0

상류(sv-platform `backend/svkit/`) 스냅샷 동기.

- **`DB_PATH` 접근 시점 해석** — 모듈 상수 고정을 PEP 562 `__getattr__` 로 바꿨다.
  공개 면(이름·`AttributeError` 계약)은 그대로이고, `from svkit.db import DB_PATH` 로
  값을 가져가 두는 소비처만 영향을 받는다(그 순간 값이 고정된다 — CONTRACT.md 의
  새 조항대로 속성 접근으로 읽을 것). 커널 내부 헬퍼 `svkit.db.base.db_path()` 추가.
- `web/device.py` 신설 — 기기 토큰 지문(앱 선언 헤더 기반) 검증과 유예·차단 누적.
- `web`(admin_key·app·casing·middleware·security)·`db/backup`·`infra/logger`·`hooks`
  상류 개선 반영(공개 계약 불변).

## 2.0.0

**새 루트다.** 공개 범위를 다시 긋고 이력을 재시작했다. 이전 판들의 태그와 이력은
이 리포에 없다.

### 공개 영역은 넷이다

`loader` · `web` · `db` · `infra` (+ 주입 창구 `hooks`).

`automation`(선언 기반 실행 엔진)·`browser`(컨테이너 브라우저 호스팅)·`term`(PTY 브리지)은
공개하지 않는다. 그 셋은 커널을 **쓰는** 쪽이라 빠져도 여기가 깨지지 않는다 —
의존은 `automation → term·infra·browser`, `browser → web·loader·db` 한 방향이었다.

**그 이름들은 예약어로 남긴다.** 조각 기계가 한 영역을 두 조각이 가지면 import 시점에
실패시키므로, 여기 없다고 새 조각에 그 이름을 붙이면 그 배포에서 충돌한다.

### 알아 둘 것

- `svkit @ https://github.com/oseongryu/sv-kit-backend/archive/refs/tags/svkit-v2.0.0.tar.gz`
- 옛 태그(`v0.*`·`svkit2-v*`·`svkit-v1.*`)는 전부 사라졌다. 그 URL 을 문 매니페스트는
  이 판으로 올린다
- 응답 봉투 `{ok, data, meta?}` / `{ok: false, error}` 와 env 이름
  (`APP_DOMAIN_PACKAGES`·`APP_DB_PATH`·`APP_STATIC_DIR`·`SVKIT_APP_ROOT`·`EDITION` …)은
  이전 판과 같다 — 기존 DB·compose·배포 스크립트는 그대로 문다
