import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.routes import api
from app.services import archive, github, scanner
from app.services.triage import triage

FILE = "import openai\n@app.post('/chat')\ndef chat():\n    print(f'User {email} said {msg}')\n    return client.chat.completions.create()\n"
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
            confidence=0.9, file_path="server.py", evidence="@app.post",
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


def test_dashboard_data_and_page(client):
    client.post("/api/scans", json={"repo_url": "https://github.com/o/r", "questionnaire": Q})
    d = client.get("/api/dashboard").json()
    assert d["stats"]["scans"] == 1 and d["stats"]["waiting"] == 1
    assert d["scans"][0]["name"] == "o/r" and d["scans"][0]["attention"]
    assert d["integrity"]["ok"] is True and d["checks"][2]["found"] == 1
    assert "Dashboard" in client.get("/").text


from app.services.redact import redact


def test_redact_masks_common_secrets():
    text = ('key = "sk-abcdefghijklmnopqrstuvwxyz123456"\nAWS = "AKIAABCDEFGHIJKLMNOP"\n'
            'password = "hunter2hunter2"\nok = "hello"\n'
            "token = github_pat_ABCDEFGHIJKLMNOPQRSTUVWX\n")
    out, n = redact(text)
    assert n >= 4 and "sk-abc" not in out and "AKIA" not in out and "hunter2" not in out
    assert "github_pat_" not in out and 'ok = "hello"' in out


def test_secrets_are_masked_before_going_to_the_model(monkeypatch):
    import asyncio
    sent = []

    async def fake_batch(client, system, batch, context=""):
        sent.append(dict(batch))
        return scanner.ScanOutput(findings=[], risk_signals=[])

    monkeypatch.setattr(scanner, "_scan_batch", fake_batch)
    files = {"a.py": 'import openai\nKEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\n'}
    result = asyncio.run(scanner.analyse(files, {}, {"description": "x"}))
    assert "sk-abcdef" not in sent[0]["a.py"] and result["stats"]["secrets_masked"] == 1


def test_assessment_flow_needs_no_code(client):
    q = {**Q, "domain": "hiring", "ai_features": ["chat", "decisions_about_people"],
         "ai_provider": "openai", "data_types": ["contact"], "product_name": "HireBot"}
    r = client.post("/api/assessments", json=q)
    assert r.status_code == 200 and r.json()["status"] == "escalated"
    sid = r.json()["scan_id"]
    data = client.get(f"/api/scans/{sid}").json()
    rules = [f["rule_id"] for f in data["findings"]]
    assert {"AIA-50-1", "GDPR-13", "GDPR-5-1C", "AIA-RISK"} <= set(rules)
    assert any("OpenAI" in f["suggested_patch"] for f in data["findings"])
    assert client.get(f"/api/scans/{sid}/checklist").status_code == 409
    assert client.post(f"/api/scans/{sid}/pr").status_code == 409
    for f in data["findings"]:
        client.post(f"/api/findings/{f['id']}/review", json={
            "action": "approve" if f["rule_id"] != "GDPR-5-1C" else "reject",
            "reviewer": "Ayesha", "reason": "reviewed with the team"})
    md = client.get(f"/api/scans/{sid}/checklist")
    assert md.status_code == 200 and "Ayesha" in md.text and "AI assistant" in md.text
    assert "checklist_exported" in [e["action"] for e in client.get("/api/audit/export").json()]
    assert client.get("/api/audit/verify").json()["ok"] is True


def test_delete_uploaded_files(client):
    z = make_zip({"proj/server.py": FILE})
    sid = client.post("/api/scans/upload", data={"questionnaire": __import__("json").dumps(Q)},
                      files={"file": ("a.zip", z, "application/zip")}).json()["scan_id"]
    assert client.get(f"/api/scans/{sid}").json()["scan"]["has_files"] is True
    assert client.delete(f"/api/scans/{sid}/files").json()["deleted"] == 1
    assert client.get(f"/api/scans/{sid}").json()["scan"]["has_files"] is False
    fid = client.get(f"/api/scans/{sid}").json()["findings"][0]["id"]
    client.post(f"/api/findings/{fid}/review", json={"action": "approve", "reviewer": "A", "reason": "fine here"})
    assert client.get(f"/api/scans/{sid}/patch").status_code == 409
    assert "files_deleted" in [e["action"] for e in client.get("/api/audit/export").json()]


def test_multiple_ai_providers_named_in_wording(client):
    q = {**Q, "ai_features": ["chat"], "ai_providers": ["openai", "anthropic", "self_hosted"],
         "data_types": ["contact"]}
    sid = client.post("/api/assessments", json=q).json()["scan_id"]
    gdpr = next(f for f in client.get(f"/api/scans/{sid}").json()["findings"] if f["rule_id"] == "GDPR-13")
    assert "OpenAI and Anthropic" in gdpr["suggested_patch"] and "self-hosted" not in gdpr["suggested_patch"].lower()
    assert "each provider" in gdpr["explanation"]


def test_old_single_provider_field_still_works(client):
    sid = client.post("/api/assessments", json={**Q, "ai_provider": "google"}).json()["scan_id"]
    gdpr = next(f for f in client.get(f"/api/scans/{sid}").json()["findings"] if f["rule_id"] == "GDPR-13")
    assert "Google" in gdpr["suggested_patch"]


def test_self_hosted_only_needs_no_provider_notice(client):
    q = {**Q, "uses_llm": False, "ai_features": ["recommendations"], "ai_providers": ["self_hosted"]}
    sid = client.post("/api/assessments", json=q).json()["scan_id"]
    assert "GDPR-13" not in [f["rule_id"] for f in client.get(f"/api/scans/{sid}").json()["findings"]]
