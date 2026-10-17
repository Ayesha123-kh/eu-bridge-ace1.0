"""Plain-language catalog of EU rules and a deterministic matcher. Not legal advice.

Dates were checked on 17 Oct 2026 against public law-firm summaries, not the Official Journal.
"""

REVIEWED_ON = "17 Oct 2026"
SIZES = ["micro", "small", "medium", "large"]  # <10, 10-49, 50-249, 250+ employees

OFFERS = {
    "ai": "An AI feature, chatbot or assistant",
    "software": "Software or SaaS",
    "ecommerce": "An online store selling to consumers",
    "platform": "A platform, marketplace or social network",
    "fintech": "Financial services or fintech",
    "health": "Health or medical software",
    "devices": "Connected devices or IoT products",
    "hr": "Hiring or HR tools",
    "education": "Education or exam tools",
    "infra": "Cloud, hosting or digital infrastructure",
    "essential": "Energy, transport, water or healthcare services",
}

HIGH_RISK_OFFERS = {
    "hr": "Hiring and worker-management AI is listed as high-risk",
    "education": "AI that scores exams or decides who gets access to education is listed as high-risk",
    "fintech": "AI for credit scoring or insurance pricing is listed as high-risk",
    "health": "AI used in healthcare or medical devices can be high-risk",
    "essential": "AI used in critical infrastructure and essential services can be high-risk",
}

