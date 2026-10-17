import json
import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app import config
from app.db import connect
from app.services import audit, regulations

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
    "patch_exported": "Fixes downloaded",
}


def _fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return iso


def _short(text: str, n: int = 110) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


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


CHECKS = [("AIA-50-1", "AI disclosure"), ("GDPR-13", "Third-party AI notice"),
          ("GDPR-5-1C", "Personal data in logs")]
OPEN_STATUSES = ("ready_for_review", "escalated")


def _dashboard() -> dict:
    conn = connect()
    try:
        scans = [dict(r) for r in conn.execute("SELECT * FROM scans ORDER BY created_at DESC")]
        findings = [dict(r) for r in conn.execute("SELECT scan_id, rule_id, status FROM findings")]
        recent = conn.execute("SELECT * FROM audit_log ORDER BY seq DESC LIMIT 6").fetchall()
        exported = conn.execute(
            "SELECT COUNT(DISTINCT scan_id) AS n FROM audit_log WHERE action='patch_exported'"
        ).fetchone()["n"]
    finally:
        conn.close()

    by_scan = {s["id"]: s for s in scans}
    waiting_states = ("pending", "needs_human")
    approved_states = ("approved", "applied", "apply_failed")
    open_waiting = [f for f in findings if f["status"] in waiting_states
                    and by_scan.get(f["scan_id"], {}).get("status") in OPEN_STATUSES]

    attention = []
    for sc in scans:
        if sc["status"] not in OPEN_STATUSES:
            continue
        n = sum(1 for f in open_waiting if f["scan_id"] == sc["id"])
        unreviewed = sc["status"] == "escalated" and not sc["risk_reviewed_by"]
        reasons = []
        if n:
            reasons.append(f"{n} {'decision' if n == 1 else 'decisions'} waiting")
        if unreviewed:
            reasons.append("risk tier not yet confirmed")
        if reasons:
            attention.append({"id": sc["id"], "name": f"{sc['repo_owner']}/{sc['repo_name']}",
                              "why": ", ".join(reasons)})

    checks = []
    for rule, name in CHECKS:
        rows = [f for f in findings if f["rule_id"] == rule]
        found = len(rows)
        appr = sum(f["status"] in approved_states for f in rows)
        rej = sum(f["status"] == "rejected" for f in rows)
        wait = sum(f["status"] in waiting_states for f in rows)
        checks.append({"rule": rule, "name": name, "found": found, "approved": appr,
                       "rejected": rej, "waiting": wait,
                       "p_ok": round(100 * appr / found) if found else 0,
                       "p_rej": round(100 * rej / found) if found else 0,
                       "p_wait": 100 - round(100 * appr / found) - round(100 * rej / found) if found else 0})
    escalated = [sc for sc in scans if sc["risk_tier"] == "possibly_high"]
    risk = {"escalated": len(escalated),
            "confirmed": sum(1 for sc in escalated if sc["risk_reviewed_by"])}

    activity = []
    for r in recent:
        try:
            details = json.loads(r["details_json"])
        except ValueError:
            details = {}
        activity.append({"when": _fmt_time(r["timestamp"]),
                         "actor": {"ai": "AI", "system": "System"}.get(r["actor"], r["actor"]),
                         "action": ACTION_LABELS.get(r["action"], r["action"]),
                         "summary": _short(_summary(r["action"], details)), "scan_id": r["scan_id"]})
    prs = sum(1 for sc in scans if sc["status"] == "pr_opened")
    return {
        "stats": {"scans": len(scans), "waiting": len(open_waiting),
                  "approved": sum(f["status"] in approved_states for f in findings),
                  "delivered": prs + exported},
        "attention": attention, "checks": checks, "risk": risk, "activity": activity,
        "integrity": audit.verify(),
        "scans": [{**sc, "status_label": STATUS_LABELS.get(sc["status"], sc["status"]),
                   "when": _fmt_time(sc["created_at"]),
                   "findings": sum(1 for f in findings if f["scan_id"] == sc["id"])}
                  for sc in scans[:8]],
    }


@router.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html",
                                      {**_dashboard(), "active": "dashboard"})


@router.get("/explore")
def explore(request: Request):
    return templates.TemplateResponse(request, "explore.html", {
        "active": "explore", "offers": regulations.OFFERS, "tiers": regulations.AI_TIERS,
        "reviewed_on": regulations.REVIEWED_ON})


@router.get("/new")
def new_scan(request: Request):
    return templates.TemplateResponse(request, "new.html", {"active": "new"})


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
