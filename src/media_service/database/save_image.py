"""RQ job: download Telegram photo → Postgres → CLIP → Qdrant."""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import text
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bot_service.config import BOT_TOKEN, PROXY_FULL_ADDRESS
from db.models import Image
from db.sync_session import get_sync_sessionmaker
from media_service.clip import embed_image_path
from media_service.paths import IMAGES_DIR
from media_service.qdrant_store import upsert_image_vector

FILE_STATUS_STORED = 2  # seed order: uploaded=1, stored=2, ...
INDEX_STATUS_INDEXING = 2
INDEX_STATUS_READY = 3
INDEX_STATUS_ERROR = 4


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
    """
    Persist photo for user and index it for semantic search.
    Returns {"image_id": str, "file_id": str}.
    """
    user_dir = IMAGES_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    image_id = uuid.uuid4()
    file_name = f"{image_id}.jpg"
    save_path = user_dir / file_name

    proxy = PROXY_FULL_ADDRESS if PROXY_FULL_ADDRESS and "None" not in PROXY_FULL_ADDRESS else None
    try:
        download_image_by_file_path(
            bot_token=BOT_TOKEN,
            file_path=file_path,
            save_path=str(save_path),
            proxy=proxy,
        )
    except Exception as e:
        raise Exception(f"Failed downloading picture with file_path={file_path}: {e}") from e

    digest = _content_hash(save_path)
    now = datetime.now(tz=timezone.utc)
    relative_path = f"{user_id}/{file_name}"

    Session = get_sync_sessionmaker()
    with Session() as session:
        # FK: user must exist (bot registers on /start and before enqueue)
        model_id = _embedding_model_id(session)
        row = Image(
            image_id=image_id,
            path=relative_path,
            extension="jpg",
            user_id=user_id,
            telegram_file_id=file_id,
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
        vector = embed_image_path(str(save_path))
        upsert_image_vector(
            image_id=image_id,
            vector=vector,
            user_id=user_id,
            telegram_file_id=file_id,
            local_path=relative_path,
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

    return {"image_id": str(image_id), "file_id": file_id}


def embed_text_job(text: str) -> list[float]:
    """RQ job used by inline search — runs on the same CLIP worker."""
    from media_service.clip import embed_text

    return embed_text(text)
