"""Save rate limits and album size caps (Package 3 Stage A).

Stage B (L3 job quota ≤3, L5 queue depth) — TODO, not in this module yet.
"""

from __future__ import annotations

import os

from redis_queue.queue import redis_conn

SAVE_ALBUM_MAX = int(os.getenv("SAVE_ALBUM_MAX", "5"))
SAVE_RATE_LIMIT = int(os.getenv("SAVE_RATE_LIMIT", "20"))
SAVE_RATE_WINDOW_SEC = int(os.getenv("SAVE_RATE_WINDOW_SEC", "600"))

_RATE_KEY = "picsaver:save_rate:{user_id}"

# Atomic check + consume: refuse without increment when over limit.
_CONSUME_LUA = """
local key = KEYS[1]
local n = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local current = tonumber(redis.call('GET', key) or '0')
if current + n > limit then
  return {0, current}
end
local new = redis.call('INCRBY', key, n)
if new == n then
  redis.call('EXPIRE', key, window)
end
return {1, new}
"""

_consume_script = redis_conn.register_script(_CONSUME_LUA)


def try_consume_save_quota(user_id: int, n: int = 1) -> tuple[bool, int]:
    """Try to reserve ``n`` saves for ``user_id`` in the rolling fixed window.

    Returns ``(allowed, current_count)``. On refuse, the counter is unchanged.
    """
    if n <= 0:
        return True, 0
    key = _RATE_KEY.format(user_id=user_id)
    allowed, current = _consume_script(
        keys=[key],
        args=[n, SAVE_RATE_LIMIT, SAVE_RATE_WINDOW_SEC],
    )
    return bool(allowed), int(current)


MSG_ALBUM_TOO_BIG = (
    "В альбоме слишком много фото. Можно сохранить не больше "
    f"{SAVE_ALBUM_MAX} за раз."
)
MSG_RATE_LIMIT = (
    "Сейчас слишком много сохранений. Подождите немного и попробуйте снова "
    f"(лимит: {SAVE_RATE_LIMIT} фото за {SAVE_RATE_WINDOW_SEC // 60} минут)."
)
MSG_BUSY = "Сейчас бот слишком загружен, попробуйте позже."
MSG_SAVE_TIMEOUT = "Не удалось сохранить изображение вовремя. Попробуйте ещё раз."
MSG_SAVE_FAILED = "Не удалось сохранить изображение вовремя. Попробуйте ещё раз."
