"""도메인 SQL 선언 집결 — 모듈이 저마다 둔 `feature/feature_query_*.xml` 을 한 매퍼로 본다.

`domain_globals` 와 같은 방식이다: 파일을 **이름으로** 거둬 오므로 새 모듈을 더할 때
목록을 고칠 곳이 없다. 이름공간은 그 XML 의 `<mapper namespace>` 라, 어느 모듈이
선언했는지와 무관하게 `"<ns>.<id>"` 하나로 부른다.

목록은 **호출 시점에** 다시 푼다 — import 순서에 따라 아직 로드되지 않은 모듈이 있고,
그 시점에 굳히면 그 모듈의 선언이 통째로 빠진다.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from svkit.db.mapper import SqlMapper
from svkit.loader import domain_hooks
from svkit.loader.editions import MODULE_PREFIX

GLOB = "feature/feature_query_*.xml"


def _module_dir(pkg: str) -> Path | None:
    """패키지 위치만 얻는다 — import 하지 않는다(선언 실행은 로더의 일이 아니다)."""
    try:
        spec = importlib.util.find_spec(pkg)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(list(spec.submodule_search_locations)[0])


def query_files() -> list[Path]:
    """켜진 모듈의 매퍼 파일 — 패키지명 사전순, 그 안은 파일명 사전순."""
    out: list[Path] = []
    for name in domain_hooks.domain_names():
        base = _module_dir(f"{MODULE_PREFIX}{name}")
        if base is None:
            continue
        out.extend(sorted(base.glob(GLOB)))
    return out


#: 전역 레지스트리 — 파일 목록·mtime 을 스스로 다시 본다.
QUERIES = SqlMapper(query_files)


def build(qid: str, params=None):
    """`(sql, binds)` — 자세한 계약은 `svkit/db/mapper.py`."""
    return QUERIES.build(qid, params)


def build_fragment(refid: str, params=None):
    return QUERIES.build_fragment(refid, params)


def owners() -> dict[str, str]:
    """`{이름공간: 그 선언을 가진 파일}` — 같은 ns 를 둘이 쓰면 매퍼가 먼저 막는다."""
    out: dict[str, str] = {}
    for path in query_files():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "<mapper" in line and "namespace=" in line:
                ns = line.split('namespace="', 1)[1].split('"', 1)[0]
                out[ns] = str(path)
                break
    return out


__all__ = ["QUERIES", "GLOB", "query_files", "build", "build_fragment", "owners"]
