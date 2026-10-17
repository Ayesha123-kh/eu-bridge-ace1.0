import os
import re
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config

config.validate_env()

from app.db import init_db  # noqa: E402
from app.routes import api, ui  # noqa: E402
from app.services import auth  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)
GUEST_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")


@app.middleware("http")
async def identity(request, call_next):
    """Attach who is calling: a signed-in user, or an anonymous guest tied to a cookie."""
    path = request.url.path
    if path == "/healthz" or path.startswith("/static/"):
        return await call_next(request)
    user = auth.user_for_token(request.cookies.get(api.SESSION_COOKIE))
    guest = request.cookies.get(api.GUEST_COOKIE, "")
    fresh = None
    if not GUEST_RE.fullmatch(guest):
        guest = fresh = secrets.token_urlsafe(16)
    request.state.user = user
    request.state.guest_id = guest
    request.state.owner = f"u:{user['id']}" if user else f"g:{guest}"
    response = await call_next(request)
    if fresh:
        response.set_cookie(api.GUEST_COOKIE, fresh, max_age=60 * 60 * 24 * 365, httponly=True,
                            samesite="lax", secure=api.is_https(request))
    return response


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
app.include_router(api.router)
app.include_router(ui.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
