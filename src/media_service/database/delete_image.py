"""Delete user image from Postgres, storage, and Qdrant."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from db.models import Image
from db.sync_session import get_sync_sessionmaker
from media_service.paths import IMAGES_DIR
from media_service.qdrant_store import delete_image_vector
from media_service.storage import get_storage


class ImageNotFoundError(LookupError):
    pass


def delete_user_image(*, user_id: int, image_id: UUID) -> dict:
    """
    Remove from search (Qdrant), soft-delete in Postgres, delete from storage.
    Ownership is enforced by user_id.
    """
    Session = get_sync_sessionmaker()
    with Session() as session:
        img = session.get(Image, image_id)
        if img is None or img.user_id != user_id or img.deleted_at is not None:
            raise ImageNotFoundError(str(image_id))
        relative_path = img.path

    # Drop vector first so inline search cannot surface a soft-deleted row
    delete_image_vector(image_id=image_id)

    with Session() as session:
        img = session.get(Image, image_id)
        if img is None or img.user_id != user_id:
            raise ImageNotFoundError(str(image_id))
        if img.deleted_at is None:
            now = datetime.now(tz=timezone.utc)
            img.deleted_at = now
            img.updated_at = now
            session.commit()

    try:
        get_storage().delete(relative_path)
    except Exception:
        pass

    return {"image_id": str(image_id), "deleted": True}


def list_user_images(*, user_id: int, limit: int = 200) -> list[dict]:
    """All non-deleted images for gallery (newest first)."""
    Session = get_sync_sessionmaker()
    with Session() as session:
        rows = session.scalars(
            select(Image)
            .where(Image.user_id == user_id, Image.deleted_at.is_(None))
            .order_by(Image.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "image_id": str(row.image_id),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "path": row.path,
            }
            for row in rows
        ]


def resolve_user_image_path(*, user_id: int, image_id: UUID) -> Path:
    """
    Resolve local disk path when the object lives under IMAGES_DIR.
    Prefer resolve_user_image_bytes for storage-agnostic serving.
    """
    Session = get_sync_sessionmaker()
    with Session() as session:
        img = session.get(Image, image_id)
        if img is None or img.user_id != user_id or img.deleted_at is not None:
            raise ImageNotFoundError(str(image_id))
        path = IMAGES_DIR / img.path
        if not path.is_file():
            raise ImageNotFoundError(str(image_id))
        return path


def resolve_user_image_bytes(*, user_id: int, image_id: UUID) -> bytes:
    """Fetch image bytes via STORAGE_BACKEND (MinIO and/or local)."""
    Session = get_sync_sessionmaker()
    with Session() as session:
        img = session.get(Image, image_id)
        if img is None or img.user_id != user_id or img.deleted_at is not None:
            raise ImageNotFoundError(str(image_id))
        key = img.path

    try:
        return get_storage().open_bytes(key)
    except FileNotFoundError as e:
        raise ImageNotFoundError(str(image_id)) from e
    except Exception as e:
        raise ImageNotFoundError(str(image_id)) from e
