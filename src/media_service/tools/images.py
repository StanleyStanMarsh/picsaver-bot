import asyncio

from aiogram import Bot

from utils import setup_logger

setup_logger()

from utils import APP_CTX

from ..database import add_image, get_images

from redis_queue import save_queue, read_queue

logger = APP_CTX.get_logger()


async def wait_for_job(job, timeout=30, interval=0.2):
    loop = asyncio.get_event_loop()
    start = loop.time()

    while True:
        job.refresh()

        if job.is_finished:
            return True

        if job.is_failed:
            raise Exception("Saving image failed")

        if loop.time() - start > timeout:
            raise TimeoutError("Saving image timeout")

        await asyncio.sleep(interval)


async def save_image(bot: Bot, user_id: int, file_id: str):
    file = await bot.get_file(file_id)
    logger.info(f"Processing file {file}...")
    job = save_queue.enqueue(
        add_image,
        kwargs={
            "user_id": user_id,
            "file_path": file.file_path,
            "file_id": file_id
        }
    )

    logger.info(f"Saving image job is enqueued with job.id={job.id}")
    await wait_for_job(job)
    

async def get_user_images(user_id: int):
    logger.info(f"Getting images...")
    return await get_images(user_id)