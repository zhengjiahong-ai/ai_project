"""Tests for core/config.py"""
import pytest
from core.config import Settings, settings


def test_settings_singleton_exists():
    assert settings is not None
    assert isinstance(settings, Settings)


def test_llm_defaults():
    assert settings.deepseek_model == "deepseek-v4-pro"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_temperature == 0.3
    assert settings.deepseek_thinking_type == "enabled"
    assert settings.deepseek_reasoning_effort == "high"
    assert settings.deepseek_timeout_seconds == 120
    assert settings.deepseek_translation_model == "deepseek-v4-flash"
    assert settings.deepseek_translation_temperature == 0.1
    assert settings.deepseek_translation_thinking_type is None
    assert settings.deepseek_translation_reasoning_effort is None
    assert settings.pixiu_llm_mode == "deepseek"


def test_logging_defaults():
    assert settings.pixiu_log_level == "INFO"
    assert settings.pixiu_log_json is False


def test_features_default_off():
    assert settings.pixiu_allow_browser is False
    assert settings.pixiu_allow_reproducibility is False


def test_runtime_defaults():
    assert settings.pixiu_agentic_max_iterations == 3
    assert settings.pixiu_max_tokens_per_task == 500_000
    assert settings.pixiu_session_token_budget == 2_000_000


def test_grobid_default():
    assert settings.grobid_server_url == "http://grobid:8070"


def test_env_override(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("PIXIU_LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.deepseek_model == "deepseek-v4-flash"
    assert s.pixiu_log_level == "DEBUG"


def test_feature_gate_bool_parsing(monkeypatch):
    monkeypatch.setenv("PIXIU_ALLOW_BROWSER", "true")
    s = Settings()
    assert s.pixiu_allow_browser is True


def test_runtime_int_parsing(monkeypatch):
    monkeypatch.setenv("PIXIU_MAX_TOKENS_PER_TASK", "100000")
    s = Settings()
    assert s.pixiu_max_tokens_per_task == 100000
