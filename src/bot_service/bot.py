from aiogram.client.session.aiohttp import AiohttpSession

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot_service.config import BOT_TOKEN, PROXY_FULL_ADDRESS
from bot_service.handlers import commands_router, inline_router, messages_router

from utils import APP_CTX
from db.session import dispose_engine, init_engine


logger = APP_CTX.get_logger()


async def main():
    session = AiohttpSession(proxy=PROXY_FULL_ADDRESS) if PROXY_FULL_ADDRESS else AiohttpSession()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session
    )

    dp = Dispatcher()

    await init_engine()

    dp.include_router(messages_router)
    dp.include_router(commands_router)
    dp.include_router(inline_router)

    if PROXY_FULL_ADDRESS:
        logger.info("Connecting to Telegram API via proxy")
    else:
        logger.info("Connecting to Telegram API without proxy")

    try:
        await dp.start_polling(bot)
    finally:
        await dispose_engine()
