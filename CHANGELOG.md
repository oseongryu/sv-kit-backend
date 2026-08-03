# Changelog

svkit 의 모든 소비자 영향 변경을 기록한다. 형식은 Keep a Changelog, 버전은 semver(0.x).
태그는 `svkit-v<버전>` — **다음 발행부터**다. 0.2.1 까지는 `v<버전>` 으로 나갔고 그 태그들은
옮기지 않는다(소비자 requirements 가 그 URL 을 가리킨다).

항목은 **무엇을 왜** 로 적는다. "무엇" 만 남으면 다음 사람이 그 결정을 되돌려도 되는지
판단할 수 없다 — 아래 0.2.0·0.1.0 이 그렇게 남아 있다(소급해 지어내지 않고 그대로 둔다).

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
