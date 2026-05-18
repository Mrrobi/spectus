from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: str = Field(default="")
    openai_model_intent: str = "gpt-4o-mini"
    openai_model_plan: str = "gpt-4.1"
    openai_model_repair: str = "gpt-4.1"

    db_url: str = "sqlite+aiosqlite:///./spectus.db"
    artifacts_dir: Path = Path("./artifacts")
    metrics_path: Path = Path("./metrics.json")

    user_agent: str = "Mozilla/5.0 (compatible; spectus/0.1; +https://example.invalid/bot)"
    browser_pool_size: int = 3
    browser_headless: bool = True
    browser_recycle_uses: int = 50
    browser_recycle_seconds: int = 1800

    rate_limit_rps: float = 1.0
    rate_limit_burst: float = 1.0
    allow_private_targets: bool = False

    robots_cache_ttl_sec: int = 3600
    http_timeout_sec: float = 10.0
    http_connect_timeout_sec: float = 2.0

    job_deadline_sec: float = 60.0
    llm_intent_timeout_sec: float = 12.0
    llm_planner_timeout_sec: float = 20.0
    llm_repair_timeout_sec: float = 20.0

    max_records_hard_cap: int = 1000
    max_html_bytes: int = 5 * 1024 * 1024

    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_for_test(new: Settings | None = None) -> None:
    global _settings
    _settings = new
