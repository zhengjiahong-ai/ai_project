"""P6-22 end-to-end integration tests for web search and iterative search pipelines.

These tests verify that the full pipeline — from search → fetch → judge →
evidence collection → report generation — works correctly with web search
enabled. All tests use mock providers so no network access is required.
"""
import unittest


class WebSearchE2EPipelineTests(unittest.TestCase):
    """End-to-end tests for the web search pipeline integrated with deep research."""

    def test_search_web_tool_registered_and_callable(self):
        from services.tool_registry import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get("search_web")
        self.assertIsNotNone(tool, "search_web tool must be registered")
        result = registry.invoke("search_web", {"query": "deep learning evaluation", "limit": 3})
        self.assertIn("status", result)
        self.assertIn("items", result)
        self.assertIn(result["status"], ("success", "disabled", "failed", "budget_exceeded"))

    def test_fetch_web_page_tool_registered_and_callable(self):
        from services.tool_registry import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get("fetch_web_page")
        self.assertIsNotNone(tool, "fetch_web_page tool must be registered")
        result = registry.invoke("fetch_web_page", {
            "url": "https://www.nature.com/article", "maxChars": 1000,
        })
        self.assertIn("status", result)
        self.assertIn(result["status"], ("success", "disabled", "failed", "budget_exceeded"))

    def test_retrieve_external_academic_still_works(self):
        """Academic search must work unchanged regardless of web search state."""
        from services.tool_registry import get_tool_registry

        registry = get_tool_registry()
        result = registry.invoke("retrieve_external_academic", {
            "query": "retrieval augmented generation", "limit": 2,
            "yearFrom": 2022, "yearTo": 2024,
        })
        self.assertIn(result["status"], ("success", "disabled", "failed", "budget_exceeded"))

    def test_judge_evidence_includes_coverage_diversity_fields(self):
        """P6-20: judge evidence output includes source diversity and trust fields."""
        from services.retrieval_judge_service import judge_evidence_quality

        evidence = [
            {"sourceType": "current_paper", "text": "Deep learning uses neural networks with many layers."},
            {"sourceType": "library", "text": "Neural network architectures include CNNs and transformers."},
        ]
        result = judge_evidence_quality(
            question="What is deep learning?",
            evidence_items=evidence,
            keywords=["deep", "learning", "neural"],
        )
        coverage = result.get("coverage", {})
        self.assertIn("sourceDiversityScore", coverage)
        self.assertIn("sourceTrustWeightedScore", coverage)
        self.assertIn("crossSourceAgreement", coverage)

    def test_evidence_items_have_provenance_when_normalized(self):
        """P6-19: normalized external evidence includes provenance field."""
        from services.external_evidence import normalize_external_evidence

        item = normalize_external_evidence({
            "provider": "Semantic Scholar",
            "providerId": "paper-1",
            "title": "Test Paper",
            "url": "https://example.org/paper",
            "retrievedAt": "2026-07-13T10:00:00Z",
            "query": "deep learning",
        })
        self.assertIn("provenance", item)
        self.assertIsInstance(item["provenance"], dict)
        self.assertEqual(item["provenance"]["discoveryPath"], "external_academic")

    def test_report_includes_all_required_sections(self):
        """P6-21: report includes evidence summary, cross-validation, provenance, and exec stats."""
        from services.research_aggregator import build_research_report

        findings = [{
            "subQuestion": "Test question",
            "summary": "Test summary.",
            "verdict": "CORRECT",
            "judgeScore": 75,
            "coverage": {
                "score": 0.6,
                "matchedAspects": 2,
                "totalAspects": 3,
                "evidenceCount": 2,
                "sourceTypes": ["current_paper", "library"],
                "sourceDiversityScore": 0.5,
                "sourceTrustWeightedScore": 0.85,
                "crossSourceAgreement": None,
            },
            "sourceIds": ["src-1", "src-2"],
            "sources": [
                {"sourceId": "src-1", "sourceType": "current_paper", "text": "Evidence text."},
                {"sourceId": "src-2", "sourceType": "library", "text": "More evidence."},
            ],
        }]
        trace = {"counters": {"llmCalls": 2, "retrievalCalls": 3}, "durationMs": 5000}

        report = build_research_report(
            "test question", "test brief", [], findings, trace_summary=trace,
        )

        required_sections = [
            "研究 brief",
            "子问题结论",
            "证据收集摘要",
            "综合判断",
            "证据不足与后续建议",
        ]
        for section in required_sections:
            self.assertIn(section, report, f"Report should contain section: {section}")
        self.assertIn("执行统计", report)

    def test_cross_validator_integration(self):
        """P6-18: cross validator produces valid claims from evidence."""
        from services.evidence_cross_validator import cross_validate_evidence

        evidence = [
            {"sourceId": "a", "sourceType": "current_paper",
             "text": "Deep learning achieves state-of-the-art results in image recognition tasks."},
            {"sourceId": "b", "sourceType": "external_academic",
             "text": "Deep learning methods outperform traditional approaches in computer vision."},
        ]
        result = cross_validate_evidence(evidence, use_llm=False)
        self.assertIn("claims", result)
        self.assertIn("summary", result)
        summary = result["summary"]
        self.assertIn("total_claims", summary)

    def test_agentic_loop_creates_evidence_with_provenance(self):
        """P6-19: agentic search loop evidence items carry provenance metadata."""
        from services.agentic_search_loop import run_agentic_search_loop

        def mock_search(query, limit=4):
            return {
                "status": "success", "provider": "brave",
                "items": [{"url": "https://www.nature.com/a", "title": "Test",
                           "description": "desc", "query": query}],
            }

        def mock_fetch(url, max_chars=8000):
            return {"status": "success", "content": f"Content from {url}"}

        def mock_judge(question, evidence_items):
            return {"verdict": "CORRECT", "confidence": 0.85, "missingAspects": [],
                    "coverage": {"score": 0.9}}

        result = run_agentic_search_loop(
            question="test", sub_question="test", missing_aspects=["aspect1"],
            query_plan={"keywords": []}, max_iterations=1,
            invoke_search=mock_search, invoke_fetch=mock_fetch, invoke_judge=mock_judge,
        )

        for item in result.get("evidence_items", []):
            self.assertIn("provenance", item)
            prov = item["provenance"]
            self.assertIn("discoveryPath", prov)
            self.assertIn("searchQuery", prov)
            self.assertIn("searchIteration", prov)

    def test_source_types_preserved_in_pipeline(self):
        """P6-20: web_search and web_page source types are preserved throughout."""
        from services.evidence_service import normalize_evidence_items

        items = [
            {"sourceType": "web_search", "text": "Web search result text for testing."},
            {"sourceType": "web_page", "text": "Fetched web page content for testing."},
            {"sourceType": "current_paper", "text": "Paper evidence for testing."},
        ]
        normalized = normalize_evidence_items(items)

        source_types = {item.get("sourceType") for item in normalized}
        self.assertIn("web_search", source_types)
        self.assertIn("web_page", source_types)
        self.assertIn("current_paper", source_types)


