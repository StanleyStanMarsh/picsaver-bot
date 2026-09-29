import asyncio
import os
from collections.abc import Callable
from typing import Any

from aiogram import Bot

from utils import setup_logger

setup_logger()

from utils import APP_CTX

from bot_service.services.save_limits import (
    SaveQuotaExceeded,
    check_queue_depth_or_raise,
    release_active_slot,
    try_acquire_active_slot,
)
from media_service.database.get_image import get_images
from media_service.qdrant_store import search_user_images
from redis_queue import save_queue

logger = APP_CTX.get_logger()

SAVE_JOB_TIMEOUT = int(os.getenv("SAVE_JOB_TIMEOUT", "600"))  # CLIP on CPU can be slow
EMBED_JOB_TIMEOUT = int(os.getenv("EMBED_JOB_TIMEOUT", "120"))

SEARCH_MIN_SCORE = float(os.getenv("SEARCH_MIN_SCORE", "0.25"))
SIMILAR_MIN_SCORE = float(os.getenv("SIMILAR_MIN_SCORE", "0.35"))

# String paths so RQ imports reliably inside the worker process
SAVE_JOB = "media_service.database.save_image.add_image"
EMBED_TEXT_JOB = "media_service.database.save_image.embed_text_job"
EMBED_IMAGE_JOB = "media_service.database.save_image.embed_image_job"

ProgressCallback = Callable[[str], Any]


async def wait_for_job(
    job,
    timeout=30,
    interval=0.2,
    on_tick: Callable[[Any], Any] | None = None,
):
    """Poll RQ job until finished/failed/timeout.

    ``on_tick`` is invoked after each refresh (e.g. to read job.meta['phase']).
    Callers must throttle Telegram edits themselves — do not spam on every tick.
    """
    loop = asyncio.get_running_loop()
    start = loop.time()

    while True:
        await asyncio.to_thread(job.refresh)

        if on_tick is not None:
            maybe = on_tick(job)
            if maybe is not None and asyncio.iscoroutine(maybe):
                await maybe

        if job.is_finished:
            return job.result

        if job.is_failed:
            raise Exception(f"Job failed: {job.id}")

        if loop.time() - start > timeout:
            raise TimeoutError(f"Job timeout: {job.id}")

        await asyncio.sleep(interval)


def _acquire_clip_slot(user_id: int) -> None:
    """L5 depth then L3 per-user slot; raise typed errors (no enqueue yet)."""
    depth = check_queue_depth_or_raise()
    logger.info("save queue depth=%s user_id=%s", depth, user_id)
    if not try_acquire_active_slot(user_id):
        raise SaveQuotaExceeded(
            f"user_id={user_id} active CLIP/save slots at limit"
        )


async def _enqueue_and_wait(
    *,
    user_id: int,
    job_path: str,
    kwargs: dict,
    job_timeout: int,
    result_ttl: int,
    failure_ttl: int,
    log_label: str,
    on_tick: Callable[[Any], Any] | None = None,
):
    """Enqueue onto save/CLIP queue with L5 depth + L3 active-slot guards."""
    await asyncio.to_thread(_acquire_clip_slot, user_id)
    try:
        job = save_queue.enqueue(
            job_path,
            kwargs=kwargs,
            job_timeout=job_timeout,
            result_ttl=result_ttl,
            failure_ttl=failure_ttl,
        )
        logger.info("%s enqueued job.id=%s user_id=%s", log_label, job.id, user_id)
        return await wait_for_job(job, timeout=job_timeout, on_tick=on_tick)
    finally:
        await asyncio.to_thread(release_active_slot, user_id)


async def save_image(
    bot: Bot,
    user_id: int,
    file_id: str,
    on_progress: ProgressCallback | None = None,
):
    """Download file meta from TG, enqueue worker job, wait for result.

    ``on_progress(phase)`` is called with coarse phase keys:
    download → queue → (worker meta: storage / clip / qdrant / done).
    CLIP stays on ``clip`` for the whole encode; no mid-forward ticks.
    """

    async def _emit(phase: str) -> None:
        if on_progress is None:
            return
        maybe = on_progress(phase)
        if maybe is not None and asyncio.iscoroutine(maybe):
            await maybe

    await _emit("download")
    file = await bot.get_file(file_id)
    logger.info(f"Processing file {file.file_path} for user={user_id}")

    await _emit("queue")

    last_phase: dict[str, str | None] = {"value": None}

    async def _on_tick(job) -> None:
        phase = (job.meta or {}).get("phase")
        if not phase or phase == last_phase["value"]:
            return
        last_phase["value"] = phase
        await _emit(phase)

    return await _enqueue_and_wait(
        user_id=user_id,
        job_path=SAVE_JOB,
        kwargs={
            "user_id": user_id,
            "file_path": file.file_path,
            "file_id": file_id,
        },
        job_timeout=SAVE_JOB_TIMEOUT,
        result_ttl=600,
        failure_ttl=86400,
        log_label="Saving image job",
        on_tick=_on_tick,
    )


async def get_user_images(user_id: int):
    return await get_images(user_id)


async def search_user_images_by_text(user_id: int, query: str, limit: int = 20) -> list[dict]:
    """Encode query on CLIP worker, then search Qdrant filtered by user + SEARCH_MIN_SCORE."""
    text = (query or "").strip()
    if not text:
        # Empty inline: Postgres list, no CLIP / no cutoff
        images = await get_images(user_id, limit=limit)
        return [{"file_id": img["file_id"], "score": None} for img in images]

    vector = await _enqueue_and_wait(
        user_id=user_id,
        job_path=EMBED_TEXT_JOB,
        kwargs={"text": text},
        job_timeout=EMBED_JOB_TIMEOUT,
        result_ttl=120,
        failure_ttl=600,
        log_label="Embed text job",
    )
    return await asyncio.to_thread(
        search_user_images,
        vector=vector,
        user_id=user_id,
        limit=limit,
        min_score=SEARCH_MIN_SCORE,
    )


async def search_user_images_by_photo(
    bot: Bot,
    user_id: int,
    file_id: str,
    limit: int = 3,
) -> list[dict]:
    """Embed query photo on CLIP worker, search own images; exclude source file_id."""
    file = await bot.get_file(file_id)
    vector = await _enqueue_and_wait(
        user_id=user_id,
        job_path=EMBED_IMAGE_JOB,
        kwargs={"file_path": file.file_path},
        job_timeout=EMBED_JOB_TIMEOUT,
        result_ttl=120,
        failure_ttl=600,
        log_label="Embed image job",
    )
    return await asyncio.to_thread(
        search_user_images,
        vector=vector,
        user_id=user_id,
        limit=limit,
        min_score=SIMILAR_MIN_SCORE,
        exclude_file_ids={file_id},
    )
