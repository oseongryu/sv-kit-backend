# CHANGELOG

판은 semver. 브레이킹 체인지는 CONTRACT.md 의 **공개 계약**을 바꾸는 것을 말한다 —
내부(`_` 접두·로그 문구·파일 안 배치)는 판을 올리지 않는다.

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
