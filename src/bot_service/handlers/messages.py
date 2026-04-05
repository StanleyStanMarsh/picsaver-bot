import asyncio

from aiogram import Bot
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from utils import APP_CTX

from media_service.tools import save_image

logger = APP_CTX.get_logger()

router = Router()


@router.message(F.photo)
async def save_photo(message: types.Message, bot: Bot):
    photo = message.photo[-1]

    await message.reply("📸 Изображение сохраняется...")

    asyncio.create_task(
        save_and_notify(
            message,
            bot,
            photo.file_id
        )
    )


async def save_and_notify(message: types.Message, bot: Bot, file_id: str):
    await save_image(
        bot=bot,
        user_id=message.from_user.id,
        file_id=file_id
    )

    await message.reply("✅ Изображение сохранено")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer('Добро пожаловать')
