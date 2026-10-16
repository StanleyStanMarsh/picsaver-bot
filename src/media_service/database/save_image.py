"""RQ job: download Telegram photo/GIF → storage → Postgres → CLIP → Qdrant."""
from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from rq import get_current_job
from sqlalchemy import text
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bot_service.config import BOT_TOKEN, PROXY_FULL_ADDRESS
from db.models import Image
from db.sync_session import get_sync_sessionmaker
from media_service.qdrant_store import upsert_image_vector
from media_service.storage import get_storage
from loguru import logger

FILE_STATUS_STORED = 2  # seed order: uploaded=1, stored=2, ...
INDEX_STATUS_INDEXING = 2
INDEX_STATUS_READY = 3
INDEX_STATUS_ERROR = 4


def _set_job_phase(phase: str) -> None:
    """Publish coarse phase for bot status UI. No mid-CLIP ticks."""
    job = get_current_job()
    if job is None:
        return
    job.meta["phase"] = phase
    job.save_meta()


def _embedding_model_id(session) -> int | None:
    row = session.execute(
        text("SELECT embedding_model_id FROM embedding_models WHERE model_name = :n LIMIT 1"),
        {"n": os.getenv("CLIP_MODEL_NAME", "jinaai/jina-clip-v2")},
    ).first()
    return int(row[0]) if row else None


@retry(
    retry=retry_if_exception_type(requests.exceptions.Timeout),
    wait=wait_exponential(max=5),
    stop=stop_after_attempt(5),
    reraise=True,
)
def download_image_by_file_path(
    bot_token: str, file_path: str, save_path: str, proxy: str | None = None
):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    response = requests.get(
        download_url, proxies=proxies, stream=True, timeout=(10, 120)
    )
    response.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def _content_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def add_image(user_id: int, file_path: str, file_id: str) -> dict:
    """Photo save job (unchanged RQ path)."""
    return _add_media(user_id=user_id, file_path=file_path, file_id=file_id, media_type="photo")


def add_gif(user_id: int, file_path: str, file_id: str) -> dict:
    """GIF save job: mp4 → storage; first/mid/last frames → mean vector."""
    return _add_media(user_id=user_id, file_path=file_path, file_id=file_id, media_type="gif")


def _add_media(user_id: int, file_path: str, file_id: str, media_type: str) -> dict:
    """
    Persist photo for user and index it for semantic search.
    Downloads to a tempfile, stores via STORAGE_BACKEND, embeds from temp.
    Returns {"image_id": str, "file_id": str}.

    Publishes job.meta['phase'] at coarse steps only (download / storage /
    clip / qdrant). CLIP phase is set once at encode START — never mid-forward.
    """
    is_gif = media_type == "gif"
    ext = "mp4" if is_gif else "jpg"
    content_type = "video/mp4" if is_gif else "image/jpeg"
    image_id = uuid.uuid4()
    file_name = f"{image_id}.{ext}"
    relative_path = f"{user_id}/{file_name}"

    proxy = PROXY_FULL_ADDRESS if PROXY_FULL_ADDRESS and "None" not in PROXY_FULL_ADDRESS else None

    tmp_path: str | None = None
    try:
        _set_job_phase("download")
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            download_image_by_file_path(
                bot_token=BOT_TOKEN,
                file_path=file_path,
                save_path=tmp_path,
                proxy=proxy,
            )
        except Exception as e:
            raise Exception(f"Failed downloading picture with file_path={file_path}: {e}") from e

        digest = _content_hash(Path(tmp_path))
        now = datetime.now(tz=timezone.utc)

        _set_job_phase("storage")
        storage = get_storage()
        storage.put_file(relative_path, tmp_path, content_type=content_type)

        Session = get_sync_sessionmaker()
        with Session() as session:
            # FK: user must exist (bot registers on /start and before enqueue)
            model_id = _embedding_model_id(session)
            row = Image(
                image_id=image_id,
                path=relative_path,
                extension=ext,
                user_id=user_id,
                telegram_file_id=file_id,
                media_type=media_type,
                file_status=FILE_STATUS_STORED,
                content_hash=digest,
                embedding_model=model_id,
                index_status=INDEX_STATUS_INDEXING,
                index_attempts=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()

        try:
            # One phase at encode START; bar may sit here for tens of seconds (CPU).
            if is_gif:
                vector = _embed_gif(tmp_path, user_id=user_id)
            else:
                from media_service.clip import embed_image_path

                _set_job_phase("clip")
                vector = embed_image_path(tmp_path)

            _set_job_phase("qdrant")
            upsert_image_vector(
                image_id=image_id,
                vector=vector,
                user_id=user_id,
                telegram_file_id=file_id,
                local_path=relative_path,
                media_type=media_type,
            )
            with Session() as session:
                img = session.get(Image, image_id)
                if img:
                    img.index_status = INDEX_STATUS_READY
                    img.indexed_at = datetime.now(tz=timezone.utc)
                    img.updated_at = datetime.now(tz=timezone.utc)
                    img.last_index_error = None
                    session.commit()
        except Exception as e:
            with Session() as session:
                img = session.get(Image, image_id)
                if img:
                    img.index_status = INDEX_STATUS_ERROR
                    img.last_index_error = str(e)[:2000]
                    img.updated_at = datetime.now(tz=timezone.utc)
                    session.commit()
            raise

        _set_job_phase("done")
        return {"image_id": str(image_id), "file_id": file_id}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _embed_gif(src_path: str, *, user_id: int) -> list[float]:
    """Extract first/mid/last frames (ffmpeg), mean of L2-normalised vectors."""
    from media_service.clip import embed_image_paths_mean
    from media_service.gif_frames import extract_key_frames

    with tempfile.TemporaryDirectory(prefix="gif_frames_") as frames_dir:
        frames = extract_key_frames(src_path, frames_dir)
        logger.info(
            "gif frames user_id={} media_type=gif frames={}", user_id, len(frames)
        )
        _set_job_phase("clip")
        return embed_image_paths_mean([str(f) for f in frames])


def embed_text_job(text: str) -> list[float]:
    """RQ job used by inline search — runs on the same CLIP worker."""
    from media_service.clip import embed_text

    return embed_text(text)


def embed_image_job(file_path: str) -> list[float]:
    """RQ job: download Telegram file to temp, CLIP image embed, delete temp."""
    from media_service.clip import embed_image_path

    proxy = PROXY_FULL_ADDRESS if PROXY_FULL_ADDRESS and "None" not in PROXY_FULL_ADDRESS else None
    suffix = Path(file_path).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
    try:
        download_image_by_file_path(
            bot_token=BOT_TOKEN,
            file_path=file_path,
            save_path=tmp_path,
            proxy=proxy,
        )
        return embed_image_path(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
