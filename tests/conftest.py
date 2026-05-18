from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ARTIFACTS_DIR", "./artifacts_test")
os.environ.setdefault("ALLOW_PRIVATE_TARGETS", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("BROWSER_POOL_SIZE", "0")


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def settings():
    from app.config import Settings, reset_settings_for_test

    s = Settings(allow_private_targets=True, openai_api_key="", browser_pool_size=0)
    reset_settings_for_test(s)
    yield s
    reset_settings_for_test(None)
