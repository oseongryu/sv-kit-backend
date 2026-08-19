# svkit — 백엔드 커널 킷

FastAPI 앱을 **도메인 모듈의 조합**으로 찍어내는 커널. 소비 앱은 모듈만 갖고, 앱을 조립하고
설정을 읽고 DB 를 여는 일은 이쪽이 한다.

실제로 운영되는 플랫폼의 백엔드에서 **도메인 지식이 없는 층만** 떼어 낸 것이다.
그래서 여기 있는 것은 전부 어느 앱에서든 그대로 도는 기계다.

## 영역

```
svkit/
  hooks.py       ★ 앱 고유값 주입 창구 — 킷이 앱을 아는 유일한 통로
  loader/        editions · domain · domain_meta · domain_hooks · conf
  web/           app · response · api · errors · reqctx · security · middleware · static · admin_key · casing · lifecycle
  db/            kernel · base · sqlite · postgres · backup
  infra/         jobs · storage · proxy · image_io · crypto · timez · serialize · env · logger · errors · warp
```

| 영역 | 무엇 |
|---|---|
| `loader` | 배포 변형 발견(`editions`)·모듈 선언 읽기(`domain`·`domain_meta`)·**공용층이 도메인 이름을 모르게 하는 훅 로더**(`domain_hooks`)·설정 창구(`conf`). 파이썬에서 `config/*.yml` 을 해석하는 유일한 곳 |
| `web` | 앱 조립·도메인 레지스트리·내장 인증·SPA 서빙(`app`), 봉투 규약(`response`), 라우터 팩토리(`api`), 요청 컨텍스트(`reqctx`), 해시·JWT(`security`), 요청 로깅·rate limit(`middleware`), 기동·정리 훅(`lifecycle`) |
| `db` | 커넥션 진입점·엔진 선택·백업. 스키마·질의는 앱 몫 |
| `infra` | 잡 레지스트리·스토리지(S3/로컬)·리버스 프록시·이미지 IO·Fernet·타임존·직렬화·env·로거·egress 프록시(`warp`) |

응답 본문은 `{ok, data, meta?}` / `{ok: false, error}` 다.

## 앱이 해야 할 일 — 주입 한 번

킷은 **소비 앱을 모른다.** import 하지 않고 문자열로도 가리키지 않는다. 그런데도 앱마다
달라지는 값은 `hooks` 한 곳에서 받는다.

```python
from svkit import hooks

hooks.register(
    app_root=BACKEND_ROOT,        # config 탐색·배선 발견·선언 읽기·DB 경로의 기준
    nav_seeder=seed_nav_pages,    # nav 표는 앱 저장소 소유 (선택)
    timezone="Asia/Seoul",        # 없으면 env SVKIT_TZ, 그것도 없으면 UTC
    log_dir=None,                 # 없으면 app_root/logs
)
```

`app_root` 만 기본값이 있을 수 없어 미설정 시 `RuntimeError` 다 — 조용히 엉뚱한 자리를
가리키면 빈 설정·빈 DB 로 떠서 한참 뒤에 드러난다. env `SVKIT_APP_ROOT` 로도 준다.

**한 컴포넌트의 동작 차이는 훅이 아니라 생성자 인자로 받는다** — rate limit 의 429 본문은
`RateLimitMiddleware(app, body=…)`, 잡 등록은 `Registry(name, job_cls=…)` 다.
전역으로 올리면 그 값을 쓰지 않는 소비처까지 함께 바뀐다.

## 무는 방법 — 발행 판을 pip 로

```
# requirements.txt
svkit @ https://github.com/oseongryu/sv-kit-backend/archive/refs/tags/svkit-v2.0.0.tar.gz
```

태그 tar.gz 를 그대로 문다. 공개 리포라 자격증명이 필요 없고, 소비 앱은 판을 그 한 줄로
고정한다. 킷을 고쳐 가며 쓸 때는 `pip install -e .` 로 붙인다.

소비처 코드는 `from svkit.web import create_app` 만 쓰고 킷 위치를 모른다.

### 앱 값 주입 — 부르는 자리는 앱 모듈 하나

`hooks.register(app_root=…)` 를 진입점마다 되풀이하지 않는다. 값이 필요한데 등록이 없으면
창구가 `SVKIT_BOOTSTRAP`(기본 `svkit_bootstrap`) 모듈을 **한 번** import 하므로, 앱은 그
이름의 모듈 하나에 등록을 모아 두면 된다 — 웹·pytest·`python -m`·워커가 모두 같은 값을 본다.
킷이 아는 것은 그 이름 하나이고 내용은 모른다. 값을 직접 등록하는 앱은 이 경로를 타지 않는다.

### 조각 여럿 — 한 이름공간, 여러 리포

**`__path__` 는 리스트라 조각이 여럿일 수 있다.** 이 리포는 **공개 커널 조각**이고, 소비 앱은
자기 조각을 같은 `svkit` 이름공간에 얹는다.

```
svkit.loader/web/db/infra   ← 이 리포 (pip, 필수)
svkit.<영역>                ← 추가 조각 (env SVKIT_PATH, 선택)
```

`SVKIT_PATH`(os.pathsep 구분)가 가리킨 디렉토리에 `svkit/` 이 있으면 그것이 조각이다.

규칙 하나: **조각끼리 이름(영역 디렉토리·최상위 모듈)이 겹치면 안 된다.** 겹치면 첫
조각이 이기고 뒤가 조용히 가려지므로 import 시점에 실패시킨다. 영역 이름이 곧 소유 선언이다.

> **예약된 이름** — `automation`·`browser`·`term` 은 이 커널을 만든 쪽의 비공개 조각이
> 쓰는 이름이다. 여기 없다고 새 조각에 그 이름을 붙이면 그 배포에서 충돌한다.

선택 조각은 앱이 `svkit.has("<영역>")` 으로 묻고 지연 import 한다 — **없으면 그 기능만
없고 앱은 뜬다.**

## 의존

`fastapi` 만 필수다(= `loader` + `web`). 나머지는 쓰는 영역만 깐다 —
`[postgres]`(sqlalchemy·psycopg, `infra.serialize` 도 그쪽) ·
`[infra]`(boto3·requests·cryptography·pillow·opencv·numpy) · `[yaml]`(없으면 평면 파서) ·
`[server]`(uvicorn). sqlite 전용 배포에 무거운 것이 딸려오지 않게 한 설계다.

## 여기 없는 것

**킷은 범용 기계만 갖는다.** 소비 앱의 기능은 — 여러 모듈이 공유하더라도 — 앱에 남는다.
"공유한다"와 "범용이다"는 다른 축이고, 앞의 것을 뒤의 것으로 읽으면 앱 도메인이 킷으로
넘어온다(실제로 한 번 그랬다: 프로필·계정 스택, 마트 ORM 모델, 통합 인증 연동).

판정은 CONTRACT.md 의 원칙으로 한다 — 업무 용어·테이블·외부 서비스 이름이 코드에
드러나면 앱 것이고, 그 외의 결합(설정 이름·응답 형식·경로·정책)은 **주입으로 끊어 킷에
남긴다.** 결합을 이유로 범용 기계를 내리는 것은 답이 아니다 — 같은 것을 두 번 만들게
된다(`web.middleware`·`infra.timez` 가 그렇게 나갔다 돌아왔다).

## 라이선스

MIT — `LICENSE` 를 본다.
