"""공통 인증 — JWT(HS256, stdlib) + 역할(admin/viewer) + /api/auth 라우트.

외부 의존성 없이 표준 라이브러리로 구현. 기본 비활성(AUTH_ENABLED=false 면
데코레이터가 통과)이라 인증이 필요 없는 프로젝트에는 영향이 없다.

활성화(AUTH_ENABLED=true) 시:
  - 부팅 때 auth_user 가 비면 env(ADMIN_USER/ADMIN_PASSWORD,
    VIEWER_USER/VIEWER_PASSWORD)로 초기 계정을 시드한다 (app.py 가 호출).
  - POST /api/auth/login {username,password} → ok({token,username,role})
  - GET  /api/auth/me → ok({auth,username,role})
토큰 전달: Authorization: Bearer <token>. SSE 등 헤더를 못 싣는 요청은 ?token=.

보호 데코레이터: @require_auth(열람) / @require_admin(조작). g.user 에 payload.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from functools import wraps

from flask import g, request

from svkit.api import make_blueprint
from svkit.response import err, ok

AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'false').lower() == 'true'
SECRET = os.environ.get('JWT_SECRET', 'dev-insecure-secret-change-me').encode()
TOKEN_TTL = int(os.environ.get('JWT_TTL', '86400'))  # 초, 기본 1일
_PBKDF_ITER = 200000

SCHEMA = '''
CREATE TABLE IF NOT EXISTS auth_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'viewer',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
'''


def _b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _b64d(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, _PBKDF_ITER)
    return f'pbkdf2${salt.hex()}${dk.hex()}'


def verify_password(password, stored):
    try:
        _, salt_hex, hash_hex = stored.split('$')
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), _PBKDF_ITER)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def create_token(username, role):
    header = _b64e(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    payload = _b64e(json.dumps({'sub': username, 'role': role, 'exp': int(time.time()) + TOKEN_TTL}).encode())
    seg = f'{header}.{payload}'
    sig = _b64e(hmac.new(SECRET, seg.encode(), hashlib.sha256).digest())
    return f'{seg}.{sig}'


def verify_token(token):
    """유효하면 payload(dict), 아니면 None"""
    try:
        seg, sig = token.rsplit('.', 1)
        expected = _b64e(hmac.new(SECRET, seg.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(seg.split('.')[1]))
        if int(payload.get('exp', 0)) < time.time():
            return None
        return payload
    except Exception:
        return None


def _extract_token():
    h = request.headers.get('Authorization', '')
    if h.startswith('Bearer '):
        return h[7:]
    return request.args.get('token', '')  # SSE 등 헤더 못 싣는 경우


def require_auth(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not AUTH_ENABLED:
            return fn(*a, **kw)
        payload = verify_token(_extract_token())
        if not payload:
            return err('인증 필요', 401)
        g.user = payload
        return fn(*a, **kw)
    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not AUTH_ENABLED:
            return fn(*a, **kw)
        payload = verify_token(_extract_token())
        if not payload:
            return err('인증 필요', 401)
        if payload.get('role') != 'admin':
            return err('권한 없음', 403)
        g.user = payload
        return fn(*a, **kw)
    return wrapper


def seed_users():
    """AUTH_ENABLED이고 사용자가 없으면 env로 초기 계정 생성 (app.py 가 부팅 시 호출)"""
    from svkit.db import get_conn
    with get_conn() as conn:
        cnt = conn.execute('SELECT COUNT(*) c FROM auth_user').fetchone()['c']
        if cnt:
            return
        for role, u_key, p_key in [('admin', 'ADMIN_USER', 'ADMIN_PASSWORD'),
                                   ('viewer', 'VIEWER_USER', 'VIEWER_PASSWORD')]:
            u = os.environ.get(u_key)
            p = os.environ.get(p_key)
            if u and p:
                conn.execute('INSERT INTO auth_user (username, password_hash, role) VALUES (?, ?, ?)',
                             (u, hash_password(p), role))


bp = make_blueprint('auth')


@bp.post('/login')
def login():
    from svkit.db import get_conn
    data = request.get_json() or {}
    with get_conn() as conn:
        row = conn.execute('SELECT username, password_hash, role FROM auth_user WHERE username=?',
                           (data.get('username', ''),)).fetchone()
    if not row or not verify_password(data.get('password', ''), row['password_hash']):
        return err('인증 실패', 401)
    token = create_token(row['username'], row['role'])
    return ok({'token': token, 'username': row['username'], 'role': row['role']})


@bp.get('/me')
@require_auth
def me():
    if not AUTH_ENABLED:
        return ok({'auth': False, 'role': 'admin'})
    return ok({'auth': True, 'username': g.user['sub'], 'role': g.user['role']})