REGULATIONS = {
    "ai-act": {
        "name": "EU AI Act",
        "full": "Regulation (EU) 2024/1689",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
        "summary": "Rules for AI systems that scale with the harm they could do. The riskier the use, the heavier the duties.",
        "asks": [
            "Do not build prohibited AI such as social scoring or manipulative systems (Art. 5).",
            "Tell people when they are talking to an AI or looking at AI-generated content (Art. 50).",
            "If your AI is high-risk, such as hiring or credit scoring, you need risk management, documentation, logging, human oversight and a conformity assessment.",
            "Make sure staff who work with AI understand it (AI literacy, Art. 4).",
        ],
        "dates": [
            "Prohibited practices and AI literacy: 2 Feb 2025",
            "Duties for general-purpose AI model providers: 2 Aug 2025",
            "Transparency duties (Art. 50): 2 Aug 2026",
            "High-risk systems (Annex III): moved from 2 Aug 2026 to 2 Dec 2027 by the Digital Omnibus*",
            "AI built into regulated products (Annex I): 2 Aug 2028*",
        ],
        "penalty": "Up to €35M or 7% of worldwide turnover for prohibited practices. Up to €15M or 3% for most other breaches.",
        "eubridge": "EU-Bridge checks the Art. 50 AI disclosure in your code and sends possible high-risk use to a person.",
        "footnote": "*Postponement agreed in the Digital Omnibus (final Council approval 29 June 2026, per law-firm summaries). Confirm in the Official Journal.",
    },
    "gdpr": {
        "name": "GDPR",
        "full": "Regulation (EU) 2016/679",
        "url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "summary": "The EU's data protection law. It covers any personal data of people in the EU, including data you send to an AI provider.",
        "asks": [
            "Tell people what you do with their data, including when it goes to an outside AI provider (Art. 13).",
            "Collect only what you need and keep personal data out of logs (Art. 5(1)(c), Art. 32).",
            "Sign a data processing agreement with every provider that handles the data (Art. 28).",
            "Honour access and deletion requests, and report breaches within 72 hours.",
        ],
        "dates": ["In force since 25 May 2018"],
        "penalty": "Up to €20M or 4% of worldwide turnover.",
        "eubridge": "EU-Bridge checks the third-party AI notice (Art. 13) and personal data in logs (Art. 5(1)(c)).",
    },
    "eprivacy": {
        "name": "ePrivacy Directive (cookies)",
        "full": "Directive 2002/58/EC",
        "url": "https://eur-lex.europa.eu/eli/dir/2002/58/oj",
        "summary": "Rules for cookies, trackers and electronic communications. This is the source of the cookie banner.",
        "asks": [
            "Get consent before setting non-essential cookies or trackers.",
            "Explain what each one does.",
            "Make refusing as easy as accepting.",
        ],
        "dates": ["In force. Applied through each country's national law."],
        "penalty": "Set by each member state.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "dsa": {
        "name": "Digital Services Act (DSA)",
        "full": "Regulation (EU) 2022/2065",
        "url": "https://eur-lex.europa.eu/eli/reg/2022/2065/oj",
        "summary": "Rules for online intermediaries: hosting, platforms, marketplaces and social networks.",
        "asks": [
            "Give users a way to report illegal content and act on reports.",
            "Publish clear terms and a contact point for authorities and users.",
            "Marketplaces must verify and trace the traders who sell on them.",
            "Small and micro platforms are exempt from some of the extra duties.",
        ],
        "dates": ["Fully applicable since 17 Feb 2024"],
        "penalty": "Up to 6% of worldwide turnover.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "data-act": {
        "name": "Data Act",
        "full": "Regulation (EU) 2023/2854",
        "url": "https://eur-lex.europa.eu/eli/reg/2023/2854/oj",
        "summary": "Who may use the data that connected products and cloud services generate, and how easily customers can switch cloud providers.",
        "asks": [
            "Connected products: let users access and share the data their device produces.",
            "Use fair terms when you share data with other businesses.",
            "Cloud and data processing services: make switching provider possible and drop switching charges.",
        ],
        "dates": [
            "Applies since 12 Sep 2025",
            "Design rules for connected products placed on the market from 12 Sep 2026",
            "Switching charges end 12 Jan 2027",
        ],
        "penalty": "Set by each member state.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "nis2": {
        "name": "NIS2 Directive",
        "full": "Directive (EU) 2022/2555",
        "url": "https://eur-lex.europa.eu/eli/dir/2022/2555/oj",
        "summary": "Cybersecurity duties for medium and large companies in sectors such as energy, transport, health, digital infrastructure and online marketplaces.",
        "asks": [
            "Run a cybersecurity risk management programme.",
            "Report significant incidents, with an early warning within 24 hours.",
            "Secure your supply chain and suppliers.",
            "Senior management is accountable for approving and overseeing the measures.",
        ],
        "dates": ["Member states had to turn it into national law by 17 Oct 2024. Timing varies by country."],
        "penalty": "Up to €10M or 2% of worldwide turnover for essential entities.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "cra": {
        "name": "Cyber Resilience Act (CRA)",
        "full": "Regulation (EU) 2024/2847",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
        "summary": "Security rules for products with digital elements: connected hardware and software you ship to customers.",
        "asks": [
            "Build security in and ship security updates for the product's support period.",
            "Handle vulnerabilities and keep technical documentation, including a software bill of materials.",
            "CE-mark the product once it meets the requirements.",
            "Report actively exploited vulnerabilities to the authorities.",
        ],
        "dates": ["Reporting duties from 11 Sep 2026", "Main obligations from 11 Dec 2027"],
        "penalty": "Up to €15M or 2.5% of worldwide turnover.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "dora": {
        "name": "DORA",
        "full": "Regulation (EU) 2022/2554",
        "url": "https://eur-lex.europa.eu/eli/reg/2022/2554/oj",
        "summary": "Digital resilience rules for banks, insurers, payment firms and other financial entities, and for the ICT providers they depend on.",
        "asks": [
            "Manage ICT risk with a documented framework.",
            "Report major ICT incidents to the regulator.",
            "Test your operational resilience regularly.",
            "Put required terms in contracts with ICT providers.",
        ],
        "dates": ["Applies since 17 Jan 2025"],
        "penalty": "Set by each member state and financial supervisor.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "eaa": {
        "name": "European Accessibility Act",
        "full": "Directive (EU) 2019/882",
        "url": "https://eur-lex.europa.eu/eli/dir/2019/882/oj",
        "summary": "Accessibility rules for consumer products and services such as online stores, consumer banking, e-books and ticketing.",
        "asks": [
            "Make your website and apps usable with assistive technology (the EN 301 549 standard, based on WCAG).",
            "Publish an accessibility statement.",
            "Micro-enterprises that provide services are exempt.",
        ],
        "dates": ["Applies since 28 Jun 2025"],
        "penalty": "Set by each member state.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "pld": {
        "name": "Product Liability Directive",
        "full": "Directive (EU) 2024/2853",
        "url": "https://eur-lex.europa.eu/eli/dir/2024/2853/oj",
        "summary": "Software and AI now count as products. People harmed by a defective one can claim compensation without proving fault.",
        "asks": [
            "Treat missing security updates and unsafe AI behaviour as possible defects.",
            "Keep records, because courts can order you to disclose evidence.",
        ],
        "dates": ["Applies to products placed on the market from 9 Dec 2026"],
        "penalty": "Compensation claims rather than fines.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
    "mdr": {
        "name": "Medical Device Regulation (MDR)",
        "full": "Regulation (EU) 2017/745",
        "url": "https://eur-lex.europa.eu/eli/reg/2017/745/oj",
        "summary": "Software with a medical purpose, such as diagnosis or treatment decisions, is a medical device and needs approval.",
        "asks": [
            "Decide whether your software has a medical purpose. Wellness apps usually do not.",
            "If it does: classify it, run a clinical evaluation and CE-mark it.",
            "Monitor the product after launch.",
        ],
        "dates": ["Applies since 26 May 2021"],
        "penalty": "Set by each member state.",
        "eubridge": "Not covered by EU-Bridge checks yet.",
    },
}

ORDER = ["ai-act", "gdpr", "eprivacy", "dsa", "data-act", "nis2", "cra", "dora", "eaa", "pld", "mdr"]

AI_TIERS = [
    {"id": "prohibited", "name": "Prohibited",
     "text": "Banned outright, for example social scoring, manipulative AI, untargeted scraping of face images, and emotion recognition at work or school.",
     "ref": "Art. 5"},
    {"id": "high", "name": "High-risk",
     "text": "AI used in hiring, education, credit, essential services, law enforcement and similar areas. Needs risk management, documentation, human oversight and a conformity assessment.",
     "ref": "Annex III"},
    {"id": "transparency", "name": "Transparency",
     "text": "Chatbots and AI-generated content. People must be told they are dealing with an AI or looking at generated content.",
     "ref": "Art. 50"},
    {"id": "minimal", "name": "Minimal",
     "text": "Everything else, such as spam filters. No new duties, though voluntary codes are encouraged.",
     "ref": ""},
]


def _size_at_least(size: str, minimum: str) -> bool:
    return size in SIZES and SIZES.index(size) >= SIZES.index(minimum)


def match(offers: list[str], eu_users: str = "planned", size: str = "small",
          personal_data: bool = True) -> dict:
    """Return which rules apply. Each hit has a level ('applies' or 'check') and reasons."""
    o = {x for x in offers if x in OFFERS}
    hits: dict[str, dict] = {}

    def add(rid: str, level: str, why: str) -> None:
        h = hits.setdefault(rid, {"level": level, "why": []})
        if level == "applies":
            h["level"] = "applies"
        if why not in h["why"]:
            h["why"].append(why)

    # AI Act
    if "ai" in o:
        add("ai-act", "applies", "You offer an AI feature")
    for k, why in HIGH_RISK_OFFERS.items():
        if k in o:
            add("ai-act", "applies" if "ai" in o else "check", why)
    # GDPR
    if personal_data:
        add("gdpr", "applies", "You handle personal data of people in the EU")
    elif eu_users in ("yes", "planned") and o:
        add("gdpr", "check", "Most digital products end up handling some personal data, such as emails or IP addresses")
    # ePrivacy
    for k in ("software", "ecommerce", "platform"):
        if k in o:
            add("eprivacy", "applies", "You run a website or app that can set cookies or trackers")
            break
    # DSA
    if "platform" in o:
        add("dsa", "applies", "You run a platform, marketplace or social network")
    if "infra" in o:
        add("dsa", "applies", "Hosting and infrastructure services are covered as intermediaries")
    # Data Act
    if "devices" in o:
        add("data-act", "applies", "You sell connected products")
    if "infra" in o:
        add("data-act", "applies", "You provide cloud or data processing services")
    if "software" in o:
        add("data-act", "check", "SaaS can count as a data processing service, which has to allow switching")
    # NIS2
    in_scope = o & {"infra", "essential", "platform"}
    if in_scope:
        if _size_at_least(size, "medium"):
            add("nis2", "applies", "You are a medium or large company in a covered sector")
        else:
            add("nis2", "check", "Companies under 50 people are usually out of scope, but some digital providers are covered whatever their size")
    elif "software" in o and _size_at_least(size, "medium"):
        add("nis2", "check", "IT service providers to other businesses can be covered")
    # CRA
    if "devices" in o:
        add("cra", "applies", "You sell connected hardware with software")
    if "software" in o:
        add("cra", "check", "Software you distribute, such as apps or firmware, is covered. Pure hosted SaaS mostly is not")
    # DORA
    if "fintech" in o:
        add("dora", "applies", "You are in financial services or sell to it")
    # EAA
    if "ecommerce" in o:
        add("eaa", "applies" if size != "micro" else "check", "You sell to consumers online" +
            ("" if size != "micro" else ". Micro-enterprises providing services are exempt"))
    if "fintech" in o:
        add("eaa", "applies" if size != "micro" else "check", "Consumer banking services are covered")
    if "devices" in o:
        add("eaa", "check", "Some consumer devices such as e-readers and terminals are covered")
    # Product liability
    for k, why in (("ai", "AI counts as a product"), ("devices", "Connected products are covered"),
                   ("health", "Health software is covered")):
        if k in o:
            add("pld", "applies", why)
    if "software" in o:
        add("pld", "check", "Software is now treated as a product")
    # MDR
    if "health" in o:
        add("mdr", "check", "If your software has a medical purpose, it can be a medical device")

    results = []
    for rid in ORDER:
        if rid in hits:
            results.append({"id": rid, **REGULATIONS[rid], **hits[rid]})
    results.sort(key=lambda r: r["level"] != "applies")  # stable: applies first
    not_matched = [{"id": rid, "name": REGULATIONS[rid]["name"]} for rid in ORDER if rid not in hits]

    tiers = []
    if "ai" in o or o & set(HIGH_RISK_OFFERS):
        if o & set(HIGH_RISK_OFFERS):
            tiers.append("high")
        if "ai" in o:
            tiers.append("transparency")
        if "ai" in o and not (o & set(HIGH_RISK_OFFERS)):
            tiers.append("minimal")
    return {"results": results, "not_matched": not_matched, "ai_tiers": tiers,
            "outside_eu": eu_users == "no", "reviewed_on": REVIEWED_ON}
