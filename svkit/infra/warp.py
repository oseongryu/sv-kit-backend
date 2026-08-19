"""egress 프록시(Cloudflare WARP) 창구 — 어느 도메인도 모른다.

전부 호출 시점에 평가한다. 모듈 상수로 굳히면 런타임 토글이 먹지 않는다.
"""
import socket
import subprocess
import time
from urllib.parse import urlparse, urlsplit

from svkit.loader import conf


def is_enabled() -> bool:
    return conf.get_bool("USE_WARP", False)


def socks_proxy() -> str:
    return conf.get_str("WARP_PROXY", "")


def http_proxy() -> str:
    return conf.get_str("WARP_HTTP_PROXY", "")


def local_proxy() -> str:
    return conf.get_str("WARP_PROXY_LOCAL", "")


def hosts() -> list[str]:
    return [h.strip().lower().lstrip(".") for h in conf.get_list("WARP_HOSTS") if h.strip()]


def applies_to(url: str | None = None) -> bool:
    """이 url 을 경유시킬지. WARP_HOSTS 가 비었거나 url 이 없으면 is_enabled() 그대로."""
    if not is_enabled():
        return False
    allow = hosts()
    if not allow or not url:
        return True
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in allow)


def requests_proxies(url: str | None = None) -> dict | None:
    """requests·curl_cffi 의 `proxies=` 인자. 대상이 아니면 None."""
    p = socks_proxy()
    if not (applies_to(url) and p):
        return None
    return {"http": p, "https": p}


def ffmpeg_args(url: str | None = None) -> list[str]:
    """ffmpeg 인자 조각. socks5 를 못 먹으므로 http 프록시만 쓴다."""
    p = http_proxy()
    if not (applies_to(url) and p):
        return []
    return ["-http_proxy", p]


def playwright_proxy(url: str | None = None) -> dict | None:
    """playwright `launch(proxy=…)` 값. 대상이 아니면 None."""
    p = socks_proxy()
    if not (applies_to(url) and p):
        return None
    return {"server": p}


# ── 스크립트 채널 — 모드 해석(auto|on|off)·컨테이너 제어 ─────────────────────
# 값은 `WARP_MODE`(이름만 선언 — 호출자별 기본이 있다)·`WARP_PROXY_URL`.
# 위의 USE_WARP 계열(런타임 opt-in)과 별개 채널이다 — 합치지 않는다.
MODES = ('auto', 'on', 'off')
DEFAULT_URL = 'socks5h://localhost:1080'
CONTAINER = 'warp'


def compose_file() -> str:
    """warp 사이드카 compose fragment 경로(`WARP_COMPOSE_FILE`).

    비면 컨테이너를 새로 만들지 않는다 — 파일 위치는 배포의 리포 레이아웃이라
    킷이 도출하지 않는다.
    """
    return conf.get_str('WARP_COMPOSE_FILE').strip()


def default_url() -> str:
    return conf.get_str('WARP_PROXY_URL') or DEFAULT_URL


def default_mode(fallback: str = 'auto') -> str:
    mode = conf.get_str('WARP_MODE').strip().lower()
    return mode if mode in MODES else fallback


def _hostport(url: str) -> tuple[str, int]:
    p = urlparse(url)
    return (p.hostname or 'localhost'), (p.port or 1080)


def is_up(url: str = '', timeout: float = 1.0) -> bool:
    """프록시 포트 접속 가능 여부(빠른 TCP 확인)."""
    host, port = _hostport(url or default_url())
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── 컨테이너 제어 ────────────────────────────────────────
def _docker(*args, timeout: int = 120) -> tuple[int, str]:
    try:
        p = subprocess.run(('docker',) + args, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return p.returncode, (p.stdout or p.stderr or '').strip()


def container_state() -> str:
    """running | exited | created | '' (컨테이너 없음/도커 미가용)."""
    code, out = _docker('inspect', '-f', '{{.State.Status}}', CONTAINER, timeout=20)
    return out if code == 0 else ''


def start_container(wait: float = 25.0, url: str = '') -> bool:
    """기존 warp 컨테이너면 start, 없으면 독립 compose 로 생성."""
    state = container_state()
    if state == 'running':
        return _wait_up(wait, url)
    if state:
        code, out = _docker('start', CONTAINER, timeout=60)
    else:
        fragment = compose_file()
        if not fragment:
            print('워프 컴포즈경로 미설정')
            return False
        code, out = _docker('compose', '-f', fragment, 'up', '-d', timeout=300)
    if code != 0:
        print(f'워프 기동실패 {out.splitlines()[-1] if out else ""}')
        return False
    return _wait_up(wait, url)


def stop_container() -> bool:
    if not container_state():
        return True
    code, out = _docker('stop', CONTAINER, timeout=60)
    if code != 0:
        print(f'워프 중지실패 {out.splitlines()[-1] if out else ""}')
    return code == 0


def _wait_up(wait: float, url: str = '') -> bool:
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_up(url):
            return True
        time.sleep(1.0)
    return is_up(url)


# ── argparse 연동 ────────────────────────────────────────
def add_args(parser, default: str = 'auto') -> None:
    """`--warp` / `--warp-url` / `--no-warp-start` 등록."""
    parser.add_argument('--warp', choices=MODES, default=default_mode(default),
                        help=f'WARP 경유 방식 (기본 {default_mode(default)})')
    parser.add_argument('--warp-url', default=default_url(), help='프록시 주소')
    parser.add_argument('--no-warp-start', action='store_true',
                        help='on 모드에서 컨테이너 자동 기동 안 함')


def resolve(args, required: bool = False) -> str | None:
    """옵션 → 프록시 URL 또는 None(직접 연결). on 실패 시 SystemExit."""
    legacy = getattr(args, 'proxy', '')
    if legacy:                      # 구 --proxy 지정 시 그대로 존중(생존확인 생략)
        print(f'프록시 지정 {legacy}')
        return legacy
    mode = getattr(args, 'warp', None) or default_mode()
    url = getattr(args, 'warp_url', '') or default_url()
    autostart = not getattr(args, 'no_warp_start', False)
    return resolve_mode(mode, url, autostart=autostart, required=required)


def resolve_mode(mode: str, url: str = '', autostart: bool = True,
                 required: bool = False) -> str | None:
    url = url or default_url()
    if mode == 'off':
        print('워프 미사용')
        return None
    if is_up(url):
        print(f'워프 경유 {url}')
        return url
    if mode == 'auto' and not required:
        print('워프 미가용 직접연결')
        return None
    if autostart:
        print('워프 기동')
        if start_container(url=url):
            print(f'워프 경유 {url}')
            return url
    raise SystemExit('워프 미가용 — 기동 후 재시도하거나 --warp off')


def as_requests(url: str | None) -> dict | None:
    """requests 용 proxies 딕셔너리."""
    return {'http': url, 'https': url} if url else None
