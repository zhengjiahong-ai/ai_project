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

    # 结构化抽取与判定专用温度（检索查询改写、证据判定、主张对齐、结构化报告）。
    # 这类任务的正确输出是输入的函数，要的是可复现而不是文采：默认 0.3 下实测同一篇
    # 论文跑两次得到 5 条与 6 条不同主张，相似度区间也不同，而且链路最上游的查询
    # 改写一变，下游每一个 prompt 都跟着变，LLM 缓存因此完全失效。模型与思考强度
    # 沿用主模型，只改采样温度，分析质量不受影响。
    deepseek_structured_temperature: float = 0.0

    # ── Logging ────────────────────────────────────────────────────────
    pixiu_log_level: str = "INFO"
    pixiu_log_json: bool = False

    # ── Feature gates ──────────────────────────────────────────────────
    pixiu_allow_browser: bool = False
    pixiu_allow_reproducibility: bool = False
    pixiu_mcp_enabled: bool = False
    pixiu_mcp_transport: str = "stdio"
    pixiu_mcp_sse_host: str = "127.0.0.1"
    pixiu_mcp_sse_port: int = 8001
    pixiu_mcp_auth_token: str = ""

    # ── Runtime ────────────────────────────────────────────────────────
    pixiu_agentic_max_iterations: int = 3
    pixiu_max_tokens_per_task: int = 500_000
    pixiu_session_token_budget: int = 2_000_000
    pixiu_task_pool_size: int = 2

    # ── Timeouts (seconds) ─────────────────────────────────────────────
    pixiu_retrieval_timeout_seconds: int = 15
    pixiu_external_search_timeout_seconds: int = 20
    pixiu_web_fetch_timeout_seconds: int = 30

    # ── Observability ───────────────────────────────────────────────────
    pixiu_slow_query_threshold_ms: int = 3000

    # ── Network / external services ────────────────────────────────────
    grobid_server_url: str = "http://grobid:8070"
    semantic_scholar_api_key: str = ""

    # ── Paths ──────────────────────────────────────────────────────────
    paper_draft_dir: str = ""

    # ── Evidence credibility weights (14-2) ──────────────────────────────
    pixiu_credibility_current_paper_weight: float = 1.0
    pixiu_credibility_library_weight: float = 0.85
    pixiu_credibility_external_academic_weight: float = 0.65
    pixiu_credibility_web_search_weight: float = 0.45
    pixiu_credibility_web_page_weight: float = 0.40
    pixiu_credibility_default_weight: float = 0.30

    # ── LLM cache (15-2) ──────────────────────────────────────────────
    pixiu_llm_cache_mode: str = "exact"
    pixiu_llm_cache_ttl_minutes: int = 60
    pixiu_llm_cache_path: str = ""

    # ── Rate limiter (15-3) ────────────────────────────────────────────
    pixiu_rate_limit_enabled: bool = True
    pixiu_rate_limit_global_rpm: int = 60
    pixiu_rate_limit_agent_rpm: int = 10
    pixiu_rate_limit_chat_rpm: int = 30
    pixiu_rate_limit_translate_rpm: int = 10

    # ── Auth (19-1) ────────────────────────────────────────────────────
    pixiu_api_auth_token: str = ""


settings = Settings()
