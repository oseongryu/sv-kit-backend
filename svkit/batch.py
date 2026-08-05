"""배치 공통 포맷 — 여러 큐 스텝(kind)을 순서대로 실행하는 파이프라인.

개별 스텝은 이미 svkit.queue 에 핸들러로 등록돼 있다. 배치는 그 스텝들을
순차 실행하는 상위 kind('batch.<이름>')를 큐에 등록한다. 그래서 배치도
일반 작업과 같은 레인/중지/재시도/이력 체계를 그대로 쓴다.

  from svkit import batch
  batch.define('catalog_daily', [
      {'kind': 'catalog.models', 'params': {'force': True}},
      {'kind': 'catalog.codes'},
      {'kind': 'catalog.details'},
  ], lane='crawl', title='카탈로그 일일 수집')

실행: queue.enqueue('batch.catalog_daily') 또는 스케줄러(svkit.scheduler).
파라미터: {'from_stage': N} — N번째(0부터) 단계부터 재실행.
단계 시작마다 중지 요청을 확인하고, 각 스텝 내부도 협조적 취소를 따르므로
중간에 멈추고 다음에 이어서(증분/갱신 로직) 실행할 수 있다.
"""
from svkit import queue
from svkit.base import batch_done, batch_progress, batch_stages, batch_stopped

# name -> {'stages': [...], 'title': str}
BATCHES = {}


def define(name, stages, lane=None, title=None):
    """배치 정의 + 'batch.<name>' kind 로 큐 핸들러 등록. 반환: kind 문자열

    단계 순회와 진행 문구는 base 에서 온다 — 같은 배치를 svkit2 로 옮겨도
    화면에 뜨는 문장이 그대로다(실행이 동기냐 async 냐만 다르다).
    """
    BATCHES[name] = {'stages': stages, 'title': title or name}

    def _runner(state, params, _stages=stages, _name=name):
        total = len(_stages)
        for i, total, stage in batch_stages(_stages, params.get('from_stage')):
            if queue.should_stop(state):
                queue.update_progress(state, batch_stopped(_name, i, total))
                return
            kind = stage['kind']
            fn = queue.handler_for(kind)
            if fn is None:
                raise RuntimeError(f'핸들러 없음: {kind}')
            queue.update_progress(state, batch_progress(_name, i, total, kind))
            queue.call_handler(fn, state, dict(stage.get('params') or {}))
        queue.update_progress(state, batch_done(_name, total))

    queue.register(f'batch.{name}', _runner, lane=lane)
    return f'batch.{name}'


def stages_of(name):
    """배치 단계 목록(없으면 빈 목록)."""
    return list(BATCHES.get(name, {}).get('stages', []))


__all__ = ['BATCHES', 'define', 'stages_of']
