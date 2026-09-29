"""Save / CLIP-queue limits: rate (Stage A), per-user active slots (L3), queue depth (L5)."""

from __future__ import annotations

import os

from redis_queue.queue import redis_conn, save_queue

SAVE_ALBUM_MAX = int(os.getenv("SAVE_ALBUM_MAX", "5"))
SAVE_RATE_LIMIT = int(os.getenv("SAVE_RATE_LIMIT", "20"))
SAVE_RATE_WINDOW_SEC = int(os.getenv("SAVE_RATE_WINDOW_SEC", "600"))
SAVE_USER_ACTIVE_MAX = int(os.getenv("SAVE_USER_ACTIVE_MAX", "3"))
# 0 = disable soft reject on queue depth
SAVE_QUEUE_MAX_DEPTH = int(os.getenv("SAVE_QUEUE_MAX_DEPTH", "50"))

_RATE_KEY = "picsaver:save_rate:{user_id}"
_ACTIVE_KEY = "picsaver:save_active:{user_id}"

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

_RELEASE_ACTIVE_LUA = """
local key = KEYS[1]
local current = tonumber(redis.call('GET', key) or '0')
if current <= 0 then
  redis.call('SET', key, 0)
  return 0
end
return redis.call('DECR', key)
"""

_consume_script = redis_conn.register_script(_CONSUME_LUA)
_release_active_script = redis_conn.register_script(_RELEASE_ACTIVE_LUA)


class SaveQuotaExceeded(Exception):
    """User already has ≥ SAVE_USER_ACTIVE_MAX active CLIP/save jobs."""


class SaveQueueBusy(Exception):
    """RQ save queue depth is at or above SAVE_QUEUE_MAX_DEPTH."""


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


def get_active_slots(user_id: int) -> int:
    """Current per-user active CLIP/save job count (queued or waiting from bot)."""
    key = _ACTIVE_KEY.format(user_id=user_id)
    raw = redis_conn.get(key)
    return int(raw or 0)


def try_acquire_active_slot(user_id: int) -> bool:
    """INCR active counter; if over max, DECR and return False (no enqueue)."""
    key = _ACTIVE_KEY.format(user_id=user_id)
    new = int(redis_conn.incr(key))
    if new > SAVE_USER_ACTIVE_MAX:
        redis_conn.decr(key)
        # Keep floor ≥ 0 if concurrent release raced
        if int(redis_conn.get(key) or 0) < 0:
            redis_conn.set(key, 0)
        return False
    return True


def release_active_slot(user_id: int) -> None:
    """DECR active counter with floor 0."""
    key = _ACTIVE_KEY.format(user_id=user_id)
    _release_active_script(keys=[key])


def save_queue_depth() -> int:
    """Number of jobs currently queued on the RQ ``save`` queue (not started)."""
    return int(save_queue.count)


def check_queue_depth_or_raise() -> int:
    """Return current depth; raise SaveQueueBusy if soft-reject threshold hit."""
    depth = save_queue_depth()
    if SAVE_QUEUE_MAX_DEPTH > 0 and depth >= SAVE_QUEUE_MAX_DEPTH:
        raise SaveQueueBusy(f"save queue depth={depth} >= {SAVE_QUEUE_MAX_DEPTH}")
    return depth


MSG_ALBUM_TOO_BIG = (
    "В альбоме слишком много фото. Можно сохранить не больше "
    f"{SAVE_ALBUM_MAX} за раз."
)
MSG_RATE_LIMIT = (
    "Сейчас слишком много сохранений. Подождите немного и попробуйте снова "
    f"(лимит: {SAVE_RATE_LIMIT} фото за {SAVE_RATE_WINDOW_SEC // 60} минут)."
)
MSG_BUSY = "Сейчас бот слишком загружен, попробуйте позже."
MSG_QUOTA = (
    "У вас уже обрабатывается слишком много фото "
    f"(лимит: {SAVE_USER_ACTIVE_MAX} одновременно). "
    "Подождите и попробуйте снова."
)
MSG_SAVE_TIMEOUT = "Не удалось сохранить изображение вовремя. Попробуйте ещё раз."
MSG_SAVE_FAILED = "Не удалось сохранить изображение вовремя. Попробуйте ещё раз."
