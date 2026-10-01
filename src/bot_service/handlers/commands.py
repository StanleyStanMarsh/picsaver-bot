from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot_service.services import UsersService
from bot_service.services.save_limits import (
    MSG_BUSY,
    MSG_QUOTA,
    SaveQuotaExceeded,
    SaveQueueBusy,
)
from media_service.tools.images import (
    search_user_images_by_photo,
    search_user_images_by_text,
)
from utils import APP_CTX

logger = APP_CTX.get_logger()
router = Router()

# HTML parse_mode (bot default)
FEEDBACK_URL = "https://forms.yandex.ru/u/6abe6a7df47e73767e0498df"
FEEDBACK_LINK_HTML = (
    f'<a href="{FEEDBACK_URL}">Сообщить об ошибке или предложить улучшения</a>'
)

START_TEXT = (
    "<b>Picsaver</b> — твои сохраненки. Бот предоставляет умное хранилище фото в Telegram 📸\n\n"
    "Привет! Я помогу тебе сохранять и быстро находить свои картинки, мемы и скриншоты прямо в Telegram.\n\n"
    "<b>Как пользоваться:</b>\n\n"
    "• <b>Сохранить фото</b>\n"
    "Просто пришли любое изображение в этот чат — я его сохраню в твою личную коллекцию.\n\n"
    "• <b>Найти фото</b>\n"
    "В любом чате набери <code>@pic_vault_bot</code> и свой запрос.\n"
    "Например: <code>@pic_vault_bot мем с котом</code> — я найду похожие среди твоих сохранённых фото.\n"
    "Или в этом чате: <code>/search мем с котом</code> и <code>/similar</code> + фото.\n\n"
    "• <b>Галерея</b>\n"
    "Открой Mini App (кнопка Open возле строки ввода), чтобы посмотреть все свои фото в удобной галерее и удалить ненужные.\n\n"
    "Кидай первое фото — и начнём ✨\n\n"
    "———\n"
    "β-версия\n"
    f"{FEEDBACK_LINK_HTML}"
)

def _is_similar_caption(caption: str | None) -> bool:
    if not caption:
        return False
    head = caption.strip().split()[0].lower()
    return head in ("/similar", "/similar@pic_vault_bot")


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    if user is not None:
        await UsersService().register_or_update_from_telegram(user)

    await message.answer(START_TEXT, parse_mode=ParseMode.HTML)


@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject):
    user = message.from_user
    if user is None:
        return

    query = (command.args or "").strip()
    if not query:
        await message.answer(
            "Напиши текст после команды, например:\n<code>/search мем с котом</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    await UsersService().register_or_update_from_telegram(user)
    status = await message.answer("🔍 Ищу…")
    try:
        hits = await search_user_images_by_text(user_id=user.id, query=query, limit=5)
    except SaveQueueBusy:
        logger.warning("/search busy user_id={}", user.id)
        await status.edit_text(MSG_BUSY)
        return
    except SaveQuotaExceeded:
        logger.warning("/search quota user_id={}", user.id)
        await status.edit_text(MSG_QUOTA)
        return
    except Exception:
        logger.exception("/search failed user_id={} query={!r}", user.id, query)
        await status.edit_text("❌ Не удалось выполнить поиск. Попробуй ещё раз.")
        return

    if not hits:
        await status.edit_text("Ничего не нашлось по этому запросу.")
        return

    await status.edit_text(f"Нашёл {len(hits)}:")
    for hit in hits:
        await message.answer_photo(hit["file_id"])


@router.message(Command("similar"), F.photo)
@router.message(F.photo, F.caption.func(_is_similar_caption))
async def cmd_similar_with_photo(message: Message):
    await _run_similar(message, message.photo[-1].file_id)


@router.message(Command("similar"))
async def cmd_similar(message: Message):
    reply = message.reply_to_message
    if reply is not None and reply.photo:
        await _run_similar(message, reply.photo[-1].file_id)
        return
    await message.answer(
        "Пришли фото с подписью <code>/similar</code>, "
        "или ответь <code>/similar</code> на своё фото.",
        parse_mode=ParseMode.HTML,
    )


async def _run_similar(message: Message, file_id: str) -> None:
    user = message.from_user
    if user is None:
        return

    await UsersService().register_or_update_from_telegram(user)
    status = await message.answer("🔎 Ищу похожие…")
    try:
        hits = await search_user_images_by_photo(
            bot=message.bot,
            user_id=user.id,
            file_id=file_id,
            limit=3,
        )
    except SaveQueueBusy:
        logger.warning("/similar busy user_id={}", user.id)
        await status.edit_text(MSG_BUSY)
        return
    except SaveQuotaExceeded:
        logger.warning("/similar quota user_id={}", user.id)
        await status.edit_text(MSG_QUOTA)
        return
    except Exception:
        logger.exception("/similar failed user_id={}", user.id)
        await status.edit_text("❌ Не удалось найти похожие. Попробуй ещё раз.")
        return

    if not hits:
        await status.edit_text("Похожих фото в твоей коллекции не нашлось.")
        return

    await status.edit_text(f"Нашёл {len(hits)} похожих:")
    for hit in hits:
        await message.answer_photo(hit["file_id"])
