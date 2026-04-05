from aiogram import Bot
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from utils import APP_CTX

from bot_service.tools.images import save_image

logger = APP_CTX.get_logger()

router = Router()


@router.message(F.photo)
async def save_photo(message: types.Message, bot: Bot):
    photo = message.photo[-1]

    await save_image(
        bot=bot,
        user_id=message.from_user.id,
        file_id=photo.file_id
    )

    logger.info("Image saved")

    await message.answer("📸 Изображение сохранено")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer('Добро пожаловать')
