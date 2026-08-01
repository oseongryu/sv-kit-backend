# Changelog

svkit 의 모든 소비자 영향 변경을 기록한다. 형식은 Keep a Changelog, 버전은 semver(0.x).

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
