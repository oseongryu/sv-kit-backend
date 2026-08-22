# CHANGELOG

판은 semver. 브레이킹 체인지는 CONTRACT.md 의 **공개 계약**을 바꾸는 것을 말한다 —
내부(`_` 접두·로그 문구·파일 안 배치)는 판을 올리지 않는다.

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
