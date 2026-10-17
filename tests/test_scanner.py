from app.services.github import parse_repo_url
from app.services.scanner import RawFinding, comment_only_change, is_candidate, process_findings, score_file
import pytest


def raw(**kw):
    base = dict(rule_id="GDPR-5-1C", title="t", explanation="e", severity="high",
                confidence=0.9, file_path="a.py", original_snippet="print(email)",
                suggested_patch="pass", evidence="print(email)")
    return RawFinding(**{**base, **kw})


def test_snippet_exactly_once_is_pending():
    out = process_findings([raw()], {"a.py": "x\nprint(email)\ny"})
    assert out[0]["status"] == "pending"


def test_missing_or_ambiguous_snippet_needs_human():
    for content, snippet in (("print(email)", "print(emails)"), ("print(email) print(email)", "print(email)")):
        out = process_findings([raw(original_snippet=snippet)], {"a.py": content})
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


def test_stray_trailing_char_is_aligned_not_flagged():
    html = '  <input id="a">\n  <input id="chat-input" placeholder="Ask...">\n  <button>x</button>\n'
    snippet = '  <input id="chat-input" placeholder="Ask..."><'
    patch = '  <input id="chat-input" placeholder="Ask..."><span>AI notice</span>'
    out = process_findings([raw(rule_id="AIA-50-1", file_path="a.html", original_snippet=snippet,
                                suggested_patch=patch, evidence='placeholder="Ask..."')],
                           {"a.html": html})
    assert out[0]["status"] == "pending"
    from app.services.patcher import apply_patch
    fixed = apply_patch(html, out[0]["original_snippet"], out[0]["suggested_patch"])
    assert 'placeholder="Ask..."><span>AI notice</span>\n  <button>' in fixed


def test_hopeless_snippet_still_needs_human():
    out = process_findings([raw(original_snippet="print(user_email_not_here)")],
                           {"a.py": "print(email)"})
    assert out[0]["status"] == "needs_human"


def test_whitespace_only_difference_is_aligned():
    out = process_findings([raw(original_snippet="    print(email)  ", suggested_patch="    pass")],
                           {"a.py": "def f():\n    print(email)\n"})
    assert out[0]["status"] == "pending" and out[0]["original_snippet"] == "print(email)"


# ---- regression tests from a real scan of a general-purpose SDK (getsentry/sentry-python)
SDK_FILE = "import logging\nlogger = logging.getLogger(__name__)\n\ndef f(e):\n    logger.warning(\"Could not convert pydantic data to JSON: %s\", e)\n"
INTEGRATIONS = 'integrations = [\n    "sentry_sdk.integrations.anthropic.AnthropicIntegration",\n]\n'


def test_library_code_gets_no_ui_findings():
    dropped = []
    out = process_findings([
        raw(rule_id="AIA-50-1", file_path="sdk/integrations.py", evidence='"sentry_sdk.integrations.anthropic',
            original_snippet='"sentry_sdk.integrations.anthropic.AnthropicIntegration",',
            suggested_patch='"sentry_sdk.integrations.anthropic.AnthropicIntegration",  # AI notice'),
        raw(rule_id="GDPR-13", file_path="sdk/integrations.py", evidence='"sentry_sdk.integrations.anthropic',
            original_snippet='"sentry_sdk.integrations.anthropic.AnthropicIntegration",',
            suggested_patch='"sentry_sdk.integrations.anthropic.AnthropicIntegration",  # notice'),
    ], {"sdk/integrations.py": INTEGRATIONS}, dropped)
    assert out == [] and len(dropped) == 2


def test_log_line_without_user_data_is_dropped():
    dropped = []
    out = process_findings([raw(file_path="sdk/utils.py", evidence="logger.warning",
                                original_snippet='logger.warning("Could not convert pydantic data to JSON: %s", e)',
                                suggested_patch='logger.warning("Could not convert pydantic data to JSON: %s", "[x]")')],
                           {"sdk/utils.py": SDK_FILE}, dropped)
    assert out == [] and "does not contain user data" in dropped[0]


def test_comment_only_fix_is_dropped():
    html = '<input id="chat-input" placeholder="Ask">\n'
    dropped = []
    out = process_findings([raw(rule_id="AIA-50-1", file_path="a.html", evidence='id="chat-input"',
                                original_snippet='<input id="chat-input" placeholder="Ask">',
                                suggested_patch='<input id="chat-input" placeholder="Ask"> <!-- AI notice -->')],
                           {"a.html": html}, dropped)
    assert out == [] and "only adds a comment" in dropped[0]
    assert comment_only_change("a.py", "x = 1", "x = 1  # note") is True
    assert comment_only_change("a.py", "x = 1", "x = 2") is False


def test_fix_calling_missing_redact_helper_is_dropped():
    code = 'def chat(req):\n    print(f"User {req.email} said: {req.message}")\n'
    dropped = []
    out = process_findings([raw(file_path="s.py", evidence="req.email", original_snippet='print(f"User {req.email} said: {req.message}")',
                                suggested_patch='print(redact(req.message))')], {"s.py": code}, dropped)
    assert out == [] and "helper that does not exist" in dropped[0]
    ok = code + "def redact(x):\n    return '[x]'\n"
    assert len(process_findings([raw(file_path="s.py", evidence="req.email", original_snippet='print(f"User {req.email} said: {req.message}")',
                                     suggested_patch='print(redact(req.message))')], {"s.py": ok})) == 1


def test_finding_without_evidence_is_dropped_and_unlocated_confidence_is_capped():
    assert process_findings([raw(evidence="this text is not in the file")], {"a.py": "print(email)"}) == []
    out = process_findings([raw(original_snippet="print(emails)", confidence=1.0)], {"a.py": "print(email)"})
    assert out[0]["status"] == "needs_human" and out[0]["confidence"] <= 0.5


def test_real_chat_app_still_gets_all_three_findings():
    server = '@app.post("/chat")\ndef chat(req):\n    print(f"User {req.email} said: {req.message}")\n    return client.chat.completions.create(model="x")\n'
    html = '<body>\n  <input id="chat-input" placeholder="Ask a question...">\n</body>\n'
    files = {"server.py": server, "static/index.html": html}
    out = process_findings([
        raw(rule_id="GDPR-5-1C", file_path="server.py", evidence="req.email", original_snippet='print(f"User {req.email} said: {req.message}")', suggested_patch='print("chat request received")'),
        raw(rule_id="AIA-50-1", file_path="static/index.html", evidence='id="chat-input"', original_snippet='<input id="chat-input" placeholder="Ask a question...">', suggested_patch='<input id="chat-input" placeholder="Ask a question..."><span>AI notice</span>'),
        raw(rule_id="GDPR-13", file_path="static/index.html", evidence='id="chat-input"', original_snippet='<input id="chat-input" placeholder="Ask a question...">', suggested_patch='<input id="chat-input" placeholder="Ask a question..."><span>Sent to OpenAI</span>'),
    ], files)
    assert [f["status"] for f in out] == ["pending"] * 3


def test_tests_and_docs_are_not_scanned():
    for path in ("tests/test_x.py", "pkg/test_chat.py", "src/chat.test.js", "docs/example.py", "conftest.py"):
        assert not is_candidate(path), path
    assert is_candidate("app/chat.py") and is_candidate("src/Chat.jsx")


def test_risk_signal_needs_evidence_in_the_code():
    from app.services.scanner import evidence_found
    files = {"a.py": "def score_candidates(cvs):\n    return rank(cvs)\n"}
    assert evidence_found("def score_candidates(cvs)", files, 12)
    assert not evidence_found("credit scoring", files, 12)
