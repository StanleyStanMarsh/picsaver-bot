from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from utils import APP_CTX
from bot_service.services import UsersService


logger = APP_CTX.get_logger()
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    if user is None:
        await message.answer("Добро пожаловать")
        return

    await UsersService().register_or_update_from_telegram(user)

    await message.answer("Добро пожаловать")

