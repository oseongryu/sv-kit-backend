"""앞단 프록시 라우팅 등록 창구 — traefik file provider 디렉토리를 소유한다.

라우트 하나 = 파일 하나(`<접두><이름>.yml`)이고 traefik 이 watch 로 즉시 읽는다.
어느 앱 도메인도 모른다 — 이름·주소·포트만 받는다.

`create_app()` 은 그 창구를 HTTP 로 낸다: `GET/PUT/DELETE /api/routes[/{name}]`.
쓰기는 `EDGE_API_TOKEN` 이 있어야 하고, 값이 비면 등록을 받지 않는다(503).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from svkit.loader import conf

#: 파일명·traefik 라우터 id 로 동시에 쓰이는 이름.
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
_TARGET = re.compile(r"^[A-Za-z0-9_.-]+$")
_HOST = re.compile(r"^[A-Za-z0-9_.-]+$")
_META_PREFIX = "# edge-route "


class EdgeError(Exception):
    """등록 거부 — 호출부가 400 으로 옮긴다."""


def routes_dir() -> Path:
    return Path(conf.get_str("EDGE_ROUTES_DIR", "/dynamic"))


def _prefix() -> str:
    return conf.get_str("EDGE_ROUTE_PREFIX", "external-")


def _entrypoint() -> str:
    return conf.get_str("EDGE_ENTRYPOINT", "websecure")


def _cert_resolver() -> str:
    return conf.get_str("EDGE_CERT_RESOLVER", "le")


def _path(name: str) -> Path:
    return routes_dir() / f"{_prefix()}{name}.yml"


def _validate(name: str, target: str, port: int, host: str) -> None:
    if not _NAME.match(name or ""):
        raise EdgeError(f"이름은 소문자·숫자·하이픈 31자 이내: {name!r}")
    if not _TARGET.match(target or ""):
        raise EdgeError(f"대상 주소 형식이 아니다: {target!r}")
    if not 1 <= int(port) <= 65535:
        raise EdgeError(f"포트 범위 밖: {port}")
    if not _HOST.match(host or "") or "." not in host:
        raise EdgeError(f"호스트 형식이 아니다: {host!r}")


def _render(meta: dict) -> str:
    name, host = meta["name"], meta["host"]
    return (
        _META_PREFIX + json.dumps(meta, ensure_ascii=False, sort_keys=True) + "\n"
        "http:\n"
        "  routers:\n"
        f"    {name}:\n"
        f'      rule: "Host(`{host}`)"\n'
        f"      entryPoints: [{meta['entrypoint']}]\n"
        f"      service: {name}\n"
        "      tls:\n"
        f"        certResolver: {meta['certResolver']}\n"
        "  services:\n"
        f"    {name}:\n"
        "      loadBalancer:\n"
        "        servers:\n"
        f'          - url: "http://{meta["target"]}:{meta["port"]}"\n'
    )


def _parse(path: Path) -> dict | None:
    """등록 메타 — 첫 줄 주석이 그것을 담는다. 없으면 이름만 낸다(손으로 넣은 파일)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    prefix = _prefix()
    name = path.stem[len(prefix):] if path.stem.startswith(prefix) else path.stem
    first = text.splitlines()[0] if text else ""
    meta = {}
    if first.startswith(_META_PREFIX):
        try:
            meta = json.loads(first[len(_META_PREFIX):])
        except ValueError:
            meta = {}
    return {**meta, "name": name}


def list_routes() -> list[dict]:
    d = routes_dir()
    if not d.is_dir():
        return []
    out = [_parse(p) for p in sorted(d.glob(f"{_prefix()}*.yml"))]
    return [r for r in out if r]


def get_route(name: str) -> dict | None:
    path = _path(name)
    return _parse(path) if path.is_file() else None


def put_route(name: str, target: str, port: int, host: str = "",
              entrypoint: str = "", cert_resolver: str = "") -> dict:
    """등록·갱신. 같은 이름이면 덮어쓴다. 실패는 EdgeError 또는 OSError."""
    host = host or f"{name}.{conf.get_str('BASE_DOMAIN')}"
    _validate(name, target, port, host)
    meta = {
        "name": name, "host": host, "target": target, "port": int(port),
        "entrypoint": entrypoint or _entrypoint(),
        "certResolver": cert_resolver or _cert_resolver(),
    }
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(meta), encoding="utf-8")
    return meta


def delete_route(name: str) -> bool:
    """지웠으면 True, 원래 없었으면 False."""
    if not _NAME.match(name or ""):
        raise EdgeError(f"이름 형식이 아니다: {name!r}")
    path = _path(name)
    if not path.is_file():
        return False
    path.unlink()
    return True


def create_app():
    from fastapi import Depends, FastAPI, Header

    from svkit.web import ApiError, install_error_handlers

    def guard(x_edge_token: str = Header(default="")) -> None:
        """토큰은 `X-Edge-Token` 하나로만 받는다 — 같은 값을 넣는 길이 둘일 이유가 없다."""
        expected = conf.get_str("EDGE_API_TOKEN")
        if not expected:
            raise ApiError("EDGE_API_TOKEN 미설정 — 등록 창구가 닫혀 있다", 503)
        if x_edge_token != expected:
            raise ApiError("토큰이 맞지 않는다", 401)

    app = FastAPI(title="Edge Registrar", version="1.0.0")
    install_error_handlers(app)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "data": {"status": "ok", "routes": len(list_routes())}}

    @app.get("/api/routes", dependencies=[Depends(guard)])
    def _list() -> dict:
        return {"ok": True, "data": list_routes()}

    @app.get("/api/routes/{name}", dependencies=[Depends(guard)])
    def _get(name: str) -> dict:
        route = get_route(name)
        if route is None:
            raise ApiError(f"없는 라우트: {name}", 404)
        return {"ok": True, "data": route}

    @app.put("/api/routes/{name}", dependencies=[Depends(guard)])
    def _put(name: str, body: dict) -> dict:
        try:
            meta = put_route(
                name, str(body.get("target", "")), int(body.get("port", 0)),
                str(body.get("host", "")), str(body.get("entrypoint", "")),
                str(body.get("certResolver", "")))
        except EdgeError as e:
            raise ApiError(str(e), 400)
        except (TypeError, ValueError) as e:
            raise ApiError(f"본문이 잘못됐다: {e}", 400)
        except OSError as e:
            raise ApiError(f"라우트 파일 쓰기 실패: {e}", 500)
        return {"ok": True, "data": meta}

    @app.delete("/api/routes/{name}", dependencies=[Depends(guard)])
    def _delete(name: str) -> dict:
        try:
            removed = delete_route(name)
        except EdgeError as e:
            raise ApiError(str(e), 400)
        except OSError as e:
            raise ApiError(f"라우트 파일 삭제 실패: {e}", 500)
        return {"ok": True, "data": {"name": name, "removed": removed}}

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=conf.get_int("EDGE_PORT", 8507))


if __name__ == "__main__":
    main()
