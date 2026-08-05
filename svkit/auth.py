"""공통 인증 — JWT(HS256, stdlib) + 역할(admin/viewer) + /api/auth 라우트.

외부 의존성 없이 표준 라이브러리로 구현. 기본 비활성(AUTH_ENABLED=false 면
데코레이터가 통과)이라 인증이 필요 없는 프로젝트에는 영향이 없다.

**토큰 발급·검증·비밀번호 해시는 `base` 하나**다 — svkit2 와 같은 코드라
같은 JWT_SECRET 이면 두 판이 서로의 토큰을 받는다.

활성화(AUTH_ENABLED=true) 시:
  - 부팅 때 auth_user 가 비면 env(ADMIN_USER/ADMIN_PASSWORD,
    VIEWER_USER/VIEWER_PASSWORD)로 초기 계정을 시드한다 (app.py 가 호출).
  - POST /api/auth/login {username,password} → ok({token,username,role})
  - GET  /api/auth/me → ok({auth,username,role})
토큰 전달: Authorization: Bearer <token>. SSE 등 헤더를 못 싣는 요청은 ?token=.

보호 데코레이터: @require_auth(열람) / @require_admin(조작). g.user 에 payload,
`current_user()` 로 svkit2 와 같은 `User` 객체를 얻는다.
"""
import os
from functools import wraps

from flask import g, request

from svkit import base
from svkit.api import make_blueprint
from svkit.base import ANONYMOUS_ADMIN, User, hash_password, verify_password
from svkit.response import err, ok

AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'false').lower() == 'true'
SECRET = os.environ.get('JWT_SECRET', 'dev-insecure-secret-change-me').encode()
TOKEN_TTL = int(os.environ.get('JWT_TTL', '86400'))  # 초, 기본 1일

SCHEMA = '''
CREATE TABLE IF NOT EXISTS auth_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'viewer',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
'''


def create_token(username, role):
    return base.create_token(username, role, SECRET, TOKEN_TTL)


def verify_token(token):
    """유효하면 payload(dict), 아니면 None"""
    return base.verify_token(token, SECRET)


def _extract_token():
    return base.token_from(request.headers.get('Authorization', ''),
                           request.args.get('token', ''))


def _authenticate(admin_only=False):
    """통과하면 payload, 아니면 (응답, status) 튜플."""
    if not AUTH_ENABLED:
        return None
    payload = verify_token(_extract_token())
    if not payload:
        return err('인증 필요', 401)
    if admin_only and payload.get('role') != 'admin':
        return err('권한 없음', 403)
    g.user = payload
    return None


def _guard(admin_only):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            denied = _authenticate(admin_only)
            if denied is not None:
                return denied
            return fn(*a, **kw)
        return wrapper
    return decorator


def require_auth(fn=None):
    """`@require_auth` 와 `@require_auth()` 둘 다 받는다(호출형은 svkit2 표기)."""
    guard = _guard(False)
    return guard if fn is None else guard(fn)


def require_admin(fn=None):
    """`@require_admin` 과 `@require_admin()` 둘 다 받는다."""
    guard = _guard(True)
    return guard if fn is None else guard(fn)


#: svkit2 와 이름을 맞춘 별칭
require_user = require_auth


def current_user():
    """현재 요청 사용자(`User`). 인증 비활성이면 관리자로 취급한다."""
    if not AUTH_ENABLED:
        return ANONYMOUS_ADMIN
    payload = getattr(g, 'user', None) or verify_token(_extract_token())
    return User.from_payload(payload) if payload else None


def optional_user():
    """토큰이 있으면 해석하고 없으면 None — 공개 라우트의 선택적 개인화용."""
    return current_user()


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


__all__ = ['AUTH_ENABLED', 'SCHEMA', 'bp', 'User', 'ANONYMOUS_ADMIN',
           'hash_password', 'verify_password', 'create_token', 'verify_token',
           'require_auth', 'require_admin', 'require_user', 'current_user',
           'optional_user', 'seed_users']