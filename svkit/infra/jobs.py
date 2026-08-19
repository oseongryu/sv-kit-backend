"""백그라운드 잡 레지스트리 — 오래 걸리는 작업을 시작하고 화면이 폴링으로 따라간다.

**stdlib 만 쓴다.** 웹 프레임워크와 만나는 지점은 `Job.public()` 이 돌려주는 dict 하나뿐이다.

**소유자로 좁히는 것이 이 모듈의 규칙이다.** `get`/`list` 는 owner 를 필수로 받고 남의 잡을
`None` 으로 돌려준다.

**저장소는 프로세스 메모리다.** 재시작하면 사라진다. 도메인 고유 필드는 `Job` 을
**상속**해서 더한다.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type

#: 끝난 잡을 언제까지 조회할 수 있게 둘지. 화면이 폴링으로 결과를 가져갈 시간이면 충분하다.
DEFAULT_TTL_SEC = 30 * 60

RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class Job:
    id: str
    kind: str
    #: 이 잡을 만든 사용자. 남의 잡을 조회·중단할 수 없어야 한다.
    owner: str = ""
    status: str = RUNNING
    log: list = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    _cancel: threading.Event = field(default_factory=threading.Event)

    def note(self, message: str) -> None:
        """진행 한 줄. 화면이 그대로 보여 주므로 사람이 읽는 문장으로 적는다."""
        self.log.append(message)
        self.updated_at = time.time()

    def cancel(self) -> None:
        """중단 요청. **일하는 쪽이 `cancelled` 를 봐야 실제로 멈춘다** —
        스레드를 밖에서 죽이면 정리 코드가 안 돌아 자원이 샌다."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def public(self) -> dict:
        """화면에 나가는 모양. 상속해서 필드를 더할 땐 `{**super().public(), ...}`."""
        return {
            "id": self.id, "kind": self.kind, "status": self.status,
            "log": self.log, "result": self.result, "error": self.error,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


class Registry:
    """잡 보관소 하나. 도메인마다 하나씩 만든다 (같은 프로세스에 여럿이어도 된다).

    `name` 은 스레드 이름 접두로만 쓴다 — `docker exec`·`py-spy` 로 들여다볼 때
    어느 도메인의 잡인지 보이라고 붙인다.
    """

    def __init__(self, name: str, job_cls: Type[Job] = Job,
                 ttl_sec: int = DEFAULT_TTL_SEC) -> None:
        self._name = name
        self._job_cls = job_cls
        self._ttl = ttl_sec
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str, owner: str) -> Optional[Job]:
        """남의 잡은 **없는 것으로 본다** (403 이 아니라 None) — 존재 여부 자체를 숨긴다."""
        job = self._jobs.get(job_id)
        return job if job is not None and job.owner == owner else None

    def list(self, owner: str) -> list:
        return [j.public() for j in
                sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
                if j.owner == owner]

    def spawn(self, kind: str, owner: str, work: Callable[[Job], Any],
              on_finish: Optional[Callable[[Job], None]] = None, **fields: Any) -> Job:
        """잡을 만들고 데몬 스레드에서 `work(job)` 을 돌린다. 즉시 잡을 돌려준다.

        `work` 가 돌려준 값이 `job.result` 가 된다. 예외는 삼키지 않고 `status=failed` +
        `error` 로 옮긴다 — 스레드 안에서 터진 예외는 아무도 못 보기 때문이다.

        **`work` 가 `job.error` 를 채웠으면 done 이 아니라 failed 다.** "돌긴 돌았지만
        결과는 실패" 를 done 으로 두면 화면이 초록 완료와 성공 토스트를 띄운다.

        `on_finish` 는 성공·실패·예외 어느 쪽이든 마지막에 한 번 불린다 (세션 정리 등).
        여기서 터진 예외는 잡 상태를 바꾸지 않는다 — 정리 실패로 결과를 잃지 않게.

        `fields` 는 `job_cls` 의 추가 필드로 넘어간다.
        """
        job = self._job_cls(id=uuid.uuid4().hex[:12], kind=kind, owner=owner, **fields)
        with self._lock:
            self._sweep()
            self._jobs[job.id] = job

        def run() -> None:
            try:
                job.result = work(job)
                job.status = FAILED if job.error else DONE
            except Exception as exc:  # noqa: BLE001 — 잡 실패는 상태로 보고한다
                job.status = FAILED
                job.error = str(exc)
                job.note(f"실패: {exc}")
            finally:
                if on_finish is not None:
                    try:
                        on_finish(job)
                    except Exception:  # noqa: BLE001 — 정리 실패가 결과를 덮지 않게
                        pass
                job.updated_at = time.time()

        threading.Thread(target=run, name=f"{self._name}-{kind}-{job.id}",
                         daemon=True).start()
        return job

    def _sweep(self) -> None:
        """TTL 지난 **끝난** 잡을 버린다. 도는 잡은 아무리 오래돼도 남긴다."""
        cutoff = time.time() - self._ttl
        for job_id, job in list(self._jobs.items()):
            if job.status != RUNNING and job.updated_at < cutoff:
                self._jobs.pop(job_id, None)
