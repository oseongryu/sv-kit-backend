"""전용 워커 프로세스 — 큐 레인 소비 엔트리(컨테이너 분리 시).

생성물 backend/worker.py 는 이것만 쓴다:

    from svkit.worker import main
    main(__file__)

백엔드 API 와 같은 이미지에서 `python worker.py` 로 실행한다.
db.init_all() 이 registry 를 로드하며 도메인 etl 의 핸들러 등록도 이때 일어난다.
API 컨테이너 쪽은 RUN_WORKER=false 로 두어 이중 소비를 막는다.
"""
import os
import sys


def main(root: str | None = None) -> None:
    from svkit.app import _resolve_root
    root = _resolve_root(root)
    if root not in sys.path:
        sys.path.insert(0, root)

    from svkit import db, logger, queue, registry, scheduler

    registry.load_domains()
    db.init_all()
    logger.info("worker", "부팅")
    scheduler.start_thread()
    queue.worker_loop()
