"""백엔드 공용 로거 — 모듈 코드는 `print` 대신 이걸 쓴다. 스크립트는 예외다.

**핸들러를 여기서 보장한다.** 맨 `logging.getLogger` 만 쓰면 루트에 핸들러가 없을 때
INFO 가 조용히 버려진다 (lastResort 핸들러는 WARNING 이상만 낸다).
"""
import logging
import os
import sys
from svkit.loader import conf

_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    level = getattr(logging, conf.get_str("APP_LOG_LEVEL").upper(), logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(handler)
    # 루트 기본 레벨은 WARNING 이다 — 그대로 두면 info() 가 버려진다.
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """`log = get_logger(__name__)`. 메시지는 한국어로 짧게, 포매팅은 `%s` 지연 인자로."""
    _configure()
    return logging.getLogger(name)


def setup_file_logging(filename: str = "server.log", log_dir: str = "") -> str:
    """파일 로깅 — uvicorn 로거까지 같은 핸들러로 모은다.

    `log_dir` 생략 시 앱 루트 밑 `logs/`.
    """
    from logging.handlers import RotatingFileHandler

    from svkit import hooks

    log_dir = log_dir or str(hooks.log_dir())
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, filename)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(fmt)
    handler.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.INFO)

    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.addHandler(handler)
    logging.getLogger("").addHandler(console)

    print(f"로그 파일: {path}")
    return path


def quiet_loggers(*names: str, level: int = logging.WARNING) -> None:
    """지정 로거의 레벨을 올려 주기성 INFO 소음을 줄인다 — 경고·오류는 그대로 남는다."""
    for name in names:
        logging.getLogger(name).setLevel(level)


class _AccessPathFilter(logging.Filter):
    """지정 경로의 성공(2xx) 접근 로그만 걸러낸다 — 실패 응답은 남긴다."""

    def __init__(self, paths: tuple) -> None:
        super().__init__()
        self._needles = tuple(f" {p} " for p in paths)

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if not any(n in msg for n in self._needles):
            return True
        return '" 2' not in msg


def mute_access_logs(*paths: str, logger_name: str = "uvicorn.access") -> None:
    """지정 경로의 성공 접근 로그를 억제한다 — 헬스체크류 주기 호출 전용.

    계약: 경로는 쿼리 없는 요청 경로 그대로 일치하고, 2xx 만 걸러 실패는 로그에 남는다.
    """
    logging.getLogger(logger_name).addFilter(_AccessPathFilter(paths))
