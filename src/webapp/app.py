"""Mini App API + static gallery."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from media_service.database.delete_image import (
    ImageNotFoundError,
    delete_user_image,
    list_user_images,
    resolve_user_image_path,
)
from webapp.auth import AuthError, validate_webapp_init_data

STATIC_DIR = Path(__file__).resolve().parent / "static"
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = FastAPI(title="Picsaver Mini App", docs_url=None, redoc_url=None)


def _extract_init_data(
    authorization: str | None,
    x_telegram_init_data: str | None,
) -> str:
    if authorization and authorization.lower().startswith("tma "):
        return authorization[4:].strip()
    if x_telegram_init_data:
        return x_telegram_init_data.strip()
    raise HTTPException(status_code=401, detail="Telegram auth required")


def current_user_id(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> int:
    try:
        init_data = _extract_init_data(authorization, x_telegram_init_data)
        payload = validate_webapp_init_data(init_data, BOT_TOKEN)
        return payload["user_id"]
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/images")
def api_list_images(user_id: int = Depends(current_user_id)):
    items = list_user_images(user_id=user_id)
    return {"images": items}


@app.get("/api/images/{image_id}/file")
def api_image_file(image_id: UUID, user_id: int = Depends(current_user_id)):
    try:
        path = resolve_user_image_path(user_id=user_id, image_id=image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="image/jpeg", filename=f"{image_id}.jpg")


@app.delete("/api/images/{image_id}")
def api_delete_image(image_id: UUID, user_id: int = Depends(current_user_id)):
    try:
        return delete_user_image(user_id=user_id, image_id=image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete failed: {e}") from e


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="static missing")
    return FileResponse(index_path)


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
