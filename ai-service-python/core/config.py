"""
Centralised configuration via pydantic-settings.

Usage::

    from core.config import settings
    model = settings.deepseek_model
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── LLM ────────────────────────────────────────────────────────────
    pixiu_llm_mode: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_temperature: float = 0.3
    deepseek_thinking_type: str = "enabled"
    deepseek_reasoning_effort: str = "high"
    deepseek_timeout_seconds: int = 120
    pixiu_llm_fixture_path: str = ""

    deepseek_translation_model: str = "deepseek-v4-flash"
    deepseek_translation_temperature: float = 0.1
    deepseek_translation_thinking_type: str | None = None
    deepseek_translation_reasoning_effort: str | None = None

    # ── Logging ────────────────────────────────────────────────────────
    pixiu_log_level: str = "INFO"
    pixiu_log_json: bool = False

    # ── Feature gates ──────────────────────────────────────────────────
    pixiu_allow_browser: bool = False
    pixiu_allow_reproducibility: bool = False

    # ── Runtime ────────────────────────────────────────────────────────
    pixiu_agentic_max_iterations: int = 3
    pixiu_max_tokens_per_task: int = 500_000
    pixiu_session_token_budget: int = 2_000_000

    # ── Network / external services ────────────────────────────────────
    grobid_server_url: str = "http://grobid:8070"
    semantic_scholar_api_key: str = ""

    # ── Paths ──────────────────────────────────────────────────────────
    paper_draft_dir: str = ""


settings = Settings()
