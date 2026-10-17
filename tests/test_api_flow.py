"""End-to-end API flow with GitHub and OpenAI mocked."""
import pytest
from fastapi.testclient import TestClient

from app.routes import api
from app.services import github, scanner

FILE = "import openai\n@app.post('/chat')\ndef chat():\n    print(f'User {email} said {msg}')\n    return client.chat.completions.create()\n"
QUESTIONNAIRE = {"description": "CV screening bot", "uses_llm": True,
                 "processes_personal_data": True, "domain": "hiring"}


@pytest.fixture
def client(db, monkeypatch):
    from app.main import app
    api._hits.clear()
    calls = {"puts": [], "prs": []}

    async def get_repo(o, r, **kw): return {"default_branch": "main"}
    async def get_branch_sha(o, r, b, **kw): return "headsha"
    async def get_file(o, r, p, ref, **kw): return FILE, "blobsha"
    async def create_branch(o, r, n, s, **kw): calls["branch"] = n
    async def put_file(o, r, path, content, sha, branch, msg, **kw): calls["puts"].append((path, content, msg))
    async def create_pr(o, r, head, base, title, body, **kw):
        calls["prs"].append(body)
        return "https://github.com/o/r/pull/1"
    async def scan_repo(o, r, ref, **kw):
        fs = scanner.process_findings([
            scanner.RawFinding(rule_id="GDPR-5-1C", title="PII in log", explanation="e",
                               severity="high", confidence=0.9, file_path="server.py", evidence="@app.post",
                               original_snippet="print(f'User {email} said {msg}')",
                               suggested_patch="print('chat message received')"),
            scanner.RawFinding(rule_id="AIA-50-1", title="No disclosure", explanation="e",
                               severity="medium", confidence=0.9, file_path="server.py", evidence="@app.post",
                               original_snippet="NOT IN FILE", suggested_patch="x"),
        ], {"server.py": FILE})
        return {"findings": fs, "risk_signals": [], "stats": {}, "warnings": [],
                "files": {"server.py": FILE}}

    for name, fn in dict(get_repo=get_repo, get_branch_sha=get_branch_sha, get_file=get_file,
                         create_branch=create_branch, put_file=put_file,
                         create_pr=create_pr).items():
        monkeypatch.setattr(github, name, fn)
    async def scan_archive(files, questionnaire=None):
        return await scan_repo("u", "r", "x")

    monkeypatch.setattr(scanner, "scan_repo", scan_repo)
    monkeypatch.setattr(scanner, "scan_archive", scan_archive)
    c = TestClient(app)
    c.calls = calls
    return c


def test_full_flow(client):
    r = client.post("/api/scans", json={"repo_url": "https://github.com/o/r",
                                        "questionnaire": QUESTIONNAIRE})
    assert r.status_code == 200 and r.json()["status"] == "escalated"
    sid = r.json()["scan_id"]
    data = client.get(f"/api/scans/{sid}").json()
    assert data["scan"]["risk_tier"] == "possibly_high"
    pending = [f for f in data["findings"] if f["status"] == "pending"]
    needs = [f for f in data["findings"] if f["status"] == "needs_human"]
    assert len(pending) == 1 and len(needs) == 1

    # reviewer + reason are required
    bad = client.post(f"/api/findings/{pending[0]['id']}/review",
                      json={"action": "approve", "reviewer": " ", "reason": "ok fine"})
    assert bad.status_code == 422
    bad = client.post(f"/api/findings/{pending[0]['id']}/review",
                      json={"action": "approve", "reviewer": "Ayesha", "reason": "no"})
    assert bad.status_code == 422

    # PR blocked while a finding is pending
    assert client.post(f"/api/scans/{sid}/pr").status_code == 409

    ok = client.post(f"/api/findings/{pending[0]['id']}/review",
                     json={"action": "approve", "reviewer": "Ayesha", "reason": "removes PII"})
    assert ok.status_code == 200
    client.post(f"/api/findings/{needs[0]['id']}/review",
                json={"action": "reject", "reviewer": "Ayesha", "reason": "not applicable"})
    assert client.post(f"/api/scans/{sid}/risk-review",
                       json={"reviewer": "Counsel", "reason": "confirmed high risk"}).status_code == 200

    pr = client.post(f"/api/scans/{sid}/pr")
    assert pr.status_code == 200, pr.text
    assert pr.json()["applied"] == 1
    path, content, msg = client.calls["puts"][0]
    assert "chat message received" in content and "Ayesha" in msg
    body = client.calls["prs"][0]
    assert "Ayesha" in body and "Counsel" in body and "not legal advice" in body
    assert client.post(f"/api/scans/{sid}/pr").status_code == 409  # already open

    assert client.get("/api/audit/verify").json()["ok"] is True
    actions = [e["action"] for e in client.get("/api/audit/export").json()]
    for a in ("scan_started", "finding_created", "escalated", "approved", "rejected",
              "risk_reviewed", "pr_opened"):
        assert a in actions


def test_edit_and_approve_requires_patch(client):
    sid = client.post("/api/scans", json={"repo_url": "https://github.com/o/r",
                                          "questionnaire": QUESTIONNAIRE}).json()["scan_id"]
    f = client.get(f"/api/scans/{sid}").json()["findings"][0]
    r = client.post(f"/api/findings/{f['id']}/review",
                    json={"action": "edit_and_approve", "reviewer": "A", "reason": "tweaking"})
    assert r.status_code == 422


def test_rejects_non_github_url(client):
    r = client.post("/api/scans", json={"repo_url": "https://evil.com/o/r",
                                        "questionnaire": QUESTIONNAIRE})
    assert r.status_code == 400


def test_ui_pages_render(client):
    for path, needle in (("/new", "Scan a repository"), ("/", "Dashboard"), ("/audit", "Audit log"),
                         ("/scans/abc", 'data-scan-id="abc"')):
        r = client.get(path)
        assert r.status_code == 200 and needle in r.text
        assert "reviewed by a human" in r.text and "not legal advice" in r.text
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/review.js").status_code == 200


def test_audit_page_lists_entries(client):
    client.post("/api/scans", json={"repo_url": "https://github.com/o/r",
                                    "questionnaire": QUESTIONNAIRE})
    page = client.get("/audit").text
    assert "Scan started" in page and "AI suggested a fix" in page
