import os
import sqlite3

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    default_branch TEXT,
    commit_sha TEXT,
    questionnaire_json TEXT NOT NULL,
    risk_tier TEXT,
    status TEXT NOT NULL,
    escalation_reason TEXT,
    pr_url TEXT,
    error TEXT,
    scan_notes_json TEXT,
    risk_reviewed_by TEXT,
    risk_reviewed_reason TEXT,
    risk_reviewed_at TEXT,
    source TEXT NOT NULL DEFAULT 'public',
    source_name TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    title TEXT NOT NULL,
    explanation TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    file_path TEXT NOT NULL,
    original_snippet TEXT NOT NULL,
    suggested_patch TEXT NOT NULL,
    final_patch TEXT,
    status TEXT NOT NULL,
    needs_human_reason TEXT,
    reviewer TEXT,
    review_reason TEXT,
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS scan_files (
    scan_id TEXT NOT NULL,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (scan_id, path)
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    scan_id TEXT,
    finding_id TEXT,
    details_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(os.path.join(config.DATA_DIR, "eubridge.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(scans)")}
        for name, ddl in (("source", "TEXT NOT NULL DEFAULT 'public'"), ("source_name", "TEXT")):
            if name not in cols:
                conn.execute(f"ALTER TABLE scans ADD COLUMN {name} {ddl}")
        conn.commit()
    finally:
        conn.close()
