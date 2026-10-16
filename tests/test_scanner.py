from app.services.github import parse_repo_url
from app.services.scanner import RawFinding, is_candidate, process_findings, score_file
import pytest


def raw(**kw):
    base = dict(rule_id="GDPR-5-1C", title="t", explanation="e", severity="high",
                confidence=0.9, file_path="a.py", original_snippet="print(email)",
                suggested_patch="pass")
    return RawFinding(**{**base, **kw})


def test_snippet_exactly_once_is_pending():
    out = process_findings([raw()], {"a.py": "x\nprint(email)\ny"})
    assert out[0]["status"] == "pending"


def test_missing_or_ambiguous_snippet_needs_human():
    for content in ("nothing", "print(email) print(email)"):
        out = process_findings([raw()], {"a.py": content})
        assert out[0]["status"] == "needs_human"
        assert "could not be located" in out[0]["needs_human_reason"]


def test_low_confidence_needs_human():
    out = process_findings([raw(confidence=0.3)], {"a.py": "print(email)"})
    assert out[0]["status"] == "needs_human"


def test_invented_file_is_dropped():
    assert process_findings([raw(file_path="ghost.py")], {"a.py": "print(email)"}) == []


def test_candidate_filter():
    assert is_candidate("src/Chat.jsx") and is_candidate("server.py")
    assert not is_candidate("node_modules/x/index.js")
    assert not is_candidate("static/app.min.js")
    assert not is_candidate("README.md")


def test_score_requires_content_signal():
    assert score_file("util.py", "x = 1") == 0
    assert score_file("server.py", "import openai") > 0
    assert score_file("s.py", 'print(f"User {email} said")') > 0


def test_repo_url_parsing():
    assert parse_repo_url("https://github.com/o/r") == ("o", "r")
    assert parse_repo_url("https://github.com/o/r.git/") == ("o", "r")
    for bad in ("http://github.com/o/r", "https://evil.com/o/r", "https://github.com/o"):
        with pytest.raises(ValueError):
            parse_repo_url(bad)
