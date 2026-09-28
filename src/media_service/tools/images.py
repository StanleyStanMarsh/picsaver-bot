import asyncio
import os

from aiogram import Bot

from utils import setup_logger

setup_logger()

from utils import APP_CTX

from media_service.database.get_image import get_images
from media_service.qdrant_store import search_user_images
from redis_queue import save_queue

logger = APP_CTX.get_logger()

SAVE_JOB_TIMEOUT = int(os.getenv("SAVE_JOB_TIMEOUT", "600"))  # CLIP on CPU can be slow
EMBED_JOB_TIMEOUT = int(os.getenv("EMBED_JOB_TIMEOUT", "120"))

# String paths so RQ imports reliably inside the worker process
SAVE_JOB = "media_service.database.save_image.add_image"
EMBED_TEXT_JOB = "media_service.database.save_image.embed_text_job"


async def wait_for_job(job, timeout=30, interval=0.2):
    loop = asyncio.get_running_loop()
    start = loop.time()

    while True:
        await asyncio.to_thread(job.refresh)

        if job.is_finished:
            return job.result

        if job.is_failed:
            raise Exception(f"Job failed: {job.id}")

        if loop.time() - start > timeout:
            raise TimeoutError(f"Job timeout: {job.id}")

        await asyncio.sleep(interval)


async def save_image(bot: Bot, user_id: int, file_id: str):
    file = await bot.get_file(file_id)
    logger.info(f"Processing file {file.file_path} for user={user_id}")
    job = save_queue.enqueue(
        SAVE_JOB,
        kwargs={
            "user_id": user_id,
            "file_path": file.file_path,
            "file_id": file_id,
        },
        job_timeout=SAVE_JOB_TIMEOUT,
        result_ttl=600,
        failure_ttl=86400,
    )
    logger.info(f"Saving image job enqueued job.id={job.id}")
    return await wait_for_job(job, timeout=SAVE_JOB_TIMEOUT)


async def get_user_images(user_id: int):
    return await get_images(user_id)


async def search_user_images_by_text(user_id: int, query: str, limit: int = 20) -> list[dict]:
    """Encode query on CLIP worker, then search Qdrant filtered by user."""
    text = (query or "").strip()
    if not text:
        images = await get_images(user_id, limit=limit)
        return [{"file_id": img["file_id"], "score": None} for img in images]

    job = save_queue.enqueue(
        EMBED_TEXT_JOB,
        kwargs={"text": text},
        job_timeout=EMBED_JOB_TIMEOUT,
        result_ttl=120,
        failure_ttl=600,
    )
    vector = await wait_for_job(job, timeout=EMBED_JOB_TIMEOUT)
    return await asyncio.to_thread(
        search_user_images, vector=vector, user_id=user_id, limit=limit
    )
