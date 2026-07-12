import unittest


def _mock_search_success(query, limit=4):
    return {
        "status": "success",
        "provider": "brave",
        "items": [
            {"url": "https://www.nature.com/article1", "title": "Key findings on aspect1", "description": "A very long description with detailed information about the research topic."},
            {"url": "https://github.com/project", "title": "Code repo", "description": "Implementation details."},
        ],
    }


def _mock_fetch_success(url, max_chars=8000):
    return {"status": "success", "content": f"Fetched content from {url}"}


def _mock_judge_correct(question, evidence_items):
    return {"verdict": "CORRECT", "confidence": 0.85, "missingAspects": [], "coverage": {"score": 0.9}}


def _mock_judge_incorrect(question, evidence_items):
    return {"verdict": "INCORRECT", "confidence": 0.3, "missingAspects": ["still missing x"], "coverage": {"score": 0.3}}


class AgenticSearchLoopTests(unittest.TestCase):
    def test_module_imports(self):
        from services import agentic_search_loop
        self.assertIsNotNone(agentic_search_loop)

    def test_terminates_when_verdict_correct_and_confident(self):
        from services.agentic_search_loop import run_agentic_search_loop

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": ["key1"]},
            max_iterations=3,
            invoke_search=_mock_search_success,
            invoke_fetch=_mock_fetch_success,
            invoke_judge=_mock_judge_correct,
        )
        self.assertIn("iterations", result)
        self.assertEqual(result["verdict"], "CORRECT")
        self.assertGreaterEqual(result["confidence"], 0.75)
        self.assertTrue(result["web_search_used"])

    def test_terminates_at_max_iterations(self):
        from services.agentic_search_loop import run_agentic_search_loop

        # Judge always says INCORRECT → loop runs to max
        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": []},
            max_iterations=1,
            invoke_search=_mock_search_success,
            invoke_fetch=_mock_fetch_success,
            invoke_judge=_mock_judge_incorrect,
        )
        self.assertEqual(result["iterations"], 1)

    def test_handles_empty_missing_aspects(self):
        from services.agentic_search_loop import run_agentic_search_loop

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=[],
            query_plan={"keywords": []},
            max_iterations=3,
        )
        self.assertEqual(result["iterations"], 0)
        self.assertEqual(result["evidence_items"], [])

    def test_respects_cancel_signal(self):
        from services.agentic_search_loop import run_agentic_search_loop

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": []},
            max_iterations=3,
            should_cancel=lambda: True,
        )
        self.assertEqual(result["iterations"], 0)

    def test_url_priority_sorting(self):
        from services.agentic_search_loop import _select_top_urls

        items = [
            {"url": "https://example.com/a", "title": "Some title", "description": "short"},
            {"url": "https://www.nature.com/b", "title": "Key Nature paper", "description": "longer desc here"},
            {"url": "https://github.com/c", "title": "Code repo", "description": "medium desc"},
            {"url": "https://en.wikipedia.org/d", "title": "Wiki article matching aspect1", "description": "very long description text"},
        ]
        selected = _select_top_urls(items, missing_aspects=["aspect1"], max_urls=3)
        self.assertLessEqual(len(selected), 3)
        urls = [s["url"] for s in selected]
        self.assertTrue(any("nature.com" in u for u in urls))

    def test_handles_search_failure(self):
        from services.agentic_search_loop import run_agentic_search_loop

        def failing_search(query, limit=4):
            return {"status": "disabled", "provider": "disabled", "items": []}

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": []},
            max_iterations=3,
            invoke_search=failing_search,
        )
        self.assertEqual(result["iterations"], 0)
        self.assertFalse(result["web_search_used"])

    # ---- P6-15: search-result-driven fetch priority ----

    def test_select_top_urls_respects_skip_urls(self):
        """Verify _select_top_urls excludes URLs in skip_urls."""
        from services.agentic_search_loop import _select_top_urls

        items = [
            {"url": "https://www.nature.com/a", "title": "Key finding on aspect1",
             "description": "A very detailed and long description about the research topic."},
            {"url": "https://github.com/b", "title": "Code repo",
             "description": "Some description."},
            {"url": "https://www.nature.com/c", "title": "Another finding matching aspect1",
             "description": "Another long description with detailed analysis."},
        ]
        skip = {"https://www.nature.com/a"}
        selected = _select_top_urls(items, missing_aspects=["aspect1"], max_urls=3,
                                     skip_urls=skip)
        urls = [s["url"] for s in selected]
        self.assertNotIn("https://www.nature.com/a", urls)
        self.assertIn("https://www.nature.com/c", urls)
        self.assertLessEqual(len(selected), 2)

    def test_select_top_urls_empty_skip_urls_defaults(self):
        """Verify _select_top_urls works normally when skip_urls is None/empty."""
        from services.agentic_search_loop import _select_top_urls

        items = [
            {"url": "https://www.nature.com/a", "title": "Key finding",
             "description": "long description."},
            {"url": "https://github.com/b", "title": "Code repo",
             "description": "medium desc."},
        ]
        selected1 = _select_top_urls(items, max_urls=2)
        selected2 = _select_top_urls(items, max_urls=2, skip_urls=set())
        selected3 = _select_top_urls(items, max_urls=2, skip_urls=None)
        self.assertEqual(len(selected1), 2)
        self.assertEqual(len(selected2), 2)
        self.assertEqual(len(selected3), 2)

    def test_select_top_urls_all_skipped_returns_empty(self):
        """When all URLs are in skip_urls, return empty list."""
        from services.agentic_search_loop import _select_top_urls

        items = [
            {"url": "https://example.com/a", "title": "A", "description": "desc"},
            {"url": "https://example.com/b", "title": "B", "description": "desc"},
        ]
        skip = {"https://example.com/a", "https://example.com/b"}
        selected = _select_top_urls(items, max_urls=3, skip_urls=skip)
        self.assertEqual(selected, [])

    def test_avoids_duplicate_fetches_across_rounds(self):
        """Verify a URL fetched in round 1 is not fetched again in round 2."""
        from services.agentic_search_loop import run_agentic_search_loop

        fetch_log = []
        def mock_fetch(url, max_chars=8000):
            fetch_log.append(url)
            return {"status": "success", "content": f"content from {url}"}

        call_count = [0]
        def mock_judge(question, evidence_items):
            call_count[0] += 1
            if call_count[0] >= 2:
                return {"verdict": "CORRECT", "confidence": 0.85,
                        "missingAspects": [], "coverage": {"score": 0.9}}
            return {"verdict": "INCORRECT", "confidence": 0.3,
                    "missingAspects": ["still missing x"],
                    "coverage": {"score": 0.3}}

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": ["key1"]},
            max_iterations=3,
            invoke_search=_mock_search_success,
            invoke_fetch=mock_fetch,
            invoke_judge=mock_judge,
        )
        # nature.com/article1 appears in both rounds -- should only be fetched once
        nature_fetches = [u for u in fetch_log
                          if u == "https://www.nature.com/article1"]
        self.assertEqual(len(nature_fetches), 1)
        self.assertGreaterEqual(result["pages_fetched"], 1)

    def test_skips_cached_urls_in_selection(self):
        """Verify URLs present in fetch_cache are skipped during selection."""
        from services.agentic_search_loop import run_agentic_search_loop

        class _MockCache:
            def __init__(self, hits):
                self._hits = set(hits)
            def get(self, url):
                return {"status": "success"} if url in self._hits else None

        mock_cache = _MockCache({"https://www.nature.com/article1"})

        fetch_log = []
        def mock_fetch(url, max_chars=8000):
            fetch_log.append(url)
            return {"status": "success", "content": f"content from {url}"}

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": ["key1"]},
            max_iterations=1,
            invoke_search=_mock_search_success,
            invoke_fetch=mock_fetch,
            invoke_judge=_mock_judge_correct,
            fetch_cache=mock_cache,
        )
        # nature.com/article1 is cached, so it should NOT be fetched
        self.assertNotIn("https://www.nature.com/article1", fetch_log)
        # github.com/project should still be fetched (not cached)
        self.assertIn("https://github.com/project", fetch_log)

    def test_combined_skip_cache_and_session(self):
        """Verify both cache-provided and session-fetched URLs are combined in skip set."""
        from services.agentic_search_loop import run_agentic_search_loop

        class _MockCache:
            def __init__(self, hits):
                self._hits = set(hits)
            def get(self, url):
                return {"status": "success"} if url in self._hits else None

        # cache already has github URL
        mock_cache = _MockCache({"https://github.com/project"})

        fetch_log = []
        def mock_fetch(url, max_chars=8000):
            fetch_log.append(url)
            return {"status": "success", "content": f"content from {url}"}

        # Judge says INCORRECT round 1 so round 2 runs with same search results
        call_count = [0]
        def mock_judge(question, evidence_items):
            call_count[0] += 1
            if call_count[0] >= 2:
                return {"verdict": "CORRECT", "confidence": 0.85,
                        "missingAspects": [], "coverage": {"score": 0.9}}
            return {"verdict": "INCORRECT", "confidence": 0.3,
                    "missingAspects": ["still missing"],
                    "coverage": {"score": 0.3}}

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": ["key1"]},
            max_iterations=3,
            invoke_search=_mock_search_success,
            invoke_fetch=mock_fetch,
            invoke_judge=mock_judge,
            fetch_cache=mock_cache,
        )
        # github is cached, should never be fetched
        self.assertNotIn("https://github.com/project", fetch_log)
        # nature.com is NOT cached but should be fetched at most once
        nature_count = fetch_log.count("https://www.nature.com/article1")
        self.assertLessEqual(nature_count, 1)
        # At least nature.com was fetched once
        self.assertGreaterEqual(nature_count, 1)

    def test_on_progress_callback_called_each_iteration(self):
        """Verify on_progress is called with (iteration, pages_fetched, confidence) each round."""
        from services.agentic_search_loop import run_agentic_search_loop

        progress_log = []
        def on_progress(iteration, pages_fetched, confidence):
            progress_log.append((iteration, pages_fetched, confidence))

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": ["key1"]},
            max_iterations=2,
            invoke_search=_mock_search_success,
            invoke_fetch=_mock_fetch_success,
            invoke_judge=_mock_judge_correct,
            on_progress=on_progress,
        )
        # Should be called at least once (after each iteration)
        self.assertGreaterEqual(len(progress_log), 1)
        # First call: iteration=1, pages_fetched>=1, confidence is a float
        self.assertEqual(progress_log[0][0], 1)  # iteration
        self.assertGreaterEqual(progress_log[0][1], 1)  # pages_fetched
        self.assertIsInstance(progress_log[0][2], float)  # confidence

    def test_on_progress_none_does_not_crash(self):
        """Verify loop works unchanged when on_progress is None (backward compat)."""
        from services.agentic_search_loop import run_agentic_search_loop

        result = run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": ["key1"]},
            max_iterations=1,
            invoke_search=_mock_search_success,
            invoke_fetch=_mock_fetch_success,
            invoke_judge=_mock_judge_correct,
            on_progress=None,
        )
        self.assertEqual(result["verdict"], "CORRECT")
        self.assertTrue(result["web_search_used"])

    def test_records_agentic_loop_iterations_counter(self):
        """Verify agenticLoopIterations counter is recorded each iteration."""
        from services.agentic_search_loop import run_agentic_search_loop
        from services.trace_service import start_trace, get_trace_snapshot, clear_traces

        clear_traces()
        trace_id = start_trace("unit_test")

        run_agentic_search_loop(
            question="test",
            sub_question="test sub",
            missing_aspects=["aspect1"],
            query_plan={"keywords": ["key1"]},
            max_iterations=2,
            invoke_search=_mock_search_success,
            invoke_fetch=_mock_fetch_success,
            invoke_judge=_mock_judge_correct,
        )
        snapshot = get_trace_snapshot(trace_id)
        counters = snapshot.get("counters", {})
        self.assertGreaterEqual(counters.get("agenticLoopIterations", 0), 1)
        clear_traces()


if __name__ == "__main__":
    unittest.main()
