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


if __name__ == "__main__":
    unittest.main()
