"""키 표기 변환 — 서버 안쪽은 snake_case 로 쓰고, 바깥 계약이 camelCase 일 때
경계에서만 바꾼다.

왕복이 완전 대칭은 아니다 — `userID` 는 `user_id` 를 거쳐 `userId` 로 돌아온다.

**키가 곧 데이터인 dict 가 있다** — 잡 파라미터·자동화 env·지표 attrs 처럼 사람이 이름을
짓는 것들이다. 그것까지 바꾸면 저장된 값이 오염되므로(`API_KEY` → `api_key`,
`SHOPPING` → `shopping`) 그런 키는 `opaque` 로 받아 **하위 트리를 통째로 비켜 간다.**
무엇이 그런 키인지는 앱이 안다 — 커널은 목록을 갖지 않는다.
"""
import re

_ACRONYM = re.compile(r"(.)([A-Z][a-z]+)")
_WORD = re.compile(r"([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    return _WORD.sub(r"\1_\2", _ACRONYM.sub(r"\1_\2", name)).lower()


def snake_to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def _walk(value, convert, opaque):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                out[k] = _walk(v, convert, opaque)
                continue
            # 오는 방향에 따라 키가 camel 이기도 snake 이기도 하다 — snake 로 맞춰 본다.
            out[convert(k)] = v if camel_to_snake(k) in opaque else _walk(v, convert, opaque)
        return out
    if isinstance(value, list):
        return [_walk(item, convert, opaque) for item in value]
    return value


def keys_to_snake(value, opaque=()):
    """dict 키를 재귀적으로 snake_case 로. 값은 손대지 않고, `opaque` 키의 값은 통째로 둔다."""
    return _walk(value, camel_to_snake, frozenset(opaque))


def keys_to_camel(value, opaque=()):
    """dict 키를 재귀적으로 camelCase 로. 값은 손대지 않고, `opaque` 키의 값은 통째로 둔다."""
    return _walk(value, snake_to_camel, frozenset(opaque))
