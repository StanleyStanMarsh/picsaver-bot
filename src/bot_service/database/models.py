import uuid
from pathlib import Path
import json

import aiofiles
from aiogram import Bot

IMAGES_DIR = Path("images")


async def add_image(bot: Bot, user_id: int, file_id: str):
    user_dir = IMAGES_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    file = await bot.get_file(file_id)
    file_bytes = await bot.download_file(file.file_path)

    file_name = f"{uuid.uuid4()}.jpg"
    file_path = user_dir / file_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_bytes.read())

    # сохраняем file_id
    meta_file = user_dir / "meta.json"

    data = []

    if meta_file.exists():
        async with aiofiles.open(meta_file, "r") as f:
            content = await f.read()
            if content:
                data = json.loads(content)

    data.append({
        "file_id": file_id,
        "path": file_name
    })

    async with aiofiles.open(meta_file, "w") as f:
        await f.write(json.dumps(data))


async def get_images(user_id: int):
    user_dir = IMAGES_DIR / str(user_id)
    meta_file = user_dir / "meta.json"

    if not meta_file.exists():
        return []

    async with aiofiles.open(meta_file, "r") as f:
        data = json.loads(await f.read())

    return data