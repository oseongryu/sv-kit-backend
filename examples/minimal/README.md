# svkit 최소 예제 — 백엔드 단독 실행

프론트 없이 svkit 만으로 API 서버를 띄우는 최소 구성. 파일 3개가 전부다:

```
app.py                      # from svkit import create_app 두 줄
requirements.txt            # GitHub 태그 고정 설치
domains/hello/__init__.py   # 도메인 모듈 1개 (bp + schema + seed)
```

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## 확인

```bash
curl http://localhost:5000/api/health        # 도메인 목록 포함 상태
curl http://localhost:5000/api/hello/items   # 시드된 아이템 3건
```

## 도메인을 늘리려면

`domains/<slug>/__init__.py` 를 추가하고 모듈 전역 `DOMAIN` dict 만 노출하면
재기동 시 자동 등록된다. 스키마 테이블은 `<slug>_` 접두를 지킨다.
인프라(auth·queue·scheduler·storage 등)는 전부 env 로 켜는 opt-in — 기본은 무동작.
자세한 규약은 저장소 루트 README·CONTRACT 참조.
