from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot_service.services import UsersService
from utils import APP_CTX

logger = APP_CTX.get_logger()
router = Router()

# HTML parse_mode (bot default): **…** → <b>, `…` → <code>
START_TEXT = (
    "<b>Picsaver</b> — твои сохраненки. Бот предоставляет умное хранилище фото в Telegram 📸\n"
    "\n"
    "Привет! Я помогу тебе сохранять и быстро находить свои картинки, мемы и скриншоты прямо в Telegram.\n"
    "\n"
    "<b>Как пользоваться:</b>\n"
    "\n"
    "• <b>Сохранить фото</b>\n"
    "Просто пришли любое изображение в этот чат — я его сохраню в твою личную коллекцию.\n"
    "\n"
    "• <b>Найти фото</b>\n"
    "В любом чате набери <code>@pic_vault_bot</code> и свой запрос.\n"
    "Например: <code>@pic_vault_bot мем с котом</code> — я найду похожие среди твоих сохранённых фото.\n"
    "\n"
    "• <b>Галерея</b>\n"
    "Открой Mini App (кнопка Open возле строки ввода), чтобы посмотреть все свои фото в удобной галерее и удалить ненужные.\n"
    "\n"
    "Кидай первое фото — и начнём ✨"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    if user is not None:
        await UsersService().register_or_update_from_telegram(user)

    await message.answer(START_TEXT, parse_mode=ParseMode.HTML)
