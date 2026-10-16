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
