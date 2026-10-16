from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app import config

config.validate_env()

app = FastAPI(title=config.APP_NAME)


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
