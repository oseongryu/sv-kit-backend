"""키 표기 변환 — 서버 안쪽은 snake_case 로 쓰고, 바깥 계약이 camelCase 일 때
경계에서만 바꾼다.

왕복이 완전 대칭은 아니다 — `userID` 는 `user_id` 를 거쳐 `userId` 로 돌아온다.
"""
import re

_ACRONYM = re.compile(r"(.)([A-Z][a-z]+)")
_WORD = re.compile(r"([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    return _WORD.sub(r"\1_\2", _ACRONYM.sub(r"\1_\2", name)).lower()


def snake_to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def _walk(value, convert):
    if isinstance(value, dict):
        return {(convert(k) if isinstance(k, str) else k): _walk(v, convert)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(item, convert) for item in value]
    return value


def keys_to_snake(value):
    """dict 키를 재귀적으로 snake_case 로 바꾼다. 값은 손대지 않는다."""
    return _walk(value, camel_to_snake)


def keys_to_camel(value):
    """dict 키를 재귀적으로 camelCase 로 바꾼다. 값은 손대지 않는다."""
    return _walk(value, snake_to_camel)
