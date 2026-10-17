"""Deterministic risk-tier triage. The AI never sets the tier when escalation triggers."""

HIGH_RISK_DOMAINS = {"hiring", "credit", "education", "health", "biometrics",
                     "critical_infrastructure"}

ANNEX_III_NOTE = (
    "Annex III high-risk obligations (risk management, human oversight, documentation, "
    "conformity assessment) may apply."
)

OVERSIGHT_NOTE = {
    "never": " No one reviews the AI's output before it affects people, which Article 14 expects.",
    "sometimes": " AI output is only sometimes reviewed by a person, which Article 14 expects consistently.",
}


def triage(questionnaire: dict, risk_signals: list[str]) -> dict:
    """Returns {risk_tier, status, escalation_reason}. status is 'escalated' or 'ready_for_review'."""
    domain = questionnaire.get("domain")
    features = set(questionnaire.get("ai_features") or [])
    triggers = []
    if domain in HIGH_RISK_DOMAINS:
        triggers.append(f"questionnaire domain is '{domain.replace('_', ' ')}'")
    if "biometric_emotion" in features:
        triggers.append("the product uses biometric or emotion recognition")
    if "decisions_about_people" in features:
        triggers.append("AI is used to make or support decisions about people")
    for sig in risk_signals:
        if sig in HIGH_RISK_DOMAINS and sig != domain:
            triggers.append(f"code signal '{sig.replace('_', ' ')}' detected by the scanner")
    if triggers:
        joined = "; ".join(triggers)
        reason = joined[0].upper() + joined[1:] + ". " + ANNEX_III_NOTE
        reason += OVERSIGHT_NOTE.get(questionnaire.get("human_review"), "")
        return {"risk_tier": "possibly_high", "status": "escalated", "escalation_reason": reason}
    tier = "limited" if questionnaire.get("uses_llm") else "minimal"
    return {"risk_tier": tier, "status": "ready_for_review", "escalation_reason": None}
