import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GITHUB_TOKEN", "test-token")

import pytest

from app import config
from app.db import init_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    init_db()
    return tmp_path


VALID = dict(
    company_name="Acme Ltd", website="https://acme.example.com", industry="Customer support software",
    description="An assistant that answers customer support questions", user_groups=["consumers"],
    ai_features=["chat"], ai_providers=["openai"], data_types=["contact"],
    human_review="not_applicable", uses_llm=True, processes_personal_data=True, domain="other")
