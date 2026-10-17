from app.services import regulations as reg


def ids(res, level=None):
    return [r["id"] for r in res["results"] if level is None or r["level"] == level]


def test_chatbot_startup_gets_ai_act_and_gdpr_first():
    res = reg.match(["ai", "software"], "yes", "small", True)
    assert ids(res)[:2] == ["ai-act", "gdpr"]
    assert "transparency" in res["ai_tiers"]


def test_hiring_tool_is_flagged_high_risk():
    res = reg.match(["ai", "hr"], "yes", "small", True)
    assert "high" in res["ai_tiers"]
    ai = next(r for r in res["results"] if r["id"] == "ai-act")
    assert any("hiring" in w.lower() for w in ai["why"])


def test_hr_without_ai_is_only_a_check():
    res = reg.match(["hr"], "yes", "small", True)
    ai = next(r for r in res["results"] if r["id"] == "ai-act")
    assert ai["level"] == "check"


def test_nis2_depends_on_size():
    small = reg.match(["infra"], "yes", "small", False)
    large = reg.match(["infra"], "yes", "large", False)
    assert next(r for r in small["results"] if r["id"] == "nis2")["level"] == "check"
    assert next(r for r in large["results"] if r["id"] == "nis2")["level"] == "applies"


def test_eaa_micro_enterprise_is_only_a_check():
    res = reg.match(["ecommerce"], "yes", "micro", True)
    assert next(r for r in res["results"] if r["id"] == "eaa")["level"] == "check"


def test_fintech_gets_dora_and_devices_get_cra():
    assert "dora" in ids(reg.match(["fintech"], "yes", "medium", True), "applies")
    assert "cra" in ids(reg.match(["devices"], "yes", "small", False), "applies")


def test_no_eu_users_is_flagged_and_unknown_offers_ignored():
    res = reg.match(["ai", "bogus"], "no", "small", True)
    assert res["outside_eu"] is True and "ai-act" in ids(res)


def test_nothing_selected_matches_nothing():
    res = reg.match([], "planned", "small", False)
    assert res["results"] == [] and len(res["not_matched"]) == len(reg.ORDER)


def test_every_regulation_has_complete_content():
    for rid in reg.ORDER:
        r = reg.REGULATIONS[rid]
        for key in ("name", "full", "url", "summary", "asks", "dates", "penalty", "eubridge"):
            assert r[key], (rid, key)
        assert r["url"].startswith("https://eur-lex.europa.eu/eli/")


def test_match_endpoint_and_page(db):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/regulations/match", json={"offers": ["ai", "hr"], "eu_users": "yes",
                                               "size": "small", "personal_data": True})
    assert r.status_code == 200 and r.json()["results"][0]["id"] == "ai-act"
    assert c.post("/api/regulations/match", json={"size": "huge"}).status_code == 422
    page = c.get("/explore").text
    assert "Which EU rules apply" in page and "The EU AI Act at a glance" in page
    assert "not legal advice" in page


def test_static_assets_are_versioned_and_revalidated(db):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    page = c.get("/new").text
    assert "/static/new.js?v=" in page and "/static/app.css?v=" in page
    assert c.get("/static/new.js").headers["cache-control"] == "no-cache"
