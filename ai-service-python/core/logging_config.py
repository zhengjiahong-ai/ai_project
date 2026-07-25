"""Centralized structured logging configuration for Pixiu AI service.

Configures the Python ``logging`` module with:
- ``PIXIU_LOG_LEVEL`` env var (default ``INFO``)
- ``PIXIU_LOG_JSON`` env var (default ``false``, set to ``true`` for structured JSON)
- A sanitizing formatter that redacts sensitive keys (API keys, full paper text, etc.)

Import and call ``configure_logging()`` once at application startup.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from core.config import settings

_LOG_DEFAULT_LEVEL = settings.pixiu_log_level

# Keys whose values must never appear in log output.
# Mirrors the sanitization list in trace_service.py.
_SENSITIVE_KEY_SUBSTRINGS = (
    "apikey", "api_key", "authorization", "cookie",
    "key", "password", "secret", "token",
)
_SENSITIVE_FIELD_NAMES = frozenset({
    "prompt", "systemprompt", "system_prompt", "systemmessage", "system_message",
    "papertext", "paper_text", "papercontent", "paper_content",
    "fulltext", "full_text", "documenttext", "document_text",
    "script", "scripttext", "script_text", "stdout", "stderr",
    "rawdata", "raw_data", "headers",
})

_SANITIZED_PLACEHOLDER = "[REDACTED]"
_MAX_STRING_LOG_LEN = 500


def _is_sensitive_key(key: str) -> bool:
    key_lower = str(key or "").lower()
    if key_lower in _SENSITIVE_FIELD_NAMES:
        return True
    return any(pattern in key_lower for pattern in _SENSITIVE_KEY_SUBSTRINGS)


def _sanitize_value(value: Any) -> Any:
    """Recursively redact sensitive values and truncate long strings."""
    if isinstance(value, dict):
        return {
            k: _SANITIZED_PLACEHOLDER if _is_sensitive_key(k) else _sanitize_value(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value[:12]]
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LOG_LEN:
            return value[:_MAX_STRING_LOG_LEN] + "..."
        return value
    return value


class _SanitizingTextFormatter(logging.Formatter):
    """Plain-text formatter that redacts sensitive fields."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        )

    def format(self, record: logging.LogRecord) -> str:
        if record.args and isinstance(record.args, dict):
            record.args = _sanitize_value(record.args)  # type: ignore[assignment]
        elif record.args and isinstance(record.args, (list, tuple)):
            record.args = tuple(_sanitize_value(a) for a in record.args)  # type: ignore[assignment]
        return super().format(record)


class _SanitizingJsonFormatter(logging.Formatter):
    """Structured JSON formatter that redacts sensitive fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])[:_MAX_STRING_LOG_LEN]
        if record.args and isinstance(record.args, dict):
            log_entry["extra"] = _sanitize_value(record.args)
        return json.dumps(log_entry, ensure_ascii=False, default=str)


def configure_logging(level: str | None = None) -> None:
    """Configure root logger for the Pixiu AI service.

    Call once at startup, typically from ``app.py``.

    Args:
        level: Log level string (DEBUG/INFO/WARNING/ERROR). Defaults to
               ``PIXIU_LOG_LEVEL`` env var or ``"INFO"``.
    """
    resolved_level = (level or settings.pixiu_log_level).upper()
    use_json = settings.pixiu_log_json

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, resolved_level, logging.INFO))

    # Remove any existing handlers to avoid duplication
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler: logging.Handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, resolved_level, logging.INFO))
    formatter: logging.Formatter = _SanitizingJsonFormatter() if use_json else _SanitizingTextFormatter()
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured: level=%s json=%s",
        resolved_level,
        use_json,
    )
