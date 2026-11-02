"""DB 스냅샷 백업·복원 — DB 를 볼륨에 두고 사본만 호스트에 남기는 배포용.

기동 시 복원(`restore_if_missing`)은 **첫 connect() 보다 먼저** 불러야 한다 —
sqlite3 는 없는 파일을 빈 DB 로 만들어 버린다.
"""
import glob
import os
import shutil
import signal
import sqlite3
import threading
import time
from datetime import datetime

from svkit.loader import conf
from svkit.db.base import connect, db_path
from svkit.infra.logger import get_logger

log = get_logger(__name__)

_backup_thread_started = False


def backup_dir() -> str:
    return conf.get_str("APP_BACKUP_DIR") or os.path.join(os.path.dirname(str(db_path())), "backup")


def _prefix() -> str:
    return os.path.basename(str(db_path())).rsplit(".", 1)[0]


def backup() -> str:
    """스냅샷 하나를 남기고 오래된 것을 정리한다. 반환: 백업 파일 경로.

    임시 파일에 받은 뒤 원자적으로 이름을 바꾼다 — 잘린 파일이 '최신 백업'으로
    잡히면 복원이 빈 DB 를 되살린다.
    """
    bak_dir = backup_dir()
    os.makedirs(bak_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_path = os.path.join(bak_dir, f"{_prefix()}_{ts}.db")
    tmp_path = f"{bak_path}.tmp{os.getpid()}"
    src = connect()
    try:
        dst = sqlite3.connect(tmp_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
        os.replace(tmp_path, bak_path)
    finally:
        src.close()
        for leftover in (tmp_path, f"{tmp_path}-journal"):
            try:
                os.remove(leftover)
            except OSError:
                pass
    keep = conf.get_int("APP_BACKUP_KEEP", 10)
    for old in sorted(glob.glob(os.path.join(bak_dir, f"{_prefix()}_*.db")))[:-keep]:
        try:
            os.remove(old)
        except OSError:
            pass
    return bak_path


def latest_backup() -> str | None:
    """가장 최근의 **열리는** 백업. 파일명이 타임스탬프라 사전순 = 시간순."""
    pattern = os.path.join(backup_dir(), f"{_prefix()}_*.db")
    for path in sorted(glob.glob(pattern), reverse=True):
        try:
            if os.path.getsize(path) <= 0:
                continue
            conn = sqlite3.connect(path)
            try:
                conn.execute("PRAGMA schema_version")
            finally:
                conn.close()
            return path
        except (OSError, sqlite3.DatabaseError):
            continue
    return None


def restore_if_missing() -> bool:
    """DB 파일이 없으면 최신 백업에서 복원. 반환: 복원 여부."""
    if os.path.exists(db_path()):
        return False
    src = latest_backup()
    if not src:
        return False
    os.makedirs(os.path.dirname(str(db_path())), exist_ok=True)
    tmp = f"{db_path()}.restore.{os.getpid()}"
    shutil.copy2(src, tmp)
    os.replace(tmp, db_path())
    return True


def start_backup_thread() -> None:
    """주기 백업 — 이 간격이 곧 강제 종료 시 최대 유실 구간이다."""
    global _backup_thread_started
    interval_min = conf.get_int("APP_BACKUP_INTERVAL_MIN")
    if _backup_thread_started or interval_min <= 0:
        return
    _backup_thread_started = True

    def loop():
        while True:
            time.sleep(interval_min * 60)
            try:
                backup()
            except Exception as e:  # noqa: BLE001 — 백업 실패가 워커를 죽이지 않게
                log.warning("주기 백업 실패: %s", e)

    threading.Thread(target=loop, daemon=True).start()


def install_shutdown_backup() -> None:
    """SIGTERM/SIGINT 에 백업 후 종료. 메인 스레드가 아니면 무시된다.

    ASGI 서버는 자체 시그널 처리로 graceful shutdown 을 하므로 여기서 걸지 않는다
    (전용 워커 프로세스 전용).
    """
    def handler(signum, _frame):
        try:
            backup()
        except Exception as e:  # noqa: BLE001
            log.warning("종료 백업 실패: %s", e)
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handler)
        except ValueError:
            pass
