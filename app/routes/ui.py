import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import os

from app import config
from app.db import connect
from app.services import regulations
from app.services.dashboard import ACTION_LABELS, STATUS_LABELS, display_name, fmt_time, summary

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))
_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
_ASSET_V = str(int(max(os.path.getmtime(os.path.join(_STATIC, f)) for f in os.listdir(_STATIC))))
templates.env.globals.update(app_name=config.APP_NAME, app_env=config.APP_ENV, asset_v=_ASSET_V)


def render(request: Request, name: str, ctx: dict | None = None):
    user = getattr(request.state, "user", None)
    return templates.TemplateResponse(request, name, {**(ctx or {}), "user": user})


@router.get("/")
def dashboard_page(request: Request):
    return render(request, "dashboard.html", {"active": "dashboard"})


@router.get("/signin")
def signin(request: Request, mode: str = "signin", next: str = "/"):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    return render(request, "signin.html", {"active": "signin", "mode": mode if mode in ("signin", "signup") else "signin",
                                           "next": next if next.startswith("/") and not next.startswith("//") else "/"})


@router.get("/explore")
def explore(request: Request):
    return render(request, "explore.html", {
        "active": "explore", "offers": regulations.OFFERS, "tiers": regulations.AI_TIERS,
        "reviewed_on": regulations.REVIEWED_ON})


@router.get("/new")
def new_scan(request: Request):
    return render(request, "new.html", {"active": "new"})


@router.get("/scans/{scan_id}")
def scan_page(request: Request, scan_id: str):
    return render(request, "scan.html", {"scan_id": scan_id, "active": ""})


@router.get("/audit")
def audit_page(request: Request, scan: str = ""):
    owner = request.state.owner
    conn = connect()
    try:
        scans = [dict(r) for r in conn.execute(
            "SELECT id, repo_owner, repo_name, source FROM scans WHERE owner=? ORDER BY created_at DESC", (owner,))]
        rows = conn.execute(
            "SELECT a.* FROM audit_log a JOIN scans s ON s.id = a.scan_id WHERE s.owner=? "
            "ORDER BY a.seq DESC LIMIT 2000", (owner,)).fetchall()
    finally:
        conn.close()
    names = {s["id"]: display_name(s) for s in scans}
    entries = []
    for r in rows:
        try:
            details = json.loads(r["details_json"])
        except ValueError:
            details = {}
        human = r["actor"] not in ("ai", "system")
        entries.append({
            "seq": r["seq"], "when": fmt_time(r["timestamp"]),
            "actor": {"ai": "AI", "system": "System"}.get(r["actor"], r["actor"]),
            "actor_kind": "person" if human else r["actor"], "human": human,
            "action": ACTION_LABELS.get(r["action"], r["action"]), "action_key": r["action"],
            "scan_id": r["scan_id"], "company": names.get(r["scan_id"], ""),
            "summary": summary(r["action"], details), "hash": r["hash"][:12],
        })
    people = sorted({e["actor"] for e in entries if e["human"]})
    actions = sorted({(e["action_key"], e["action"]) for e in entries})
    return render(request, "audit.html", {
        "entries": entries, "active": "audit", "scans": scans, "names": names,
        "people": people, "actions": actions, "selected_scan": scan})
