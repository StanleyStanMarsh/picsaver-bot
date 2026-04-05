import uuid

from aiogram import Router, types
from aiogram.types import InlineQueryResultCachedPhoto

from media_service.tools import get_user_images

router = Router()


@router.inline_query()
async def inline_query(query: types.InlineQuery):
    images = await get_user_images(query.from_user.id)

    results = []

    for image in images:
        results.append(
            InlineQueryResultCachedPhoto(
                id=str(uuid.uuid4()),
                photo_file_id=image["file_id"],
                caption="📸 Picsaver"
            )
        )

    await query.answer(
        results,
        cache_time=10,
        is_personal=True
    )