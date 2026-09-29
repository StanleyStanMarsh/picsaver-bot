import asyncio

from aiogram import Bot, F, Router, types

from bot_service.services import UsersService
from media_service.tools import save_image
from utils import APP_CTX

logger = APP_CTX.get_logger()
router = Router()


def _is_similar_caption(caption: str | None) -> bool:
    if not caption:
        return False
    head = caption.strip().split()[0].lower()
    return head in ("/similar", "/similar@pic_vault_bot")


@router.message(F.photo)
async def save_photo(message: types.Message, bot: Bot):
    if message.from_user is None:
        return
    # /similar handled in commands_router (registered first)
    if _is_similar_caption(message.caption):
        return

    photo = message.photo[-1]
    await message.reply("📸 Изображение сохраняется...")

    asyncio.create_task(save_and_notify(message, bot, photo.file_id))


async def save_and_notify(message: types.Message, bot: Bot, file_id: str):
    try:
        # FK images.user_id → users: ensure row exists before RQ job
        await UsersService().register_or_update_from_telegram(message.from_user)
        await save_image(bot=bot, user_id=message.from_user.id, file_id=file_id)
        await message.reply("✅ Изображение сохранено и проиндексировано")
    except Exception:
        logger.exception("save failed user_id=%s", getattr(message.from_user, "id", None))
        try:
            await message.reply("❌ Не удалось сохранить изображение. Попробуй ещё раз.")
        except Exception:
            logger.exception("failed to notify user about save error")
