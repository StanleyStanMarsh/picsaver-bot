import os

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot_service.services import UsersService
from utils import APP_CTX

logger = APP_CTX.get_logger()
router = Router()

START_TEXT = (
    "<b>Picsaver</b> — умное хранилище твоих фото в Telegram.\n\n"
    "• Пришли фото в этот чат — сохраню и проиндексирую.\n"
    "• Inline-поиск: набери <code>@бот запрос</code> "
    "(например «радуга») — найду похожие среди твоих.\n"
    "• Пустой inline — список последних сохранённых.\n"
    "• Mini App — галерея всех фото и удаление ненужных.\n\n"
    "Фото других пользователей тебе не видны."
)


def _start_keyboard() -> InlineKeyboardMarkup | None:
    url = (os.getenv("WEBAPP_URL") or "").strip()
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Мои фото",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    if user is not None:
        await UsersService().register_or_update_from_telegram(user)

    await message.answer(START_TEXT, reply_markup=_start_keyboard())
