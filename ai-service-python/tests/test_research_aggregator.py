import unittest
from unittest.mock import patch

from services.research_aggregator import (
    build_judge_trace_summary,
    build_research_report,
)


class ResearchAggregatorReportTests(unittest.TestCase):
    def setUp(self):
        self.question = "What is deep learning?"
        self.brief = "本研究旨在调查深度学习的现状。"
        self.plan_items = [
            {"id": "q1", "question": "子问题1", "kind": "evidence", "status": "done"},
            {"id": "q2", "question": "子问题2", "kind": "evidence", "status": "done"},
        ]
        # Mock get_llm to force executive summary fallback in all tests
        self._llm_patcher = patch(
            "llm.client.get_llm",
            side_effect=RuntimeError("LLM not available in test"),
        )
        self._llm_patcher.start()

    def tearDown(self):
        self._llm_patcher.stop()

    def _make_finding(self, idx, verdict="CORRECT", extra=None):
        finding = {
            "subQuestion": f"子问题{idx}",
            "summary": f"围绕子问题{idx}的结论。",
            "verdict": verdict,
            "judgeScore": 78,
            "coverage": {
                "score": 0.65,
                "matchedAspects": 3,
                "totalAspects": 5,
                "evidenceCount": 2,
                "sourceTypes": ["current_paper", "library"],
                "sourceDiversityScore": 0.69,
                "sourceTrustWeightedScore": 0.925,
                "crossSourceAgreement": 0.5,
            },
            "missingAspects": ["missing1"] if verdict != "CORRECT" else [],
            "retryReason": "",
            "externalSearchDegradation": "",
            "webSearchUsed": False,
            "sourceIds": [f"src-{idx}-1", f"src-{idx}-2"],
            "sources": [
                {
                    "sourceId": f"src-{idx}-1",
                    "sourceType": "current_paper",
                    "text": f"Evidence from current paper for sub-question {idx}.",
                },
                {
                    "sourceId": f"src-{idx}-2",
                    "sourceType": "library",
                    "text": f"Library evidence for sub-question {idx}.",
                },
            ],
        }
        if extra:
            finding.update(extra)
        return finding

    # ---- P6-21: evidence collection summary ----

    def test_report_includes_evidence_summary_section(self):
        """Report includes evidence collection summary with source distribution."""
        findings = [self._make_finding(1), self._make_finding(2)]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("证据收集摘要", report)
        self.assertIn("current_paper", report)
        self.assertIn("library", report)

    def test_evidence_summary_counts_source_types(self):
        """Evidence summary counts evidence items by source type."""
        findings = [
            self._make_finding(1, extra={
                "sources": [
                    {"sourceId": "a", "sourceType": "current_paper", "text": "text a."},
                    {"sourceId": "b", "sourceType": "current_paper", "text": "text b."},
                    {"sourceId": "c", "sourceType": "external_academic", "text": "text c."},
                ],
            }),
        ]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("current_paper", report)
        self.assertIn("external_academic", report)

    # ---- P6-21: per-finding coverage enrichment ----

    def test_per_finding_includes_judge_score(self):
        """Each finding subsection includes judgeScore."""
        findings = [self._make_finding(1)]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("78/100", report)

    def test_per_finding_includes_coverage_diversity(self):
        """Each finding subsection includes source diversity and trust scores."""
        findings = [self._make_finding(1)]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("多样性", report)
        self.assertIn("可信度", report)

    def test_per_finding_includes_source_type_counts(self):
        """Each finding shows source type distribution."""
        finding = self._make_finding(1, extra={
            "sources": [
                {"sourceId": "a", "sourceType": "current_paper", "text": "text."},
                {"sourceId": "b", "sourceType": "library", "text": "text."},
                {"sourceId": "c", "sourceType": "web_search", "text": "text."},
            ],
        })
        finding["coverage"]["sourceTypes"] = ["current_paper", "library", "web_search"]
        findings = [finding]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("web_search", report)

    def test_cross_source_agreement_shown_when_available(self):
        """crossSourceAgreement is displayed when not None."""
        findings = [self._make_finding(1)]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("跨源一致性", report)

    def test_cross_source_agreement_unavailable_when_none(self):
        """Shows '无法评估' when crossSourceAgreement is None."""
        finding = self._make_finding(1)
        finding["coverage"]["crossSourceAgreement"] = None
        finding["coverage"]["sourceTypes"] = ["current_paper"]
        findings = [finding]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("无法评估", report)

    # ---- P6-21: provenance section ----

    def test_report_includes_provenance_section_for_external_evidence(self):
        """Report includes source provenance section when external evidence exists."""
        finding = self._make_finding(1, extra={
            "sources": [
                {
                    "sourceId": "ext-1",
                    "sourceType": "external_academic",
                    "text": "External evidence.",
                    "provider": "Semantic Scholar",
                    "url": "https://example.org/paper",
                    "provenance": {
                        "discoveryPath": "external_academic",
                        "searchQuery": "deep learning survey",
                        "searchIteration": None,
                        "sourceUrl": "https://example.org/paper",
                        "retrievalTimestamp": "2026-07-13T10:00:00Z",
                    },
                },
            ],
        })
        findings = [finding]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("来源追溯", report)
        self.assertIn("Semantic Scholar", report)

    def test_provenance_shows_web_search_path(self):
        """Web search provenance shows discovery path with query and iteration."""
        finding = self._make_finding(1, extra={
            "sources": [
                {
                    "sourceId": "web-1",
                    "sourceType": "web_page",
                    "text": "Web fetched content.",
                    "url": "https://example.com/page",
                    "provenance": {
                        "discoveryPath": "web_search→web_page",
                        "searchQuery": "deep learning",
                        "searchIteration": 2,
                        "sourceUrl": "https://example.com/page",
                        "retrievalTimestamp": "2026-07-13T10:05:00Z",
                    },
                },
            ],
        })
        findings = [finding]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertIn("来源追溯", report)
        self.assertIn("web_search", report)
        self.assertIn("第2轮", report)

    def test_no_provenance_section_when_no_external_evidence(self):
        """Provenance section is omitted when no external/web evidence exists."""
        findings = [self._make_finding(1)]  # only current_paper + library
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertNotIn("来源追溯", report)

    # ---- P6-21: execution statistics ----

    def test_report_includes_execution_stats_when_trace_provided(self):
        """Execution statistics section appears when trace_summary is provided."""
        findings = [self._make_finding(1)]
        trace = {
            "counters": {
                "llmCalls": 3,
                "retrievalCalls": 5,
                "externalSearchCalls": 1,
                "webSearchCalls": 0,
                "webFetchCalls": 0,
                "agenticLoopIterations": 0,
            },
            "durationMs": 12345,
        }
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
            trace_summary=trace,
        )
        self.assertIn("执行统计", report)
        self.assertIn("LLM 调用", report)
        self.assertIn("检索调用", report)

    def test_report_omits_execution_stats_when_no_trace(self):
        """Execution statistics section is omitted when trace_summary is not provided."""
        findings = [self._make_finding(1)]
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
        )
        self.assertNotIn("执行统计", report)

    def test_execution_stats_shows_web_metrics_when_present(self):
        """Web search/fetch metrics appear when non-zero."""
        findings = [self._make_finding(1)]
        trace = {
            "counters": {
                "llmCalls": 2,
                "retrievalCalls": 3,
                "externalSearchCalls": 1,
                "webSearchCalls": 2,
                "webFetchCalls": 3,
                "agenticLoopIterations": 2,
            },
            "durationMs": 15000,
        }
        report = build_research_report(
            self.question, self.brief, self.plan_items, findings,
            trace_summary=trace,
        )
        self.assertIn("Web 搜索", report)
        self.assertIn("页面抓取", report)
        self.assertIn("迭代搜索轮次", report)

    # ---- backward compatibility ----

    def test_report_backward_compatible_old_format(self):
        """Report generation works with minimal old-format findings."""
        old_finding = {
            "subQuestion": "Old question",
            "summary": "Old summary.",
            "verdict": "CORRECT",
            "sourceIds": ["src-1"],
            "sources": [{"sourceId": "src-1", "sourceType": "current_paper", "text": "text."}],
        }
        report = build_research_report(
            self.question, self.brief, self.plan_items, [old_finding],
        )
        self.assertIn("研究 brief", report)
        self.assertIn("子问题结论", report)
        self.assertIn("综合判断", report)

    def test_report_handles_empty_findings(self):
        """Report works with empty findings list."""
        report = build_research_report(
            self.question, self.brief, self.plan_items, [],
        )
        self.assertIn("研究 brief", report)
        self.assertIn("综合判断", report)

    def test_build_judge_trace_summary(self):
        findings = [
            self._make_finding(1, verdict="CORRECT"),
            self._make_finding(2, verdict="INCORRECT", extra={"judgeScore": 42, "retryReason": "retry needed"}),
        ]
        summary = build_judge_trace_summary(findings)
        self.assertIsNotNone(summary["averageJudgeScore"])
        self.assertEqual(summary["retryFindingCount"], 1)
        self.assertEqual(summary["insufficientFindingCount"], 1)

    # ── 3-2: Report depth upgrade tests ──────────────────────────────────

    def test_report_includes_executive_summary(self):
        report = build_research_report(
            self.question, self.brief, self.plan_items,
            [self._make_finding(1)], [],
        )
        self.assertIn("执行摘要", report)

    def test_report_includes_hierarchical_citations(self):
        finding = self._make_finding(1)
        finding["sources"] = [
            {"sourceId": "src-1", "sourceType": "current_paper", "text": "Evidence text A.", "chunkIndex": 0},
            {"sourceId": "src-1", "sourceType": "current_paper", "text": "Evidence text B.", "chunkIndex": 1},
            {"sourceId": "src-2", "sourceType": "library", "text": "Another source.", "chunkIndex": 0},
        ]
        report = build_research_report(
            self.question, self.brief, self.plan_items,
            [finding], [],
        )
        self.assertIn("引用索引", report)
        self.assertIn("[1]", report)
        self.assertIn("[1.1]", report)
        self.assertIn("[1.2]", report)

    def test_report_includes_evidence_comparison_table(self):
        finding = self._make_finding(1)
        finding["sources"] = [
            {"sourceId": "s1", "sourceType": "current_paper", "text": "Method A achieves 95% accuracy."},
            {"sourceId": "s2", "sourceType": "external_academic", "text": "Prior work reports 92%."},
        ]
        report = build_research_report(
            self.question, self.brief, self.plan_items,
            [finding], [],
        )
        self.assertIn("证据对比表", report)
        self.assertIn("当前论文", report)
        self.assertIn("95%", report)

    def test_report_includes_dispute_map_with_conflicts(self):
        finding = self._make_finding(1)
        conflicts = [{
            "id": "c-1", "claim": "数值差异", "conflictType": "numeric_mismatch",
            "severity": "high", "summary": "不同来源数值矛盾",
            "sourceIds": ["src-a", "src-b"],
        }]
        report = build_research_report(
            self.question, self.brief, self.plan_items,
            [finding], conflicts,
        )
        self.assertIn("争议地图", report)
        self.assertIn("分歧区", report)

    def test_report_backward_compatible_no_new_sections_without_data(self):
        """When there are no conflicts and no findings, new sections gracefully omitted."""
        report = build_research_report(
            self.question, self.brief, self.plan_items,
            [self._make_finding(1)], [],
        )
        # Executive summary is always present (uses rule fallback)
        self.assertIn("执行摘要", report)
        # Citation index may appear even for single finding
        self.assertIn("综合判断", report)
        self.assertIn("证据不足与后续建议", report)

    def test_executive_summary_fallback_works(self):
        """Executive summary fallback to overall_assessment when LLM unavailable."""
        report = build_research_report(
            self.question, self.brief, self.plan_items,
            [self._make_finding(1, verdict="CORRECT")], [],
        )
        self.assertIn("执行摘要", report)
        # Should contain fallback content from overall_assessment
        self.assertIn("综合判断", report)


if __name__ == "__main__":
    unittest.main()
