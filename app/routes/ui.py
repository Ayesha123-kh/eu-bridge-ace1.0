import json
import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app import config
from app.db import connect

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))
templates.env.globals.update(app_name=config.APP_NAME, app_env=config.APP_ENV)

STATUS_LABELS = {
    "scanning": "Scanning",
    "ready_for_review": "Ready for review",
    "escalated": "Escalated: risk review needed",
    "pr_opened": "Pull request opened",
    "failed": "Scan failed",
}

ACTION_LABELS = {
    "scan_started": "Scan started",
    "finding_created": "AI suggested a fix",
    "escalated": "Scan escalated",
    "approved": "Fix approved",
    "edited_and_approved": "Fix edited and approved",
    "rejected": "Fix rejected",
    "risk_reviewed": "Risk tier reviewed",
    "pr_opened": "Pull request opened",
    "pr_failed": "Pull request failed",
}


def _fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return iso


def _summary(action: str, details: dict) -> str:
    if action == "scan_started":
        return details.get("repo", "")
    if action == "finding_created":
        return f"{details.get('rule_id', '')} in {details.get('file_path', '')}"
    if action in ("approved", "edited_and_approved", "rejected"):
        return f"{details.get('rule_id', '')}: {details.get('reason', '')}"
    if action == "risk_reviewed":
        return details.get("reason", "")
    if action == "escalated":
        return details.get("reason", "")
    if action == "pr_opened":
        return details.get("pr_url", "")
    if action == "pr_failed":
        return details.get("error", "")
    return ""


@router.get("/")
def index(request: Request):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT s.id, s.repo_owner, s.repo_name, s.status, s.created_at,"
            " (SELECT COUNT(*) FROM findings f WHERE f.scan_id = s.id) AS findings"
            " FROM scans s ORDER BY s.created_at DESC LIMIT 8").fetchall()
    finally:
        conn.close()
    scans = [{**dict(r), "status_label": STATUS_LABELS.get(r["status"], r["status"]),
              "when": _fmt_time(r["created_at"])} for r in rows]
    return templates.TemplateResponse(request, "index.html", {"scans": scans, "active": "new"})


@router.get("/scans/{scan_id}")
def scan_page(request: Request, scan_id: str):
    return templates.TemplateResponse(request, "scan.html", {"scan_id": scan_id, "active": ""})


@router.get("/audit")
def audit_page(request: Request):
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq DESC LIMIT 500").fetchall()
    finally:
        conn.close()
    entries = []
    for r in rows:
        try:
            details = json.loads(r["details_json"])
        except ValueError:
            details = {}
        entries.append({
            "seq": r["seq"], "when": _fmt_time(r["timestamp"]),
            "actor": {"ai": "AI", "system": "System"}.get(r["actor"], r["actor"]),
            "human": r["actor"] not in ("ai", "system"),
            "action": ACTION_LABELS.get(r["action"], r["action"]),
            "scan_id": r["scan_id"], "summary": _summary(r["action"], details),
            "hash": r["hash"][:12],
        })
    return templates.TemplateResponse(request, "audit.html", {"entries": entries, "active": "audit"})
