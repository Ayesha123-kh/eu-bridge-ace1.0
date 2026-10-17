import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.routes import api
from app.services import archive, github, scanner
from app.services.triage import triage

FILE = "import openai\nprint(f'User {email} said {msg}')\n"
Q = {"description": "CV screening bot", "uses_llm": True, "processes_personal_data": True,
     "domain": "other"}


def make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def client(db, monkeypatch):
    from app.main import app
    api._hits.clear()
    seen = {"tokens": []}

    async def get_repo(o, r, token=None):
        seen["tokens"].append(token)
        return {"default_branch": "main"}

    async def get_branch_sha(o, r, b, token=None): return "sha"
    async def get_file(o, r, p, ref, token=None): seen["tokens"].append(token); return FILE, "blob"
    async def create_branch(o, r, n, s, token=None): pass
    async def put_file(o, r, path, content, sha, branch, msg, token=None): seen["tokens"].append(token)
    async def create_pr(o, r, h, b, t, body, token=None): return "https://github.com/o/r/pull/9"

    async def scan_repo(o, r, ref, token=None, questionnaire=None):
        seen["tokens"].append(token)
        return await fake_analysis()

    async def scan_archive(files, questionnaire=None):
        return await fake_analysis(files)

    async def fake_analysis(files=None):
        files = files or {"server.py": FILE}
        fs = scanner.process_findings([scanner.RawFinding(
            rule_id="GDPR-5-1C", title="PII in log", explanation="e", severity="high",
            confidence=0.9, file_path="server.py",
            original_snippet="print(f'User {email} said {msg}')",
            suggested_patch="print('chat message received')")], files)
        return {"findings": fs, "risk_signals": [], "stats": {}, "warnings": [],
                "files": {"server.py": files.get("server.py", FILE)}}

    for name, fn in dict(get_repo=get_repo, get_branch_sha=get_branch_sha, get_file=get_file,
                         create_branch=create_branch, put_file=put_file,
                         create_pr=create_pr).items():
        monkeypatch.setattr(github, name, fn)
    monkeypatch.setattr(scanner, "scan_repo", scan_repo)
    monkeypatch.setattr(scanner, "scan_archive", scan_archive)
    c = TestClient(app)
    c.seen = seen
    return c


def test_private_scan_requires_token(client):
    r = client.post("/api/scans", json={"source": "private_token",
                                        "repo_url": "https://github.com/o/r", "questionnaire": Q})
    assert r.status_code == 422


def test_private_token_is_used_but_never_stored(client, db):
    token = "github_pat_SECRET123"
    r = client.post("/api/scans", json={"source": "private_token", "access_token": token,
                                        "repo_url": "https://github.com/o/r", "questionnaire": Q})
    assert r.status_code == 200
    sid = r.json()["scan_id"]
    assert token in client.seen["tokens"]
    # PR needs a token again for private scans
    fid = client.get(f"/api/scans/{sid}").json()["findings"][0]["id"]
    client.post(f"/api/findings/{fid}/review",
                json={"action": "approve", "reviewer": "A", "reason": "looks right"})
    assert client.post(f"/api/scans/{sid}/pr").status_code == 422
    assert client.post(f"/api/scans/{sid}/pr", json={"access_token": token}).status_code == 200
    # token appears nowhere in the database file
    raw = b"".join(p.read_bytes() for p in db.iterdir() if p.is_file())
    assert token.encode() not in raw


def test_zip_scan_review_and_download(client):
    z = make_zip({"proj/server.py": FILE, "proj/README.md": "x"})
    r = client.post("/api/scans/upload", data={"questionnaire": __import__("json").dumps(Q)},
                    files={"file": ("my-app.zip", z, "application/zip")})
    assert r.status_code == 200, r.text
    sid = r.json()["scan_id"]
    data = client.get(f"/api/scans/{sid}").json()
    assert data["scan"]["source"] == "private_zip" and data["scan"]["repo_name"] == "my-app"
    fid = data["findings"][0]["id"]
    assert client.get(f"/api/scans/{sid}/patch").status_code == 409  # still pending
    assert client.post(f"/api/scans/{sid}/pr").status_code == 409     # PRs not for ZIP scans
    client.post(f"/api/findings/{fid}/review",
                json={"action": "approve", "reviewer": "Ayesha", "reason": "removes PII"})
    out = client.get(f"/api/scans/{sid}/patch")
    assert out.status_code == 200 and out.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(out.content))
    assert "chat message received" in zf.read("fixed/server.py").decode()
    assert b"chat message received" in zf.read("eu-bridge-fixes.patch")
    assert b"Ayesha" in zf.read("APPROVALS.md")
    assert "patch_exported" in [e["action"] for e in client.get("/api/audit/export").json()]
    assert client.get("/api/audit/verify").json()["ok"] is True


def test_upload_rejects_bad_files(client):
    for data, name in ((b"not a zip", "a.zip"), (make_zip({"notes.txt": "hi"}), "b.zip")):
        r = client.post("/api/scans/upload", data={"questionnaire": __import__("json").dumps(Q)},
                        files={"file": (name, data, "application/zip")})
        assert r.status_code == 400


def test_zip_slip_is_rejected():
    with pytest.raises(archive.ArchiveError, match="unsafe"):
        archive.read_zip(make_zip({"../evil.py": "x"}))


def test_archive_strips_wrapper_and_skips_junk():
    files = archive.read_zip(make_zip({
        "repo-main/app/server.py": "a", "repo-main/node_modules/x/i.js": "b",
        "repo-main/static/app.min.js": "c", "repo-main/README.md": "d"}))
    assert list(files) == ["app/server.py"]


def test_triage_new_triggers():
    assert triage({"domain": "other", "ai_features": ["biometric_emotion"]}, [])["status"] == "escalated"
    r = triage({"domain": "other", "ai_features": ["decisions_about_people"],
                "human_review": "never"}, [])
    assert r["status"] == "escalated" and "Article 14" in r["escalation_reason"]
    assert triage({"domain": "other", "ai_features": ["chat"], "uses_llm": True}, [])["risk_tier"] == "limited"


def test_dashboard_shows_counts(client):
    client.post("/api/scans", json={"repo_url": "https://github.com/o/r", "questionnaire": Q})
    page = client.get("/").text
    assert "Decisions waiting" in page and "Findings by check" in page and "o/r" in page
    assert "Audit log intact" in page
