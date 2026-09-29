"""Mini App API + static gallery + password-protected /admin."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from media_service.database.delete_image import (
    ImageNotFoundError,
    delete_user_image,
    list_user_images,
    resolve_user_image_bytes,
)
from webapp.admin_auth import (
    admin_password,
    clear_session_cookie,
    is_locked,
    mint_session_token,
    register_login_failure,
    register_login_success,
    require_admin_session,
    set_session_cookie,
    verify_password,
    verify_session_token,
    COOKIE_NAME,
)
from webapp.admin_stats import fetch_user_stats
from webapp.auth import AuthError, validate_webapp_init_data

WEBAPP_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEBAPP_DIR / "static"
ADMIN_HTML = WEBAPP_DIR / "templates" / "admin.html"
LOGIN_HTML = WEBAPP_DIR / "templates" / "login.html"
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = FastAPI(title="Picsaver Mini App", docs_url=None, redoc_url=None)


@app.middleware("http")
async def admin_no_store(request, call_next):
    response: Response = await call_next(request)
    path = request.url.path
    if path.startswith("/admin") or path.startswith("/api/admin"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


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


def _login_page(error: str = "") -> HTMLResponse:
    html = LOGIN_HTML.read_text(encoding="utf-8")
    html = html.replace("__ERROR__", error)
    status = 401 if error else 200
    return HTMLResponse(html, status_code=status)


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
        data = resolve_user_image_bytes(user_id=user_id, image_id=image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Content-Disposition": f'inline; filename="{image_id}.jpg"'},
    )


@app.delete("/api/images/{image_id}")
def api_delete_image(image_id: UUID, user_id: int = Depends(current_user_id)):
    try:
        return delete_user_image(user_id=user_id, image_id=image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="delete failed") from e


@app.get("/api/admin/stats")
def api_admin_stats(request: Request, _admin: str = Depends(require_admin_session)):
    return fetch_user_stats()


@app.get("/admin")
def admin_page(request: Request):
    if not admin_password():
        raise HTTPException(status_code=503, detail="admin disabled")
    if not ADMIN_HTML.is_file() or not LOGIN_HTML.is_file():
        raise HTTPException(status_code=500, detail="admin static missing")

    token = request.cookies.get(COOKIE_NAME)
    if verify_session_token(token):
        return FileResponse(ADMIN_HTML)
    return _login_page()


@app.post("/admin/login")
async def admin_login(
    request: Request,
    username: str = Form(default=""),
    password: str = Form(default=""),
):
    if not admin_password():
        raise HTTPException(status_code=503, detail="admin disabled")

    if is_locked(request):
        return _login_page("Слишком много попыток. Подожди несколько минут.")

    # Empty submit — show form again, do not burn fail budget
    if not password:
        return _login_page("Введи пароль.")

    if not verify_password(username, password):
        register_login_failure(request)
        if is_locked(request):
            return _login_page("Слишком много попыток. Подожди несколько минут.")
        return _login_page("Неверный логин или пароль.")

    register_login_success(request)
    response = RedirectResponse(url="/admin", status_code=303)
    set_session_cookie(response, mint_session_token())
    return response


@app.post("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin", status_code=303)
    clear_session_cookie(response)
    return response


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="static missing")
    return FileResponse(index_path)


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
