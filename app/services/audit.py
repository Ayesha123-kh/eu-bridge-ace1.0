"""Tamper-evident (hash-chained) audit log."""
import hashlib
import json
from datetime import datetime, timezone

from app.db import connect

GENESIS = "0" * 64


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(entry)).encode()).hexdigest()


def _entry_from_row(row) -> dict:
    return {
        "timestamp": row["timestamp"],
        "actor": row["actor"],
        "action": row["action"],
        "scan_id": row["scan_id"],
        "finding_id": row["finding_id"],
        "details_json": row["details_json"],
    }


def log(actor: str, action: str, scan_id: str | None, finding_id: str | None = None,
        details: dict | None = None) -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "scan_id": scan_id,
        "finding_id": finding_id,
        "details_json": canonical_json(details or {}),
    }
    conn = connect()
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        h = compute_hash(prev, entry)
        cur = conn.execute(
            "INSERT INTO audit_log (timestamp, actor, action, scan_id, finding_id,"
            " details_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?)",
            (*entry.values(), prev, h),
        )
        conn.execute("COMMIT")
        return {"seq": cur.lastrowid, **entry, "prev_hash": prev, "hash": h}
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def verify() -> dict:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
    finally:
        conn.close()
    prev = GENESIS
    for row in rows:
        if row["prev_hash"] != prev or compute_hash(prev, _entry_from_row(row)) != row["hash"]:
            return {"ok": False, "broken_at": row["seq"], "entries": len(rows)}
        prev = row["hash"]
    return {"ok": True, "broken_at": None, "entries": len(rows)}


def export() -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY seq")]
    finally:
        conn.close()
