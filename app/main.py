from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app import config

config.validate_env()

from app.db import init_db  # noqa: E402
from app.routes import api  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)
app.include_router(api.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    badge = " [STAGING]" if config.APP_ENV == "staging" else ""
    return (
        f"<h1>{config.APP_NAME}{badge}</h1>"
        "<p>EU-Bridge uses AI to suggest fixes. Every change is reviewed by a human.</p>"
        "<p><small>Decision support, not legal advice.</small></p>"
    )
