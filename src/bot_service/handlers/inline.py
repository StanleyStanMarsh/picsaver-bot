import uuid

from aiogram import Router, types
from aiogram.types import InlineQueryResultCachedPhoto

from media_service.tools.images import search_user_images_by_text
from utils import APP_CTX

logger = APP_CTX.get_logger()
router = Router()

# Telegram inline soft-cap
MAX_RESULTS = 50


@router.inline_query()
async def inline_query(query: types.InlineQuery):
    user = query.from_user
    if user is None:
        await query.answer([], cache_time=1, is_personal=True)
        return

    try:
        images = await search_user_images_by_text(
            user_id=user.id,
            query=query.query or "",
            limit=MAX_RESULTS,
        )
    except Exception:
        logger.exception("inline search failed user_id=%s query=%r", user.id, query.query)
        await query.answer(
            [],
            cache_time=1,
            is_personal=True,
            switch_pm_text="Ошибка поиска, открой бота",
            switch_pm_parameter="start",
        )
        return

    results = []
    for image in images[:MAX_RESULTS]:
        results.append(
            InlineQueryResultCachedPhoto(
                id=str(image.get("image_id") or uuid.uuid4()),
                photo_file_id=image["file_id"],
            )
        )

    kwargs = {
        "cache_time": 10,
        "is_personal": True,
    }
    if not results:
        kwargs["switch_pm_text"] = "Сохрани фото в боте"
        kwargs["switch_pm_parameter"] = "start"

    await query.answer(results, **kwargs)
