"""Validate Telegram WebApp initData (HMAC)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class AuthError(PermissionError):
    pass


def validate_webapp_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_sec: int = 86400,
) -> dict:
    if not init_data or not bot_token:
        raise AuthError("missing init data")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise AuthError("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise AuthError("bad hash")

    auth_date = int(parsed.get("auth_date") or "0")
    if max_age_sec > 0 and auth_date and (time.time() - auth_date) > max_age_sec:
        raise AuthError("init data expired")

    user_raw = parsed.get("user")
    if not user_raw:
        raise AuthError("missing user")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as e:
        raise AuthError("bad user json") from e

    user_id = user.get("id")
    if user_id is None:
        raise AuthError("missing user id")
    return {"user_id": int(user_id), "user": user, "raw": parsed}
