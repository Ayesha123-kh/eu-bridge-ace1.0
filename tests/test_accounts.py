import json

import pytest
from fastapi.testclient import TestClient

from app.routes import api
from app.services import github, scanner

FILE = "import openai\n@app.post('/chat')\ndef chat():\n    print(f'User {email} said {msg}')\n    return client.chat.completions.create()\n"
Q = {"description": "bot", "uses_llm": True, "processes_personal_data": True, "domain": "other"}


@pytest.fixture
def app_client(db, monkeypatch):
    from app.main import app
    api._hits.clear()
    api._login_hits.clear()

    async def get_repo(o, r, **kw): return {"default_branch": "main"}
    async def get_branch_sha(o, r, b, **kw): return "sha"

    async def scan_repo(o, r, ref, **kw):
        fs = scanner.process_findings([scanner.RawFinding(
            rule_id="GDPR-5-1C", title="t", explanation="e", severity="high", confidence=0.9,
            file_path="server.py", evidence="@app.post", original_snippet="print(f'User {email} said {msg}')",
            suggested_patch="print('x')")], {"server.py": FILE})
        return {"findings": fs, "risk_signals": [], "stats": {}, "warnings": [], "files": {"server.py": FILE}}

    monkeypatch.setattr(github, "get_repo", get_repo)
    monkeypatch.setattr(github, "get_branch_sha", get_branch_sha)
    monkeypatch.setattr(scanner, "scan_repo", scan_repo)
    return lambda: TestClient(app)


def scan(c):
    return c.post("/api/scans", json={"repo_url": "https://github.com/o/r", "questionnaire": Q}).json()["scan_id"]


def test_signup_login_logout_and_validation(app_client):
    c = app_client()
    assert c.get("/api/auth/me").json()["user"] is None
    assert c.post("/api/auth/signup", json={"name": "A", "email": "a@x.com", "password": "longenough"}).status_code == 400
    assert c.post("/api/auth/signup", json={"name": "Ayesha K", "email": "nope", "password": "longenough"}).status_code == 400
    assert c.post("/api/auth/signup", json={"name": "Ayesha K", "email": "a@x.com", "password": "short"}).status_code == 400
    ok = c.post("/api/auth/signup", json={"name": "Ayesha K", "email": "a@x.com", "password": "longenough"})
    assert ok.status_code == 200 and c.get("/api/auth/me").json()["user"]["name"] == "Ayesha K"
    assert c.post("/api/auth/signup", json={"name": "Other", "email": "A@X.com", "password": "longenough"}).status_code == 400
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").json()["user"] is None
    assert c.post("/api/auth/login", json={"email": "a@x.com", "password": "wrong-password"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "a@x.com", "password": "longenough"}).status_code == 200
    assert c.get("/api/auth/me").json()["user"]["email"] == "a@x.com"


def test_password_is_hashed_not_stored(app_client, db):
    c = app_client()
    c.post("/api/auth/signup", json={"name": "Ayesha K", "email": "a@x.com", "password": "my-secret-pass"})
    raw = b"".join(p.read_bytes() for p in db.iterdir() if p.is_file())
    assert b"my-secret-pass" not in raw and b"scrypt$" in raw


def test_scans_are_private_to_their_owner(app_client):
    a, b = app_client(), app_client()
    sid = scan(a)
    assert a.get(f"/api/scans/{sid}").status_code == 200
    assert b.get(f"/api/scans/{sid}").status_code == 404
    fid = a.get(f"/api/scans/{sid}").json()["findings"][0]["id"]
    assert b.post(f"/api/findings/{fid}/review", json={"action": "approve", "reviewer": "X", "reason": "not mine"}).status_code == 404
    assert b.get("/api/dashboard").json()["stats"]["scans"] == 0
    assert a.get("/api/dashboard").json()["stats"]["scans"] == 1
    assert b.get("/api/audit/export").json() == [] and len(a.get("/api/audit/export").json()) > 0
    assert "o/r" not in b.get("/audit").text and "o/r" in a.get("/audit").text


def test_guest_scans_move_into_account_on_signup(app_client):
    c = app_client()
    sid = scan(c)
    r = c.post("/api/auth/signup", json={"name": "Ayesha K", "email": "a@x.com", "password": "longenough"})
    assert r.json()["claimed_scans"] == 1
    other = app_client()  # a different device signing in sees the history
    other.post("/api/auth/login", json={"email": "a@x.com", "password": "longenough"})
    assert other.get(f"/api/scans/{sid}").status_code == 200
    assert other.get("/api/dashboard").json()["stats"]["scans"] == 1


def test_signed_in_decisions_use_the_account_name(app_client):
    c = app_client()
    c.post("/api/auth/signup", json={"name": "Ayesha K", "email": "a@x.com", "password": "longenough"})
    sid = scan(c)
    fid = c.get(f"/api/scans/{sid}").json()["findings"][0]["id"]
    c.post(f"/api/findings/{fid}/review", json={"action": "approve", "reviewer": "Someone Else", "reason": "checked it"})
    f = c.get(f"/api/scans/{sid}").json()["findings"][0]
    assert f["reviewer"] == "Ayesha K"
    actors = [e["actor"] for e in c.get("/api/audit/export").json()]
    assert "Ayesha K" in actors and "Someone Else" not in actors


def test_pages_show_account_state(app_client):
    c = app_client()
    assert "Sign in" in c.get("/").text and c.get("/signin").status_code == 200
    c.post("/api/auth/signup", json={"name": "Ayesha K", "email": "a@x.com", "password": "longenough"})
    page = c.get("/").text
    assert "Ayesha K" in page and "Sign out" in page
    assert c.get("/signin", follow_redirects=False).status_code == 303


def test_login_is_rate_limited(app_client):
    c = app_client()
    codes = [c.post("/api/auth/login", json={"email": "a@x.com", "password": "x" * 9}).status_code for _ in range(12)]
    assert 429 in codes


def test_audit_page_has_filters_and_company_names(app_client):
    c = app_client()
    scan(c)
    page = c.get("/audit").text
    assert 'id="f-scan"' in page and "o/r" in page and "Suggestion created" in page
