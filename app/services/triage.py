"""Deterministic risk-tier triage. The AI never sets the tier when escalation triggers."""

HIGH_RISK_DOMAINS = {"hiring", "credit", "education", "health", "biometrics",
                     "critical_infrastructure"}

ANNEX_III_NOTE = (
    "Annex III high-risk obligations (risk management, human oversight, documentation, "
    "conformity assessment) may apply."
)


def triage(questionnaire: dict, risk_signals: list[str]) -> dict:
    """Returns {risk_tier, status, escalation_reason}. status is 'escalated' or 'ready_for_review'."""
    domain = questionnaire.get("domain")
    triggers = []
    if domain in HIGH_RISK_DOMAINS:
        triggers.append(f"questionnaire domain is '{domain}'")
    for sig in risk_signals:
        if sig in HIGH_RISK_DOMAINS and sig != domain:
            triggers.append(f"code signal '{sig}' detected by the scanner")
    if triggers:
        return {
            "risk_tier": "possibly_high",
            "status": "escalated",
            "escalation_reason": "; ".join(triggers).capitalize() + ". " + ANNEX_III_NOTE,
        }
    tier = "limited" if questionnaire.get("uses_llm") else "minimal"
    return {"risk_tier": tier, "status": "ready_for_review", "escalation_reason": None}
