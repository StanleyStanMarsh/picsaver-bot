from sqlalchemy import select

from db.models import Image
from db.session import get_sessionmaker

# seed: ready = 3
INDEX_STATUS_READY = 3


async def get_images(user_id: int, limit: int = 50):
    """Latest ready images for user from Postgres (telegram file_id for inline)."""
    Session = get_sessionmaker()
    async with Session() as session:
        result = await session.scalars(
            select(Image)
            .where(
                Image.user_id == user_id,
                Image.deleted_at.is_(None),
                Image.index_status == INDEX_STATUS_READY,
            )
            .order_by(Image.created_at.desc())
            .limit(limit)
        )
        rows = result.all()
        return [
            {
                "file_id": row.telegram_file_id,
                "image_id": str(row.image_id),
                "local_path": row.path,
            }
            for row in rows
        ]
