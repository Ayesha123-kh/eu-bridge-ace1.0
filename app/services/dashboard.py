"""Everything the dashboard needs for one owner, as plain data."""
import json
from datetime import datetime

from app.db import connect
from app.services import audit

RULES = [("AIA-50-1", "AI disclosure"), ("GDPR-13", "Third-party AI notice"),
         ("GDPR-5-1C", "Personal data in logs")]
OPEN = ("ready_for_review", "escalated")
WAITING = ("pending", "needs_human")
APPROVED = ("approved", "applied", "apply_failed")

STATUS_LABELS = {
    "scanning": "Scanning", "ready_for_review": "Ready for review",
    "escalated": "Escalated: risk review needed", "pr_opened": "Pull request opened",
    "failed": "Scan failed",
}
ACTION_LABELS = {
    "scan_started": "Scan started", "finding_created": "Suggestion created",
    "escalated": "Scan escalated", "approved": "Fix approved",
    "edited_and_approved": "Fix edited and approved", "rejected": "Fix rejected",
    "risk_reviewed": "Risk tier reviewed", "pr_opened": "Pull request opened",
    "pr_failed": "Pull request failed", "patch_exported": "Fixes downloaded",
    "checklist_exported": "Checklist downloaded", "files_deleted": "Uploaded files deleted",
}


def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return iso


def short(text: str, n: int = 110) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def summary(action: str, details: dict) -> str:
    if action == "scan_started":
        return details.get("repo", "")
    if action == "finding_created":
        return f"{details.get('rule_id', '')} in {details.get('file_path', details.get('source', ''))}"
    if action in ("approved", "edited_and_approved", "rejected"):
        return f"{details.get('rule_id', '')}: {details.get('reason', '')}"
    if action in ("risk_reviewed", "escalated"):
        return details.get("reason", "")
    if action == "pr_opened":
        return details.get("pr_url", "")
    if action == "pr_failed":
        return details.get("error", "")
    return ""


def display_name(scan: dict) -> str:
    return scan["repo_name"] if scan["source"] == "assessment" else f"{scan['repo_owner']}/{scan['repo_name']}"


def build(owner: str) -> dict:
    conn = connect()
    try:
        scans = [dict(r) for r in conn.execute(
            "SELECT * FROM scans WHERE owner = ? ORDER BY created_at DESC", (owner,))]
        ids = [s["id"] for s in scans]
        marks = ",".join("?" * len(ids)) or "''"
        findings = [dict(r) for r in conn.execute(
            f"SELECT scan_id, rule_id, status FROM findings WHERE scan_id IN ({marks})", ids)]
        recent = conn.execute(
            f"SELECT * FROM audit_log WHERE scan_id IN ({marks}) ORDER BY seq DESC LIMIT 8", ids).fetchall()
        delivered_ids = {r["scan_id"] for r in conn.execute(
            f"SELECT DISTINCT scan_id FROM audit_log WHERE scan_id IN ({marks}) "
            "AND action IN ('patch_exported','checklist_exported')", ids)}
    finally:
        conn.close()

    by_scan: dict[str, list[dict]] = {}
    for f in findings:
        by_scan.setdefault(f["scan_id"], []).append(f)

    items = []
    for sc in scans:
        fs = by_scan.get(sc["id"], [])
        per_rule = {}
        for rule in [r for r, _ in RULES] + ["AIA-RISK"]:
            rs = [f for f in fs if f["rule_id"] == rule]
            per_rule[rule] = {"found": len(rs),
                              "approved": sum(f["status"] in APPROVED for f in rs),
                              "rejected": sum(f["status"] == "rejected" for f in rs),
                              "waiting": sum(f["status"] in WAITING for f in rs)}
        waiting = sum(f["status"] in WAITING for f in fs) if sc["status"] in OPEN else 0
        unreviewed = sc["status"] == "escalated" and not sc["risk_reviewed_by"]
        why = []
        if waiting:
            why.append(f"{waiting} {'decision' if waiting == 1 else 'decisions'} waiting")
        if unreviewed:
            why.append("risk tier not yet confirmed")
        items.append({
            "id": sc["id"], "name": display_name(sc), "company": sc["repo_name"] if sc["source"] == "assessment" else display_name(sc),
            "source": sc["source"], "status": sc["status"],
            "status_label": STATUS_LABELS.get(sc["status"], sc["status"]),
            "risk_tier": sc["risk_tier"], "escalated": sc["risk_tier"] == "possibly_high",
            "risk_reviewed": bool(sc["risk_reviewed_by"]), "escalation_reason": sc["escalation_reason"],
            "created_at": sc["created_at"], "when": fmt_time(sc["created_at"]),
            "total": len(fs), "waiting": waiting,
            "approved": sum(f["status"] in APPROVED for f in fs),
            "rejected": sum(f["status"] == "rejected" for f in fs),
            "delivered": sc["status"] == "pr_opened" or sc["id"] in delivered_ids,
            "attention": "; ".join(why), "per_rule": per_rule,
        })

    checks = []
    for rule, name in RULES:
        rs = [f for f in findings if f["rule_id"] == rule]
        checks.append({"rule": rule, "name": name, "found": len(rs),
                       "approved": sum(f["status"] in APPROVED for f in rs),
                       "rejected": sum(f["status"] == "rejected" for f in rs),
                       "waiting": sum(f["status"] in WAITING for f in rs)})
    esc = [i for i in items if i["escalated"]]

    activity = []
    for r in recent:
        try:
            details = json.loads(r["details_json"])
        except ValueError:
            details = {}
        activity.append({"when": fmt_time(r["timestamp"]),
                         "actor": {"ai": "AI", "system": "System"}.get(r["actor"], r["actor"]),
                         "action": ACTION_LABELS.get(r["action"], r["action"]),
                         "summary": short(summary(r["action"], details)), "scan_id": r["scan_id"]})
    return {
        "stats": {"scans": len(items), "waiting": sum(i["waiting"] for i in items),
                  "approved": sum(i["approved"] for i in items),
                  "delivered": sum(i["delivered"] for i in items)},
        "scans": items, "checks": checks,
        "risk": {"escalated": len(esc), "confirmed": sum(i["risk_reviewed"] for i in esc)},
        "activity": activity, "integrity": audit.verify(),
    }
