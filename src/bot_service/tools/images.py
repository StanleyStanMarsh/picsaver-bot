from aiogram import Bot

from bot_service.database.models import add_image, get_images


async def save_image(bot: Bot, user_id: int, file_id: str):
    await add_image(bot, user_id, file_id)


async def get_user_images(user_id: int):
    return await get_images(user_id)