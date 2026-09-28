"""Cookie session auth for /admin — password from ADMIN_PASSWORD."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, Response

COOKIE_NAME = "picsaver_admin"
SESSION_TTL_SEC = 12 * 3600

_fail_lock = Lock()
_fail_until: dict[str, float] = {}
_fail_count: dict[str, int] = defaultdict(int)

_MAX_FAILS = 10
_LOCK_SEC = 300


def admin_password() -> str:
    return (os.getenv("ADMIN_PASSWORD") or "").strip()


def _session_secret() -> bytes:
    pw = admin_password()
    if not pw:
        return b""
    return hashlib.sha256(f"picsaver-admin-session-v1:{pw}".encode("utf-8")).digest()


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def is_locked(request: Request) -> bool:
    ip = _client_ip(request)
    now = time.time()
    with _fail_lock:
        until = _fail_until.get(ip, 0.0)
        if until > now:
            return True
        if until and until <= now:
            _fail_until.pop(ip, None)
            _fail_count.pop(ip, None)
        return False


def register_login_failure(request: Request) -> None:
    """Call only after a non-empty wrong password on POST /admin/login."""
    ip = _client_ip(request)
    with _fail_lock:
        _fail_count[ip] += 1
        if _fail_count[ip] >= _MAX_FAILS:
            _fail_until[ip] = time.time() + _LOCK_SEC
            _fail_count[ip] = 0


def register_login_success(request: Request) -> None:
    ip = _client_ip(request)
    with _fail_lock:
        _fail_count.pop(ip, None)
        _fail_until.pop(ip, None)


def _const_eq(a: str, b: str) -> bool:
    salt = b"picsaver-admin-v1"
    da = hashlib.sha256(salt + a.encode("utf-8")).digest()
    db = hashlib.sha256(salt + b.encode("utf-8")).digest()
    return hmac.compare_digest(da, db)


def verify_password(username: str, password: str) -> bool:
    expected = admin_password()
    if not expected:
        return False
    return _const_eq(username.strip(), "admin") and _const_eq(password, expected)


def mint_session_token() -> str:
    secret = _session_secret()
    if not secret:
        raise RuntimeError("admin disabled")
    exp = int(time.time()) + SESSION_TTL_SEC
    nonce = secrets.token_hex(8)
    payload = f"admin.{exp}.{nonce}"
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session_token(token: str | None) -> bool:
    if not token:
        return False
    secret = _session_secret()
    if not secret:
        return False
    parts = token.split(".")
    if len(parts) != 4:
        return False
    role, exp_s, nonce, sig = parts
    if role != "admin" or not exp_s.isdigit() or not nonce:
        return False
    payload = f"{role}.{exp_s}.{nonce}"
    expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    if int(exp_s) < int(time.time()):
        return False
    return True


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SEC,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def require_admin_session(request: Request) -> str:
    expected = admin_password()
    if not expected:
        raise HTTPException(status_code=503, detail="admin disabled")
    token = request.cookies.get(COOKIE_NAME)
    if not verify_session_token(token):
        raise HTTPException(status_code=401, detail="unauthorized")
    return "admin"