class MultiProviderDedupTests(unittest.TestCase):
    """Verify multi-provider search deduplication works correctly."""

    def test_deduplication_removes_duplicate_dois(self):
        from services.external_evidence import normalize_external_evidence, deduplicate_external_evidence

        item1 = normalize_external_evidence({
            "provider": "Crossref", "providerId": "work-1",
            "doi": "10.1000/test", "title": "Test Paper A",
        })
        item2 = normalize_external_evidence({
            "provider": "Semantic Scholar", "providerId": "s2-1",
            "doi": "10.1000/test", "title": "Test Paper A (duplicate)",
        })
        item3 = normalize_external_evidence({
            "provider": "ArXiv", "providerId": "arxiv-1",
            "title": "Unique Paper B",
        })

        deduped = deduplicate_external_evidence([item1, item2, item3])
        # DOI duplicate between item1 and item2 → one should be removed
        self.assertLessEqual(len(deduped), 2)
        titles = [d.get("title") for d in deduped]
        self.assertIn("Test Paper A", titles)
        self.assertIn("Unique Paper B", titles)


class GracefulDegradationTests(unittest.TestCase):
    """Verify graceful degradation when web search is unavailable."""

    def test_agentic_loop_handles_failed_search(self):
        from services.agentic_search_loop import run_agentic_search_loop

        def failing_search(query, limit=4):
            return {"status": "disabled", "provider": "disabled", "items": []}

        result = run_agentic_search_loop(
            question="test", sub_question="test", missing_aspects=["aspect1"],
            query_plan={"keywords": []}, max_iterations=3,
            invoke_search=failing_search,
        )
        self.assertEqual(result["iterations"], 0)
        self.assertFalse(result["web_search_used"])
        self.assertEqual(result["evidence_items"], [])

    def test_research_aggregator_handles_empty_findings(self):
        from services.research_aggregator import build_research_report

        report = build_research_report("test", "brief", [], [])
        self.assertIn("研究 brief", report)
        self.assertIn("综合判断", report)

    def test_judge_handles_empty_evidence(self):
        from services.retrieval_judge_service import judge_evidence_quality

        result = judge_evidence_quality("test", [], keywords=["test"])
        self.assertEqual(result["verdict"], "INCORRECT")
        self.assertLess(result["confidence"], 0.5)


if __name__ == "__main__":
    unittest.main()
