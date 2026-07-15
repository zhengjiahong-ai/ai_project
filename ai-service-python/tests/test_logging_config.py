import logging
import os
import unittest


class LoggingConfigTests(unittest.TestCase):
    def setUp(self):
        # Clear handlers before each test
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

    def tearDown(self):
        # Restore defaults
        root = logging.getLogger()
        root.setLevel(logging.WARNING)
        for h in list(root.handlers):
            root.removeHandler(h)
        if "PIXIU_LOG_LEVEL" in os.environ:
            del os.environ["PIXIU_LOG_LEVEL"]
        if "PIXIU_LOG_JSON" in os.environ:
            del os.environ["PIXIU_LOG_JSON"]

    def test_configure_logging_sets_level_from_env(self):
        from core.logging_config import configure_logging

        os.environ["PIXIU_LOG_LEVEL"] = "DEBUG"
        configure_logging()
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_configure_logging_defaults_to_info(self):
        from core.logging_config import configure_logging

        configure_logging()
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_configure_logging_respects_explicit_level(self):
        from core.logging_config import configure_logging

        configure_logging(level="ERROR")
        self.assertEqual(logging.getLogger().level, logging.ERROR)

    def test_configure_logging_adds_handler(self):
        from core.logging_config import configure_logging

        configure_logging()
        self.assertGreaterEqual(len(logging.getLogger().handlers), 1)

    def test_json_formatter_produces_valid_json(self):
        from core.logging_config import _SanitizingJsonFormatter

        fmt = _SanitizingJsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello %s", args=("world",), exc_info=None,
        )
        output = fmt.format(record)
        import json
        parsed = json.loads(output)
        self.assertEqual(parsed["level"], "INFO")
        self.assertIn("hello world", parsed["message"])

    def test_sanitize_filters_api_key(self):
        from core.logging_config import _sanitize_value

        result = _sanitize_value({"api_key": "secret-123", "name": "test"})
        self.assertEqual(result["api_key"], "[REDACTED]")
        self.assertEqual(result["name"], "test")

    def test_sanitize_filters_paper_text(self):
        from core.logging_config import _sanitize_value

        result = _sanitize_value({"paper_text": "full content", "title": "ok"})
        self.assertEqual(result["paper_text"], "[REDACTED]")
        self.assertEqual(result["title"], "ok")

    def test_sanitize_truncates_long_strings(self):
        from core.logging_config import _sanitize_value, _MAX_STRING_LOG_LEN

        long_str = "x" * (_MAX_STRING_LOG_LEN + 100)
        result = _sanitize_value(long_str)
        self.assertLess(len(result), len(long_str))

    def test_sanitize_handles_nested_dicts(self):
        from core.logging_config import _sanitize_value

        result = _sanitize_value({"outer": {"api_key": "secret", "data": "ok"}})
        self.assertEqual(result["outer"]["api_key"], "[REDACTED]")
        self.assertEqual(result["outer"]["data"], "ok")

    def test_noisy_third_party_loggers_suppressed(self):
        from core.logging_config import configure_logging

        configure_logging()
        for name in ("httpx", "urllib3", "chromadb"):
            self.assertLessEqual(logging.getLogger(name).level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
