"""공통 응답 규약 — 성공 {ok, data, meta}, 실패 {ok:false, error}.

프론트 lib/api.ts 가 이 규약을 기대한다.
"""
from flask import jsonify


def ok(data=None, meta=None, status=200):
    body = {"ok": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def err(message, status=400):
    return jsonify({"ok": False, "error": message}), status
