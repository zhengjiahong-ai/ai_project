import hashlib
import unittest

from services import trace_service


class ExternalSearchTraceTests(unittest.TestCase):
    def setUp(self):
        trace_service.clear_traces()

    def tearDown(self):
        trace_service.clear_traces()

    # ── summarize_external_search_query ──────────────────────────

    def test_summarize_external_search_query_normal_input(self):
        query = "machine learning retrieval systems"
        first = trace_service.summarize_external_search_query(query)
        second = trace_service.summarize_external_search_query(query)
        self.assertEqual(set(first), {"queryHash", "queryLength", "tokenCount"})
        self.assertEqual(len(first["queryHash"]), 16)
        self.assertEqual(first["queryLength"], len(query))
        self.assertEqual(first["tokenCount"], 4)
        self.assertEqual(first, second)

    def test_summarize_external_search_query_edge_cases(self):
        empty_hash = hashlib.sha256(b"").hexdigest()[:16]

        cases = [
            (None, empty_hash, 0, 0),
            ("", empty_hash, 0, 0),
            ("   ", empty_hash, 0, 0),
            ("\t\n  \r", empty_hash, 0, 0),
        ]
        for raw, expected_hash, expected_len, expected_tokens in cases:
            with self.subTest(raw=raw):
                result = trace_service.summarize_external_search_query(raw)
                self.assertEqual(result["queryHash"], expected_hash)
                self.assertEqual(result["queryLength"], expected_len)
                self.assertEqual(result["tokenCount"], expected_tokens)

    def test_summarize_external_search_query_unicode_and_long(self):
        result = trace_service.summarize_external_search_query("中文检索系统")
        self.assertEqual(len(result["queryHash"]), 16)
        self.assertEqual(result["queryLength"], 6)
        self.assertEqual(result["tokenCount"], 1)

        long_text = "x " * 500
        result = trace_service.summarize_external_search_query(long_text)
        self.assertEqual(len(result["queryHash"]), 16)
        self.assertEqual(result["queryLength"], len(long_text.strip()))
        self.assertEqual(result["tokenCount"], 500)

    def test_summarize_external_search_query_many_spaces_normalizes(self):
        result = trace_service.summarize_external_search_query("   many    spaces   here   ")
        normalized = "many spaces here"
        self.assertEqual(result["queryLength"], len(normalized))
        self.assertEqual(result["tokenCount"], 3)

    def test_summarize_external_search_query_non_string_types(self):
        int_result = trace_service.summarize_external_search_query(42)
        self.assertEqual(int_result["queryLength"], 2)
        self.assertEqual(int_result["tokenCount"], 1)

        list_result = trace_service.summarize_external_search_query([1, 2, 3])
        self.assertEqual(len(list_result["queryHash"]), 16)

        dict_result = trace_service.summarize_external_search_query({"key": "value"})
        self.assertEqual(len(dict_result["queryHash"]), 16)

    # ── start_trace counter initialization ───────────────────────

    def test_start_trace_initializes_all_external_search_counters(self):
        trace_id = trace_service.start_trace("unit_test")
        snapshot = trace_service.get_trace_snapshot(trace_id)
        counters = snapshot["counters"]

        expected = {
            "externalSearchCalls",
            "externalSearchCacheHits",
            "externalSearchFailures",
            "externalEvidenceCount",
            "externalSearchLatencyMs",
            "externalSearchBudgetBlocks",
        }
        for name in expected:
            self.assertIn(name, counters)
            self.assertEqual(counters[name], 0, f"{name} should start at 0")

        self.assertEqual(counters["llmCalls"], 0)
        self.assertEqual(counters["retrievalCalls"], 0)
        self.assertEqual(counters["codeExecutionCalls"], 0)
        self.assertEqual(counters["codeExecutionFailures"], 0)
        self.assertEqual(counters["codeExecutionOutputCount"], 0)

        # P6-17: verify web search/fetch + agentic loop counters are seeded
        web_counters = {
            "webSearchCalls", "webSearchResults", "webSearchFailures",
            "webSearchLatencyMs", "webSearchBudgetBlocks", "webSearchCacheHits",
            "webFetchCalls", "webFetchChars", "webFetchFailures",
            "webFetchBudgetBlocks", "webFetchCacheHits", "webFetchBytes",
            "agenticLoopIterations", "queryRefinementCalls",
        }
        for name in web_counters:
            self.assertIn(name, counters, f"{name} should be seeded")
            self.assertEqual(counters[name], 0, f"{name} should start at 0")

    # ── record_counter ───────────────────────────────────────────

    def test_record_counter_updates_each_external_search_counter(self):
        trace_id = trace_service.start_trace("unit_test")
        counters_to_test = [
            "externalSearchCalls",
            "externalSearchCacheHits",
            "externalSearchFailures",
            "externalEvidenceCount",
            "externalSearchLatencyMs",
            "externalSearchBudgetBlocks",
        ]
        for idx, name in enumerate(counters_to_test):
            trace_service.record_counter(name, idx + 1)

        snapshot = trace_service.get_trace_snapshot(trace_id)
        for idx, name in enumerate(counters_to_test):
            self.assertEqual(
                snapshot["counters"][name], idx + 1,
                f"{name} should be {idx + 1}",
            )

    def test_record_counter_accumulates_values(self):
        trace_id = trace_service.start_trace("unit_test")
        for _ in range(5):
            trace_service.record_counter("externalSearchCalls")
        trace_service.record_counter("externalSearchLatencyMs", 150)
        trace_service.record_counter("externalSearchLatencyMs", 200)

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["externalSearchCalls"], 5)
        self.assertEqual(snapshot["counters"]["externalSearchLatencyMs"], 350)

    # ── record_metric ────────────────────────────────────────────

    def test_record_metric_stores_numeric_values_overwrite(self):
        trace_id = trace_service.start_trace("unit_test")
        trace_service.record_metric("customLatency", 500)
        trace_service.record_metric("customLatency", 300)

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["customLatency"], 300)

    def test_record_metric_stores_non_numeric_in_response_meta(self):
        trace_id = trace_service.start_trace("unit_test")
        trace_service.record_metric("providerInfo", {"name": "crossref", "status": "ok"})

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertNotIn("providerInfo", snapshot["counters"])
        self.assertIn("providerInfo", snapshot["responseMeta"])
        self.assertEqual(
            snapshot["responseMeta"]["providerInfo"],
            {"name": "crossref", "status": "ok"},
        )

    # ── build_public_trace_summary ───────────────────────────────

    def test_build_public_trace_summary_includes_external_search_counters(self):
        trace_id = trace_service.start_trace("unit_test")
        trace_service.record_counter("externalSearchCalls", 3)
        trace_service.record_counter("externalSearchCacheHits", 1)
        trace_service.record_counter("externalSearchFailures", 1)
        trace_service.record_counter("externalEvidenceCount", 10)
        trace_service.record_counter("externalSearchLatencyMs", 450)
        trace_service.record_counter("externalSearchBudgetBlocks", 1)

        snapshot = trace_service.get_trace_snapshot(trace_id)
        summary = trace_service.build_public_trace_summary(snapshot)

        self.assertEqual(summary["counters"]["externalSearchCalls"], 3)
        self.assertEqual(summary["counters"]["externalSearchCacheHits"], 1)
        self.assertEqual(summary["counters"]["externalSearchFailures"], 1)
        self.assertEqual(summary["counters"]["externalEvidenceCount"], 10)
        self.assertEqual(summary["counters"]["externalSearchLatencyMs"], 450)
        self.assertEqual(summary["counters"]["externalSearchBudgetBlocks"], 1)
        self.assertEqual(summary["counters"]["llmCalls"], 0)

    # ── _public_sanitize_counters ────────────────────────────────

    def test_public_sanitize_counters_preserves_external_search_counter_values(self):
        counters = {
            "externalSearchCalls": 3,
            "externalSearchCacheHits": 1,
            "externalSearchFailures": 0,
            "externalEvidenceCount": 15,
            "externalSearchLatencyMs": 1200,
            "externalSearchBudgetBlocks": 2,
            "status": "running",
        }
        sanitized = trace_service._public_sanitize_counters(counters)
        self.assertEqual(sanitized["externalSearchCalls"], 3)
        self.assertEqual(sanitized["externalSearchCacheHits"], 1)
        self.assertEqual(sanitized["externalSearchFailures"], 0)
        self.assertEqual(sanitized["externalEvidenceCount"], 15)
        self.assertEqual(sanitized["externalSearchLatencyMs"], 1200)
        self.assertEqual(sanitized["externalSearchBudgetBlocks"], 2)
        self.assertEqual(sanitized["status"], "running")

    # ── _public_sanitize_meta ────────────────────────────────────

    def test_public_sanitize_meta_redacts_sensitive_keys(self):
        meta = {
            "api_key": "sk-secret-12345",
            "authorization": "Bearer token-abc",
            "cookie": "session=xyz",
            "prompt": "some system prompt text",
            "paper_text": "paper body content",
            "paperContent": "paper content value",
            "full_text": "full text data",
            "system_prompt": "system instructions",
            "headers": {"Authorization": "Basic secret"},
            "key": "encryption-key",
            "apikey": "api-key-value",
        }
        sanitized = trace_service._public_sanitize_meta(meta)
        for key in meta:
            self.assertEqual(sanitized[key], "[REDACTED]", f"{key} should be redacted")

    def test_public_sanitize_meta_redacts_nested_and_derived_keys(self):
        meta = {
            "openai_api_key": "sk-openai-123",
            "my_apikey": "secret-apikey",
            "paper_text_body": "text with paper+body",
            "some_full_text_content": "full text content",
            "nested": {"api_key": "inner-secret"},
        }
        sanitized = trace_service._public_sanitize_meta(meta)
        self.assertEqual(sanitized["openai_api_key"], "[REDACTED]")
        self.assertEqual(sanitized["my_apikey"], "[REDACTED]")
        self.assertEqual(sanitized["paper_text_body"], "[REDACTED]")
        self.assertEqual(sanitized["some_full_text_content"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["api_key"], "[REDACTED]")

    def test_public_sanitize_meta_preserves_safe_keys(self):
        meta = {
            "provider": "crossref",
            "querySummary": {
                "queryHash": "a1b2c3d4e5f6a1b2",
                "queryLength": 20,
                "tokenCount": 3,
            },
            "limit": 5,
            "callLimit": 3,
            "callsUsed": 1,
            "evidenceLimit": 15,
            "evidenceUsed": 7,
            "status": "success",
            "reason": "normal operation",
            "latencyMs": 450,
            "budget": {"callLimit": 3, "callsUsed": 0, "evidenceLimit": 15, "evidenceUsed": 0},
        }
        sanitized = trace_service._public_sanitize_meta(meta)
        self.assertEqual(sanitized["provider"], "crossref")
        self.assertEqual(sanitized["querySummary"]["queryHash"], "a1b2c3d4e5f6a1b2")
        self.assertEqual(sanitized["querySummary"]["queryLength"], 20)
        self.assertEqual(sanitized["querySummary"]["tokenCount"], 3)
        self.assertEqual(sanitized["limit"], 5)
        self.assertEqual(sanitized["status"], "success")
        self.assertEqual(sanitized["latencyMs"], 450)
        self.assertEqual(sanitized["budget"]["callLimit"], 3)
        self.assertEqual(sanitized["budget"]["callsUsed"], 0)

    # ── round-trip ──────────────────────────────────────────────

    def test_full_round_trip_start_record_finalize_build_summary(self):
        trace_id = trace_service.start_trace("integration_test")
        trace_service.record_counter("externalSearchCalls", 2)
        trace_service.record_counter("externalSearchCacheHits", 1)
        trace_service.record_counter("externalEvidenceCount", 7)
        snapshot = trace_service.finalize_trace("finished")

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["counters"]["externalSearchCalls"], 2)
        self.assertEqual(snapshot["counters"]["externalSearchCacheHits"], 1)
        self.assertEqual(snapshot["counters"]["externalEvidenceCount"], 7)

        summary = trace_service.build_public_trace_summary(snapshot)
        self.assertEqual(summary["traceId"], trace_id)
        self.assertEqual(summary["taskType"], "integration_test")
        self.assertEqual(summary["status"], "finished")
        self.assertIsNotNone(summary["startedAt"])
        self.assertIsNotNone(summary["finishedAt"])
        self.assertIsNotNone(summary["durationMs"])
        self.assertEqual(summary["counters"]["externalSearchCalls"], 2)
        self.assertEqual(summary["counters"]["externalSearchCacheHits"], 1)
        self.assertEqual(summary["counters"]["externalEvidenceCount"], 7)

    def test_external_search_step_metadata_is_sanitized_in_public_summary(self):
        trace_id = trace_service.start_trace("unit_test")
        meta = {
            "provider": "crossref",
            "querySummary": {
                "queryHash": "a1b2c3d4e5f6a1b2",
                "queryLength": 20,
                "tokenCount": 3,
            },
            "limit": 5,
            "budget": {"callLimit": 3, "callsUsed": 0, "evidenceLimit": 15, "evidenceUsed": 0},
            "api_key": "should-be-redacted",
        }
        with trace_service.trace_step(
            "tool_retrieve_external_academic",
            input_size=20,
            meta=meta,
        ) as step:
            step["outputSize"] = 3

        snapshot = trace_service.get_trace_snapshot(trace_id)
        summary = trace_service.build_public_trace_summary(snapshot)
        steps = summary["steps"]
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step["name"], "tool_retrieve_external_academic")
        self.assertEqual(step["status"], "success")
        self.assertEqual(step["inputSize"], 20)
        self.assertEqual(step["outputSize"], 3)
        self.assertIn("meta", step)
        self.assertEqual(step["meta"]["provider"], "crossref")
        self.assertEqual(step["meta"]["querySummary"]["queryHash"], "a1b2c3d4e5f6a1b2")
        self.assertEqual(step["meta"]["limit"], 5)
        self.assertEqual(step["meta"]["budget"]["callLimit"], 3)
        self.assertEqual(step["meta"]["api_key"], "[REDACTED]")
        self.assertNotIn("private-marker", str(step))
        for _key in step["meta"]:
            self.assertNotIn("raw query text", str(step["meta"]))

    # ── noop when no active trace ───────────────────────────────

    def test_record_counter_is_noop_when_no_active_trace(self):
        trace_service.clear_traces()
        try:
            trace_service.record_counter("externalSearchCalls", 1)
        except Exception as exc:
            self.fail(f"record_counter should not raise when no trace is active: {exc}")

    def test_record_metric_is_noop_when_no_active_trace(self):
        trace_service.clear_traces()
        try:
            trace_service.record_metric("externalSearchLatencyMs", 500)
        except Exception as exc:
            self.fail(f"record_metric should not raise when no trace is active: {exc}")

    # ── build_public_trace_summary steps window ──────────────────

    def test_public_trace_keeps_every_step_within_window(self):
        trace_id = trace_service.start_trace("unit_test")
        for i in range(15):
            with trace_service.trace_step(f"step_{i}"):
                pass
        snapshot = trace_service.get_trace_snapshot(trace_id)
        summary = trace_service.build_public_trace_summary(snapshot)
        self.assertEqual(len(summary["steps"]), 15)
        self.assertEqual(summary["stepsOmitted"], 0)

    def test_public_trace_truncates_middle_but_never_drops_final_steps(self):
        """收尾步骤必须可见。

        旧实现只取前 12 条，批判分析单次要 20+ 步，于是最贵的主张对齐
        （实测 70.6s / 总 161.6s）被静默截掉，看上去就像根本没发生。
        """
        trace_id = trace_service.start_trace("unit_test")
        for i in range(40):
            with trace_service.trace_step(f"step_{i}"):
                pass
        snapshot = trace_service.get_trace_snapshot(trace_id)
        summary = trace_service.build_public_trace_summary(snapshot)

        window = (
            trace_service._PUBLIC_TRACE_STEP_HEAD_LIMIT
            + trace_service._PUBLIC_TRACE_STEP_TAIL_LIMIT
        )
        self.assertEqual(len(summary["steps"]), window)
        # 省略条数显式回报，不把窗口误读成全部。
        self.assertEqual(summary["stepsOmitted"], 40 - window)
        names = [step["name"] for step in summary["steps"]]
        self.assertEqual(names[0], "step_0")
        self.assertEqual(names[-1], "step_39")
        # 中间被截掉的部分确实不在窗口里。
        self.assertNotIn("step_20", names)
