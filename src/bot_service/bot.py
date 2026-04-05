import socket

from aiogram.client.session.aiohttp import AiohttpSession

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import aiohttp

from bot_service.config import BOT_TOKEN, PROXY_FULL_ADDRESS, PROXY_KEY
from bot_service.handlers import inline_router, messages_router

from utils import APP_CTX


logger = APP_CTX.get_logger()


async def main():
    # auth = BasicAuth(PROXY_KEY)
    session = AiohttpSession(proxy=PROXY_FULL_ADDRESS)


    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session
    )

    dp = Dispatcher()

    dp.include_router(messages_router)
    dp.include_router(inline_router)

    logger.info(f"Connecting to Telegram API via proxy: {PROXY_FULL_ADDRESS}")

    await dp.start_polling(bot)
