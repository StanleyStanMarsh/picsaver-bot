"""HTTP Basic auth for /admin — password only from ADMIN_PASSWORD."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict
from threading import Lock
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_basic = HTTPBasic(auto_error=False)

_fail_lock = Lock()
_fail_until: dict[str, float] = {}
_fail_count: dict[str, int] = defaultdict(int)

_MAX_FAILS = 10
_LOCK_SEC = 300

_CHALLENGE = {"WWW-Authenticate": 'Basic realm="picsaver-admin", charset="UTF-8"'}


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _locked(ip: str) -> bool:
    now = time.time()
    with _fail_lock:
        until = _fail_until.get(ip, 0.0)
        if until > now:
            return True
        if until and until <= now:
            _fail_until.pop(ip, None)
            _fail_count.pop(ip, None)
        return False


def _register_failure(ip: str) -> None:
    with _fail_lock:
        _fail_count[ip] += 1
        if _fail_count[ip] >= _MAX_FAILS:
            _fail_until[ip] = time.time() + _LOCK_SEC
            _fail_count[ip] = 0


def _register_success(ip: str) -> None:
    with _fail_lock:
        _fail_count.pop(ip, None)
        _fail_until.pop(ip, None)


def _const_eq(a: str, b: str) -> bool:
    """Timing-safe compare via salted SHA-256 digests (length-independent)."""
    salt = b"picsaver-admin-v1"
    da = hashlib.sha256(salt + a.encode("utf-8")).digest()
    db = hashlib.sha256(salt + b.encode("utf-8")).digest()
    return hmac.compare_digest(da, db)


def require_admin(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
) -> str:
    expected = (os.getenv("ADMIN_PASSWORD") or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="admin disabled")

    ip = _client_ip(request)

    # Always keep WWW-Authenticate so the browser can show the login dialog,
    # including while rate-limited.
    if _locked(ip):
        raise HTTPException(
            status_code=429,
            detail="too many attempts",
            headers=dict(_CHALLENGE),
        )

    if credentials is None:
        raise HTTPException(status_code=401, detail="unauthorized", headers=dict(_CHALLENGE))

    # Cancel / empty Basic probe — challenge again, do not burn the fail budget.
    if not credentials.username.strip() and not credentials.password:
        raise HTTPException(status_code=401, detail="unauthorized", headers=dict(_CHALLENGE))

    user_ok = _const_eq(credentials.username, "admin")
    pass_ok = _const_eq(credentials.password, expected)

    if not (user_ok and pass_ok):
        # Count only real password attempts (non-empty password).
        if credentials.password:
            _register_failure(ip)
        raise HTTPException(status_code=401, detail="unauthorized", headers=dict(_CHALLENGE))

    _register_success(ip)
    return "admin"
