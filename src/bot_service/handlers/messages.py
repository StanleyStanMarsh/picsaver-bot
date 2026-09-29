import asyncio

from aiogram import Bot, F, Router, types

from bot_service.services import UsersService
from bot_service.services.save_limits import (
    MSG_ALBUM_TOO_BIG,
    MSG_BUSY,
    MSG_QUOTA,
    MSG_RATE_LIMIT,
    MSG_SAVE_FAILED,
    MSG_SAVE_TIMEOUT,
    SAVE_ALBUM_MAX,
    SAVE_QUEUE_MAX_DEPTH,
    SAVE_USER_ACTIVE_MAX,
    SaveQuotaExceeded,
    SaveQueueBusy,
    get_active_slots,
    save_queue_depth,
    try_consume_save_quota,
)
from media_service.tools import save_image
from utils import APP_CTX

logger = APP_CTX.get_logger()
router = Router()

# Debounce after last photo of a Telegram media_group before flush.
_ALBUM_DEBOUNCE_SEC = 1.2

# media_group_id -> buffer state
_pending_albums: dict[str, dict] = {}
_albums_lock = asyncio.Lock()


def _is_similar_caption(caption: str | None) -> bool:
    if not caption:
        return False
    head = caption.strip().split()[0].lower()
    return head in ("/similar", "/similar@pic_vault_bot")


async def _early_clip_guards(user_id: int) -> str | None:
    """Peek L5/L3 before starting work; return user MSG or None if OK.

    Authoritative acquire still happens in save_image / embed paths.
    """
    depth = await asyncio.to_thread(save_queue_depth)
    if SAVE_QUEUE_MAX_DEPTH > 0 and depth >= SAVE_QUEUE_MAX_DEPTH:
        return MSG_BUSY
    slots = await asyncio.to_thread(get_active_slots, user_id)
    if slots >= SAVE_USER_ACTIVE_MAX:
        return MSG_QUOTA
    return None


@router.message(F.photo)
async def save_photo(message: types.Message, bot: Bot):
    if message.from_user is None:
        return
    # /similar handled in commands_router (registered first)
    if _is_similar_caption(message.caption):
        return

    photo = message.photo[-1]
    media_group_id = message.media_group_id

    if media_group_id:
        await _buffer_album_photo(message, bot, photo.file_id, media_group_id)
        return

    await _handle_single_photo(message, bot, photo.file_id)


async def _handle_single_photo(message: types.Message, bot: Bot, file_id: str) -> None:
    user_id = message.from_user.id
    allowed, _ = await asyncio.to_thread(try_consume_save_quota, user_id, 1)
    if not allowed:
        await message.reply(MSG_RATE_LIMIT)
        return

    early = await _early_clip_guards(user_id)
    if early is not None:
        await message.reply(early)
        return

    await message.reply("📸 Изображение сохраняется...")
    asyncio.create_task(save_and_notify(message, bot, file_id))


async def _buffer_album_photo(
    message: types.Message,
    bot: Bot,
    file_id: str,
    media_group_id: str,
) -> None:
    async with _albums_lock:
        buf = _pending_albums.get(media_group_id)
        if buf is None:
            buf = {
                "messages": [],
                "file_ids": [],
                "bot": bot,
                "user_id": message.from_user.id,
                "flush_task": None,
            }
            _pending_albums[media_group_id] = buf

        buf["messages"].append(message)
        buf["file_ids"].append(file_id)

        old_task = buf.get("flush_task")
        if old_task is not None and not old_task.done():
            old_task.cancel()

        buf["flush_task"] = asyncio.create_task(
            _debounced_flush_album(media_group_id)
        )


