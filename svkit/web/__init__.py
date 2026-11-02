"""웹 커널 — 앱 조립·응답 규약·라우터 팩토리·요청 컨텍스트·인증·미들웨어·정적 서빙.

자주 쓰는 심볼은 여기서 지연 재수출한다 — 이름만 쓰는 소비처가 fastapi 를 끌지 않게
`__getattr__` 로 늦게 푼다.
"""
_EXPORTS = {
    "ApiError": "errors",
    "ok": "response", "err": "response", "WithMeta": "response",
    "envelope": "response", "error_body": "response",
    "install_error_handlers": "response",
    "make_router": "api", "page_args": "api", "Page": "api",
    "create_app": "app", "create_service_app": "app",
    "require_auth": "app", "require_admin": "app", "current_user": "app",
    "load_domains": "app", "routers_of": "app", "auth_enabled": "app",
    "DOMAINS": "app", "seed_users": "app", "AUTH_SCHEMA": "app",
    "camel_to_snake": "casing", "snake_to_camel": "casing",
    "keys_to_snake": "casing", "keys_to_camel": "casing",
    "CasingMiddleware": "middleware",
    "AuthGateMiddleware": "middleware",
    "hash_password": "security", "verify_password": "security",
    "create_token": "security", "verify_token": "security",
    "PBKDF_ITER": "security",
}


def __getattr__(name):
    mod = _EXPORTS.get(name)
    if mod is None:
        raise AttributeError(f"module 'svkit.web' has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(f"svkit.web.{mod}"), name)
    globals()[name] = value
    return value
