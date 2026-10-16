from app.services.triage import triage


def q(domain="other", llm=True):
    return {"domain": domain, "uses_llm": llm}


def test_hiring_domain_escalates():
    r = triage(q("hiring"), [])
    assert r["status"] == "escalated" and r["risk_tier"] == "possibly_high"
    assert "Annex III" in r["escalation_reason"]


def test_scanner_signal_escalates_even_if_domain_other():
    r = triage(q("other"), ["credit"])
    assert r["status"] == "escalated" and "credit" in r["escalation_reason"]


def test_llm_product_is_limited():
    r = triage(q("other", True), [])
    assert (r["risk_tier"], r["status"]) == ("limited", "ready_for_review")


def test_no_llm_is_minimal():
    assert triage(q("other", False), [])["risk_tier"] == "minimal"