async def _debounced_flush_album(media_group_id: str) -> None:
    try:
        await asyncio.sleep(_ALBUM_DEBOUNCE_SEC)
    except asyncio.CancelledError:
        return

    async with _albums_lock:
        buf = _pending_albums.pop(media_group_id, None)

    if not buf:
        return

    messages: list[types.Message] = buf["messages"]
    file_ids: list[str] = buf["file_ids"]
    bot: Bot = buf["bot"]
    user_id: int = buf["user_id"]
    reply_to = messages[0]

    n = len(file_ids)
    if n > SAVE_ALBUM_MAX:
        try:
            await reply_to.reply(MSG_ALBUM_TOO_BIG)
        except Exception:
            logger.exception("failed to notify album-too-big user_id=%s", user_id)
        return

    allowed, _ = await asyncio.to_thread(try_consume_save_quota, user_id, n)
    if not allowed:
        try:
            await reply_to.reply(MSG_RATE_LIMIT)
        except Exception:
            logger.exception("failed to notify rate-limit user_id=%s", user_id)
        return

    # Album saves are sequential (1 slot); still refuse if user already at active max.
    early = await _early_clip_guards(user_id)
    if early is not None:
        try:
            await reply_to.reply(early)
        except Exception:
            logger.exception("failed to notify clip-guard user_id=%s", user_id)
        return

    try:
        status = await reply_to.reply(f"📸 Сохраняю альбом ({n} фото)...")
    except Exception:
        logger.exception("failed to send album status user_id=%s", user_id)
        status = None

    asyncio.create_task(
        save_album_and_notify(reply_to, bot, user_id, file_ids, status)
    )


async def save_and_notify(message: types.Message, bot: Bot, file_id: str):
    try:
        # FK images.user_id → users: ensure row exists before RQ job
        await UsersService().register_or_update_from_telegram(message.from_user)
        await save_image(bot=bot, user_id=message.from_user.id, file_id=file_id)
        await message.reply("✅ Изображение сохранено и проиндексировано")
    except SaveQueueBusy:
        logger.warning("save busy user_id=%s", getattr(message.from_user, "id", None))
        try:
            await message.reply(MSG_BUSY)
        except Exception:
            logger.exception("failed to notify user about save busy")
    except SaveQuotaExceeded:
        logger.warning("save quota user_id=%s", getattr(message.from_user, "id", None))
        try:
            await message.reply(MSG_QUOTA)
        except Exception:
            logger.exception("failed to notify user about save quota")
    except TimeoutError:
        logger.exception("save timeout user_id=%s", getattr(message.from_user, "id", None))
        try:
            await message.reply(MSG_SAVE_TIMEOUT)
        except Exception:
            logger.exception("failed to notify user about save timeout")
    except Exception:
        logger.exception("save failed user_id=%s", getattr(message.from_user, "id", None))
        try:
            await message.reply(MSG_SAVE_FAILED)
        except Exception:
            logger.exception("failed to notify user about save error")


async def save_album_and_notify(
    reply_to: types.Message,
    bot: Bot,
    user_id: int,
    file_ids: list[str],
    status_message: types.Message | None,
) -> None:
    try:
        await UsersService().register_or_update_from_telegram(reply_to.from_user)
        ok = 0
        failed = 0
        quota_hit = False
        busy_hit = False
        for file_id in file_ids:
            try:
                await save_image(bot=bot, user_id=user_id, file_id=file_id)
                ok += 1
            except SaveQueueBusy:
                busy_hit = True
                failed += 1
                logger.warning(
                    "album photo save busy user_id=%s file_id=%s", user_id, file_id
                )
                break
            except SaveQuotaExceeded:
                quota_hit = True
                failed += 1
                logger.warning(
                    "album photo save quota user_id=%s file_id=%s", user_id, file_id
                )
                break
            except Exception:
                failed += 1
                logger.exception(
                    "album photo save failed user_id=%s file_id=%s", user_id, file_id
                )

        if busy_hit and ok == 0:
            text = MSG_BUSY
        elif quota_hit and ok == 0:
            text = MSG_QUOTA
        elif failed == 0:
            text = f"✅ Альбом сохранён ({ok} фото)"
        elif ok == 0:
            text = MSG_SAVE_FAILED
        else:
            text = f"⚠️ Сохранено {ok} из {ok + failed} фото. Часть не удалось сохранить."

        if status_message is not None:
            try:
                await status_message.edit_text(text)
                return
            except Exception:
                logger.exception("failed to edit album status message")
        await reply_to.reply(text)
    except TimeoutError:
        logger.exception("album save timeout user_id=%s", user_id)
        await _album_fail_notify(reply_to, status_message, MSG_SAVE_TIMEOUT)
    except Exception:
        logger.exception("album save failed user_id=%s", user_id)
        await _album_fail_notify(reply_to, status_message, MSG_SAVE_FAILED)


async def _album_fail_notify(
    reply_to: types.Message,
    status_message: types.Message | None,
    text: str,
) -> None:
    try:
        if status_message is not None:
            try:
                await status_message.edit_text(text)
                return
            except Exception:
                pass
        await reply_to.reply(text)
    except Exception:
        logger.exception("failed to notify user about album save error")
