import os
import sys

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "EU-Bridge"

REQUIRED_VARS = ["OPENAI_API_KEY", "GITHUB_TOKEN"]


def validate_env() -> None:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        for v in missing:
            print(f"Missing env var: {v}", file=sys.stderr)
        sys.exit(1)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
PORT = int(os.getenv("PORT", "8000"))
APP_ENV = os.getenv("APP_ENV", "production")
DATA_DIR = os.getenv("DATA_DIR", "./data")
MAX_FILES = int(os.getenv("MAX_FILES", "40"))
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", "40000"))

REQUIRE_LOGIN = os.getenv("REQUIRE_LOGIN", "false").lower() in ("1", "true", "yes")
