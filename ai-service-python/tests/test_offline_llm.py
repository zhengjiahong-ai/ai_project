import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from llm import client as llm_client
from llm.provider import LLMProviderError, LLMRequest, LLMResult, LLMUsage
from services.safety_service import estimate_tokens
from services import trace_service


class OfflineLlmTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fixture_path = Path(self.temp_dir.name) / "llm_responses.json"
        self.env = patch.dict(
            os.environ,
            {
                "PIXIU_LLM_MODE": "fixture",
                "PIXIU_LLM_FIXTURE_PATH": str(self.fixture_path),
            },
            clear=False,
        )
        self.env.start()
        os.environ.pop("DEEPSEEK_API_KEY", None)
        llm_client._llm = None
        llm_client._translation_llm = None

    def tearDown(self):
        trace_service.clear_traces()
        llm_client._llm = None
        llm_client._translation_llm = None
        self.env.stop()
        self.temp_dir.cleanup()

    def _write_fixture(self, responses):
        self.fixture_path.write_text(
            json.dumps({"schemaVersion": 1, "responses": responses}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_selects_fixture_clients_without_api_key_and_never_calls_http(self):
        self._write_fixture(
            [
                {
                    "id": "chat",
                    "client": "default",
                    "promptContains": ["offline question"],
                    "output": "offline answer",
                },
                {
                    "id": "translation",
                    "client": "translation",
                    "promptContains": ["translate this"],
                    "output": "固定译文",
                },
            ]
        )

        with patch("llm.client.requests.post") as post:
            answer = llm_client.get_llm()._call("offline question")
            translation = llm_client.get_translation_llm()._call("translate this")

        self.assertEqual(answer, "offline answer")
        self.assertEqual(translation, "固定译文")
        post.assert_not_called()

    def test_matches_messages_and_serializes_json_output(self):
        self._write_fixture(
            [
                {
                    "id": "json-plan",
                    "client": "default",
                    "promptContains": ["system marker", "user marker"],
                    "outputJson": {"brief": "固定计划", "subQuestions": ["问题一"]},
                }
            ]
        )

        result = llm_client.get_llm()._call(
            messages=[
                {"role": "system", "content": "system marker"},
                {"role": "user", "content": "user marker"},
            ]
        )

        self.assertEqual(json.loads(result)["brief"], "固定计划")

    def test_records_fixture_trace_counters(self):
        self._write_fixture(
            [
                {
                    "id": "trace",
                    "client": "default",
                    "promptContains": ["trace marker"],
                    "output": "trace output",
                }
            ]
        )
        trace_id = trace_service.start_trace("offline_test")

        llm_client.get_llm()._call("trace marker")

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["llmCalls"], 1)
        self.assertGreater(snapshot["counters"]["estimatedInputTokens"], 0)
        self.assertGreater(snapshot["counters"]["estimatedOutputTokens"], 0)
        self.assertEqual(snapshot["steps"][0]["meta"]["provider"], "fixture")

    def test_unmatched_prompt_fails_with_prompt_summary(self):
        self._write_fixture(
            [
                {
                    "id": "known",
                    "client": "default",
                    "promptContains": ["expected marker"],
                    "output": "known",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "No fixture response.*unknown marker"):
            llm_client.get_llm()._call("unknown marker")

    def test_ambiguous_match_fails_with_fixture_ids(self):
        self._write_fixture(
            [
                {
                    "id": "first",
                    "client": "default",
                    "promptContains": ["shared marker"],
                    "output": "first",
                },
                {
                    "id": "second",
                    "client": "default",
                    "promptContains": ["shared marker"],
                    "output": "second",
                },
            ]
        )

        with self.assertRaisesRegex(ValueError, "Ambiguous fixture response.*first.*second"):
            llm_client.get_llm()._call("shared marker")

    def test_rejects_invalid_fixture_schema(self):
        self.fixture_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "responses": [
                        {
                            "id": "invalid",
                            "client": "default",
                            "promptContains": [],
                            "output": "value",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "invalid.*promptContains"):
            llm_client.get_llm()

    def test_rejects_non_string_output(self):
        self._write_fixture(
            [
                {
                    "id": "invalid-output",
                    "client": "default",
                    "promptContains": ["marker"],
                    "output": 123,
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "invalid-output.*output must be a string"):
            llm_client.get_llm()

    def test_fixture_invoke_returns_provider_neutral_result_with_declared_usage(self):
        self._write_fixture(
            [
                {
                    "id": "structured",
                    "client": "default",
                    "promptContains": ["structured marker"],
                    "output": "structured answer",
                    "usage": {"inputTokens": 11, "outputTokens": 7, "totalTokens": 18},
                }
            ]
        )

        trace_id = trace_service.start_trace("declared_usage")
        result = llm_client.get_llm().invoke(LLMRequest(prompt="structured marker"))

        self.assertEqual(
            result,
            LLMResult(
                provider="fixture",
                model="structured",
                content="structured answer",
                usage=LLMUsage(input_tokens=11, output_tokens=7, total_tokens=18, estimated=False),
            ),
        )
        trace = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(trace["counters"]["estimatedInputTokens"], estimate_tokens("structured marker"))
        self.assertEqual(trace["counters"]["estimatedOutputTokens"], estimate_tokens("structured answer"))

    def test_fixture_invoke_estimates_usage_when_fixture_omits_it(self):
        self._write_fixture(
            [
                {
                    "id": "estimated",
                    "client": "default",
                    "promptContains": ["estimate marker"],
                    "output": "estimated answer",
                }
            ]
        )

        result = llm_client.get_llm().invoke(LLMRequest(prompt="estimate marker"))

        self.assertTrue(result.usage.estimated)
        self.assertGreater(result.usage.input_tokens, 0)
        self.assertGreater(result.usage.output_tokens, 0)
        self.assertEqual(
            result.usage.total_tokens,
            result.usage.input_tokens + result.usage.output_tokens,
        )

    def test_deepseek_invoke_normalizes_response_and_usage(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": "deepseek answer"}}],
            "usage": {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        }

        with patch("llm.client.requests.post", return_value=response):
            result = llm_client.DeepSeekLLM(model="deepseek-test", api_key="test-key").invoke(
                LLMRequest(prompt="deepseek marker")
            )

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.model, "deepseek-test")
        self.assertEqual(result.content, "deepseek answer")
        self.assertEqual(result.usage, LLMUsage(13, 5, 18, estimated=False))

    def test_deepseek_invoke_estimates_missing_usage(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": "answer without usage"}}],
        }

        with patch("llm.client.requests.post", return_value=response):
            result = llm_client.DeepSeekLLM(api_key="test-key").invoke(
                LLMRequest(prompt="usage fallback marker")
            )

        self.assertTrue(result.usage.estimated)
        self.assertEqual(result.usage.total_tokens, result.usage.input_tokens + result.usage.output_tokens)

    def test_deepseek_errors_are_normalized_without_response_body(self):
        response = Mock(status_code=429, text="secret upstream body")

        with patch("llm.client.requests.post", return_value=response):
            with self.assertRaises(LLMProviderError) as captured:
                llm_client.DeepSeekLLM(api_key="test-key").invoke(LLMRequest(prompt="rate limit"))

        self.assertEqual(captured.exception.provider, "deepseek")
        self.assertEqual(captured.exception.status_code, 429)
        self.assertTrue(captured.exception.retryable)
        self.assertNotIn("secret upstream body", str(captured.exception))

    def test_deepseek_rejects_malformed_response(self):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": []}

        with patch("llm.client.requests.post", return_value=response):
            with self.assertRaisesRegex(LLMProviderError, "invalid response"):
                llm_client.DeepSeekLLM(api_key="test-key").invoke(LLMRequest(prompt="malformed"))

    def test_default_and_translation_models_remain_unchanged(self):
        with patch.dict(
            os.environ,
            {"PIXIU_LLM_MODE": "deepseek", "DEEPSEEK_API_KEY": "test-key"},
            clear=False,
        ):
            llm_client._llm = None
            llm_client._translation_llm = None
            self.assertEqual(llm_client.get_llm().model, llm_client.DEFAULT_DEEPSEEK_MODEL)
            self.assertEqual(
                llm_client.get_translation_llm().model,
                llm_client.DEFAULT_DEEPSEEK_TRANSLATION_MODEL,
            )


if __name__ == "__main__":
    unittest.main()
