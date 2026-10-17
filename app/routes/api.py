import json
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.db import connect
from app.models import ReviewRequest, RiskReviewRequest, ScanRequest
from app.services import audit, github, patcher, scanner, triage

router = APIRouter(prefix="/api")

RATE_LIMIT = 10  # scans per minute per client
_hits: dict[str, deque] = defaultdict(deque)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    q = _hits[ip]
    cutoff = time.monotonic() - 60
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Too many scans. Please wait a minute and try again.")
    q.append(time.monotonic())


def _one(conn, sql, *args):
    row = conn.execute(sql, args).fetchone()
    return dict(row) if row else None


def _update(conn, table: str, id_: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE {table} SET {cols} WHERE id=?", (*fields.values(), id_))
    conn.commit()


def _scan_payload(conn, scan_id: str) -> dict:
    scan = _one(conn, "SELECT * FROM scans WHERE id=?", scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    scan["questionnaire"] = json.loads(scan.pop("questionnaire_json"))
    scan["notes"] = json.loads(scan.pop("scan_notes_json") or "{}")
    findings = [dict(r) for r in conn.execute(
        "SELECT * FROM findings WHERE scan_id=? ORDER BY rowid", (scan_id,))]
    counts = {"suggested": len(findings)}
    for key, statuses in (("approved", ("approved", "applied", "apply_failed")),
                          ("rejected", ("rejected",)), ("pending", ("pending",)),
                          ("needs_human", ("needs_human",))):
        counts[key] = sum(f["status"] in statuses for f in findings)
    counts["edited"] = sum(bool(f["final_patch"]) and f["status"] in
                           ("approved", "applied", "apply_failed") for f in findings)
    return {"scan": scan, "findings": findings, "counts": counts}


@router.post("/scans")
async def create_scan(body: ScanRequest, request: Request):
    _rate_limit(request)
    try:
        owner, repo = github.parse_repo_url(body.repo_url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    q = body.questionnaire.model_dump()
    scan_id = str(uuid.uuid4())
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO scans (id, repo_owner, repo_name, questionnaire_json, status, created_at)"
            " VALUES (?,?,?,?,?,?)", (scan_id, owner, repo, json.dumps(q), "scanning", _now()))
        conn.commit()
        audit.log("system", "scan_started", scan_id, details={"repo": f"{owner}/{repo}"})
        try:
            info = await github.get_repo(owner, repo)
            branch = info["default_branch"]
            sha = await github.get_branch_sha(owner, repo, branch)
            _update(conn, "scans", scan_id, default_branch=branch, commit_sha=sha)
            result = await scanner.scan_repo(owner, repo, sha)
        except (github.GitHubError, scanner.ScanError) as e:
            _update(conn, "scans", scan_id, status="failed", error=str(e))
            return JSONResponse({"scan_id": scan_id, "status": "failed", "error": str(e)},
                                status_code=502)
        for f in result["findings"]:
            fid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO findings (id, scan_id, rule_id, title, explanation, severity,"
                " confidence, file_path, original_snippet, suggested_patch, status,"
                " needs_human_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, scan_id, f["rule_id"], f["title"], f["explanation"], f["severity"],
                 f["confidence"], f["file_path"], f["original_snippet"], f["suggested_patch"],
                 f["status"], f["needs_human_reason"]))
            conn.commit()
            audit.log("ai", "finding_created", scan_id, fid, {
                "rule_id": f["rule_id"], "severity": f["severity"],
                "confidence": f["confidence"], "file_path": f["file_path"],
                "status": f["status"]})
        t = triage.triage(q, result["risk_signals"])
        notes = {**result["stats"], "warnings": result["warnings"],
                 "risk_signals": result["risk_signals"]}
        _update(conn, "scans", scan_id, risk_tier=t["risk_tier"], status=t["status"],
                escalation_reason=t["escalation_reason"], scan_notes_json=json.dumps(notes))
        if t["status"] == "escalated":
            audit.log("system", "escalated", scan_id, details={
                "risk_tier": t["risk_tier"], "reason": t["escalation_reason"]})
        return {"scan_id": scan_id, "status": t["status"], "risk_tier": t["risk_tier"],
                "findings": len(result["findings"])}
    finally:
        conn.close()


@router.get("/scans/{scan_id}")
def get_scan(scan_id: str):
    conn = connect()
    try:
        return _scan_payload(conn, scan_id)
    finally:
        conn.close()


@router.post("/findings/{finding_id}/review")
def review_finding(finding_id: str, body: ReviewRequest):
    conn = connect()
    try:
        f = _one(conn, "SELECT * FROM findings WHERE id=?", finding_id)
        if not f:
            raise HTTPException(404, "Finding not found")
        scan = _one(conn, "SELECT * FROM scans WHERE id=?", f["scan_id"])
        if scan["status"] in ("pr_opened", "scanning", "failed") or f["status"] == "applied":
            raise HTTPException(409, "This scan is no longer open for review.")
        if body.action == "edit_and_approve" and not (body.final_patch or "").strip():
            raise HTTPException(422, "edit_and_approve requires a non-empty final_patch.")
        if body.action != "reject" and scanner.SNIPPET_MISS in (f["needs_human_reason"] or ""):
            raise HTTPException(409, "This fix can't be applied automatically because the AI's "
                                     "snippet doesn't match the file. Reject it and fix it by hand.")
        status = "rejected" if body.action == "reject" else "approved"
        final_patch = body.final_patch if body.action == "edit_and_approve" else None
        before = f["status"]
        _update(conn, "findings", finding_id, status=status, final_patch=final_patch,
                reviewer=body.reviewer, review_reason=body.reason, reviewed_at=_now())
        action = {"approve": "approved", "edit_and_approve": "edited_and_approved",
                  "reject": "rejected"}[body.action]
        audit.log(body.reviewer, action, f["scan_id"], finding_id, {
            "rule_id": f["rule_id"], "reason": body.reason, "status_before": before})
        return {"finding_id": finding_id, "status": status}
    finally:
        conn.close()


@router.post("/scans/{scan_id}/risk-review")
def risk_review(scan_id: str, body: RiskReviewRequest):
    conn = connect()
    try:
        scan = _one(conn, "SELECT * FROM scans WHERE id=?", scan_id)
        if not scan:
            raise HTTPException(404, "Scan not found")
        if scan["status"] != "escalated":
            raise HTTPException(409, "This scan is not escalated.")
        _update(conn, "scans", scan_id, risk_reviewed_by=body.reviewer,
                risk_reviewed_reason=body.reason, risk_reviewed_at=_now())
        audit.log(body.reviewer, "risk_reviewed", scan_id,
                  details={"risk_tier": scan["risk_tier"], "reason": body.reason})
        return {"scan_id": scan_id, "risk_reviewed_by": body.reviewer}
    finally:
        conn.close()


@router.post("/scans/{scan_id}/pr")
async def create_pr(scan_id: str):
    conn = connect()
    try:
        payload = _scan_payload(conn, scan_id)
        scan, findings = payload["scan"], payload["findings"]
        if scan["status"] == "pr_opened":
            raise HTTPException(409, f"A pull request is already open: {scan['pr_url']}")
        if scan["status"] not in ("ready_for_review", "escalated"):
            raise HTTPException(409, "This scan is not ready for a pull request.")
        if scan["status"] == "escalated" and not scan.get("risk_reviewed_by"):
            raise HTTPException(409, "This scan is escalated. A person must confirm the risk "
                                     "tier before a pull request can be opened.")
        if any(f["status"] == "pending" for f in findings):
            raise HTTPException(409, "Review every pending finding before creating the PR.")
        approved = [f for f in findings if f["status"] == "approved"]
        if not approved:
            raise HTTPException(409, "Approve at least one finding first.")
        rejected = [f for f in findings if f["status"] == "rejected"]
        owner, repo, base = scan["repo_owner"], scan["repo_name"], scan["default_branch"]

        try:
            by_file: dict[str, list[dict]] = defaultdict(list)
            for f in approved:
                by_file[f["file_path"]].append(f)
            changed: dict[str, tuple[str, str, list[dict]]] = {}
            failed, applied = [], []
            for path, fs in by_file.items():
                content, blob_sha = await github.get_file(owner, repo, path, base)
                new_content, results = patcher.apply_findings(content, fs)
                ok = [f for f in fs if results[f["id"]] is None]
                for f in fs:
                    if results[f["id"]] is not None:
                        failed.append({**f, "error": results[f["id"]]})
                if ok and new_content != content:
                    changed[path] = (new_content, blob_sha, ok)
                    applied.extend(ok)
            for f in failed:
                _update(conn, "findings", f["id"], status="apply_failed")
            if not changed:
                msg = "None of the approved patches could be applied: " + "; ".join(
                    f"{f['file_path']}: {f['error']}" for f in failed)
                audit.log("system", "pr_failed", scan_id, details={"error": msg})
                return JSONResponse({"error": msg, "failed": [f["id"] for f in failed]},
                                    status_code=422)

            head_sha = await github.get_branch_sha(owner, repo, base)
            branch = f"eu-bridge/scan-{scan_id[:8]}"
            try:
                await github.create_branch(owner, repo, branch, head_sha)
            except github.GitHubError as e:
                if e.status != 422:
                    raise
                branch = f"{branch}-{uuid.uuid4().hex[:4]}"
                await github.create_branch(owner, repo, branch, head_sha)
            for path, (new_content, blob_sha, ok) in changed.items():
                rules = ", ".join(sorted({f["rule_id"] for f in ok}))
                who = ", ".join(sorted({f["reviewer"] for f in ok}))
                await github.put_file(owner, repo, path, new_content, blob_sha, branch,
                                      f"EU-Bridge: {rules} fix in {path} (approved by {who})")
            body = patcher.build_pr_body(scan, applied, failed, rejected)
            pr_url = await github.create_pr(
                owner, repo, branch, base,
                "EU-Bridge: EU compliance fixes (human-approved)", body)
        except github.GitHubError as e:
            audit.log("system", "pr_failed", scan_id, details={"error": str(e)})
            return JSONResponse({"error": str(e)}, status_code=502)

        for f in applied:
            _update(conn, "findings", f["id"], status="applied")
        _update(conn, "scans", scan_id, status="pr_opened", pr_url=pr_url)
        audit.log("system", "pr_opened", scan_id, details={
            "pr_url": pr_url, "branch": branch,
            "applied": [f["id"] for f in applied], "failed": [f["id"] for f in failed]})
        return {"pr_url": pr_url, "applied": len(applied), "failed": len(failed)}
    finally:
        conn.close()


@router.get("/audit/verify")
def audit_verify():
    return audit.verify()


@router.get("/audit/export")
def audit_export():
    return JSONResponse(audit.export(), headers={
        "Content-Disposition": 'attachment; filename="eu-bridge-audit-log.json"'})
