import json
from pathlib import Path

IMAGES_DIR = Path("images")


async def get_images(user_id: int):
    """
    Получаем список изображений пользователя напрямую из meta.json
    """
    user_dir = IMAGES_DIR / str(user_id)
    meta_file = user_dir / "meta.json"

    if not meta_file.exists():
        return []

    import aiofiles

    async with aiofiles.open(meta_file, "r", encoding="utf-8") as f:
        content = await f.read()
        if content:
            return json.loads(content)
        return []