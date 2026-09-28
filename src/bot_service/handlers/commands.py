from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot_service.services import UsersService
from utils import APP_CTX

logger = APP_CTX.get_logger()
router = Router()

# Exact copy for /start (plain text; backticks are literal for the user)
START_TEXT = (
    "Picsaver — умное сохры в Telegram.\n"
    "\n"
    "• Пришли фото в этот чат и я их сохраню.\n"
    "• Inline-поиск: набери в любом чате `@pic_vault_bot запрос` "
    "(например, запрос «мем с котом») — найду похожие среди твоих.\n"
    "• В Mini App — галерея всех твоих фото с возможностью удаления ненужных."
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    if user is not None:
        await UsersService().register_or_update_from_telegram(user)

    # Override bot-wide HTML so backticks/quotes stay as written
    await message.answer(START_TEXT, parse_mode=None)
