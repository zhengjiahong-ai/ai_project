import unittest

from services.trace_service import (
    clear_traces,
    finalize_trace,
    get_trace_snapshot,
    record_counter,
    record_metric,
    sanitize_text,
    start_trace,
    trace_step,
    use_trace,
)


class TraceServiceTests(unittest.TestCase):
    def setUp(self):
        clear_traces()

    def tearDown(self):
        clear_traces()

    def test_trace_records_success_steps_and_counters(self):
        trace_id = start_trace("chat", request_meta={"message": "简短问题"})

        with trace_step("retrieve_current_paper", input_size=12) as step:
            record_counter("retrievalCalls")
            record_metric("evidenceItems", 3)
            step["outputSize"] = 3

        finalize_trace("success", response_meta={"scope": "current_paper"})
        snapshot = get_trace_snapshot(trace_id)

        self.assertEqual(snapshot["status"], "success")
        self.assertEqual(snapshot["taskType"], "chat")
        self.assertEqual(snapshot["counters"]["retrievalCalls"], 1)
        self.assertEqual(snapshot["counters"]["evidenceItems"], 3)
        self.assertEqual(snapshot["steps"][0]["name"], "retrieve_current_paper")
        self.assertEqual(snapshot["steps"][0]["status"], "success")
        self.assertEqual(snapshot["steps"][0]["outputSize"], 3)
        self.assertIsNotNone(snapshot["finishedAt"])
        self.assertIsNotNone(snapshot["durationMs"])

    def test_trace_records_error_and_truncates_error_summary(self):
        trace_id = start_trace("critical")

        with self.assertRaises(RuntimeError):
            with trace_step("structured_report"):
                raise RuntimeError("X" * 500)

        finalize_trace("error", error="Y" * 500)
        snapshot = get_trace_snapshot(trace_id)

        self.assertEqual(snapshot["status"], "error")
        self.assertEqual(snapshot["steps"][0]["status"], "error")
        self.assertLessEqual(len(snapshot["steps"][0]["error"]), 243)
        self.assertLessEqual(len(snapshot["error"]), 243)

    def test_sanitize_text_and_manual_trace_context_hide_long_or_sensitive_content(self):
        raw = "token " * 120
        self.assertLessEqual(len(sanitize_text(raw, max_chars=40)), 43)

        trace_id = start_trace("deep_research", activate=False, initial_status="pending")
        with use_trace(trace_id):
            with trace_step("queue_task", meta={"question": raw, "apiKey": "secret"}) as step:
                record_counter("llmCalls")
                step["outputSize"] = 1
            finalize_trace("cancelled", response_meta={"question": raw})

        snapshot = get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["status"], "cancelled")
        self.assertEqual(snapshot["counters"]["llmCalls"], 1)
        self.assertTrue(snapshot["steps"][0]["meta"]["question"].endswith("..."))
        self.assertNotIn(raw, str(snapshot))


if __name__ == "__main__":
    unittest.main()
