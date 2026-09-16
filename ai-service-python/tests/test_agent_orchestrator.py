import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import trace_service
from services.agent_evidence_collector import (
    build_external_search_queries,
    collect_project_evidence,
)
from services.agent_orchestrator import (
    build_agent_outputs,
    build_code_execution_proposal,
    build_plan_items,
    build_review_plan_items,
    execute_run,
)
from services.agent_report_sections import build_minimal_report
from services.agent_evidence_collector import (
    retrieve_external_agent_evidence,
    should_try_external_search,
)


ADVERSARIAL_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "external_search_adversarial.json").read_text(encoding="utf-8")
)


class AgentOrchestratorTests(unittest.TestCase):
    def tearDown(self):
        trace_service.clear_traces()

    def test_build_plan_items_tracks_three_stage_statuses(self):
        retrieve_plan = build_plan_items(["paper-a", "paper-b"], active_step="retrieve")
        self.assertEqual([item["id"] for item in retrieve_plan], ["scope", "retrieve", "synthesize"])
        self.assertEqual([item["status"] for item in retrieve_plan], ["done", "running", "pending"])
        self.assertIn("2 project papers", retrieve_plan[1]["detail"])

        done_plan = build_plan_items(["paper-a"], active_step="done")
        self.assertEqual([item["status"] for item in done_plan], ["done", "done", "done"])

    def test_collect_project_evidence_records_tool_calls_and_preserves_source_metadata(self):
        trace_service.start_trace("agent_research")
        fake_registry = Mock()
        fake_registry.get.return_value.version = "1.0.0"
        fake_registry.get.return_value.safetyScope = {
            "access": "read_only",
            "dataScopes": ["current_paper"],
            "networkAccess": False,
            "sideEffects": False,
            "sensitiveOutput": True,
        }
        fake_registry.invoke.return_value = {
            "items": [
                {
                    "sourceId": "source-1",
                    "text": "Method evidence for paper A.",
                    "pdfId": "paper-a",
                    "pageIndex": 2,
                    "sectionId": "method",
                    "chunkIndex": 7,
                }
            ]
        }

        with patch("services.agent_evidence_collector._get_tool_registry", return_value=fake_registry):
            paper_contexts, tool_calls, evidence_items, _timeline = collect_project_evidence(
                prompt="compare methods",
                paper_ids=["paper-a"],
            )

        snapshot = trace_service.get_trace_snapshot(trace_service.get_current_trace_id())
        self.assertEqual(snapshot["counters"]["retrievalCalls"], 3)
        self.assertEqual(paper_contexts[0]["pdfId"], "paper-a")
        self.assertEqual(tool_calls[0]["status"], "succeeded")
        self.assertEqual(tool_calls[0]["version"], "1.0.0")
        self.assertEqual(tool_calls[0]["safetyScope"]["access"], "read_only")
        self.assertEqual(tool_calls[0]["result"], "Collected 1 evidence items for paper-a.")
        self.assertEqual(evidence_items[0]["sourceId"], "source-1")
        self.assertEqual(evidence_items[0]["pdfId"], "paper-a")
        self.assertEqual(evidence_items[0]["pageIndex"], 2)
        self.assertEqual(evidence_items[0]["sectionId"], "method")
        self.assertEqual(evidence_items[0]["chunkIndex"], 7)
        self.assertEqual(fake_registry.invoke.call_count, 3)
        queries = [call.args[1]["query"] for call in fake_registry.invoke.call_args_list]
        self.assertTrue(any("method architecture" in query for query in queries))
        self.assertTrue(any("quantitative results" in query for query in queries))
        self.assertTrue(any("limitations" in query for query in queries))

    def test_chinese_question_uses_english_aspect_queries_for_english_papers(self):
        from services.agent_evidence_collector import _build_project_evidence_queries

        queries = _build_project_evidence_queries("比较两篇论文的方法、实验和局限")

        self.assertEqual(len(queries), 3)
        self.assertTrue(all("论文" not in query for query in queries))
        self.assertIn("deformation training strategy", queries[0])
        self.assertIn("quantitative results", queries[1])
        self.assertIn("future work", queries[2])

    def test_collect_project_evidence_uses_fallback_tool_summary(self):
        trace_service.start_trace("agent_research")
        fake_registry = Mock()
        fake_registry.get.return_value.version = "1.0.0"
        fake_registry.get.return_value.safetyScope = {
            "access": "read_only",
            "dataScopes": ["current_paper"],
            "networkAccess": False,
            "sideEffects": False,
            "sensitiveOutput": True,
        }
        fake_registry.invoke.side_effect = RuntimeError("index unavailable")

        with patch("services.agent_evidence_collector._get_tool_registry", return_value=fake_registry):
            paper_contexts, tool_calls, evidence_items, _timeline = collect_project_evidence(
                prompt="compare methods",
                paper_ids=["paper-a"],
            )

        self.assertEqual(paper_contexts[0]["status"], "fallback")
        self.assertEqual(tool_calls[0]["status"], "fallback")
        self.assertEqual(tool_calls[0]["version"], "1.0.0")
        self.assertEqual(tool_calls[0]["safetyScope"]["access"], "read_only")
        self.assertIn("Collected 0 evidence items", tool_calls[0]["result"])
        self.assertEqual(evidence_items, [])
        self.assertEqual(paper_contexts[0]["evidenceCount"], 0)

    def test_build_agent_outputs_and_report_are_stable(self):
        paper_contexts = [
            {
                "pdfId": "paper-a",
                "evidenceCount": 3,
                "sourceIds": ["a-1"],
                "preview": "method evidence",
                "status": "succeeded",
            },
            {
                "pdfId": "paper-b",
                "evidenceCount": 0,
                "sourceIds": [],
                "preview": "",
                "status": "fallback",
            },
        ]
        evidence_items = [
            {
                "sourceId": "a-1",
                "text": "The method improves retrieval quality.",
                "pdfId": "paper-a",
                "sectionId": "method",
            },
            {
                "sourceId": "b-1",
                "text": "Fallback project evidence placeholder for paper-b.",
                "pdfId": "paper-b",
                "sectionId": "unknown",
                "metadata": {"fallback": True},
            },
        ]

        finding, comparison_table, conflicts, open_questions = build_agent_outputs(
            "compare methods",
            paper_contexts,
            evidence_items,
        )
        report = build_minimal_report(
            "compare methods",
            {"title": "Project A"},
            paper_contexts,
            evidence_items,
            conflicts,
            open_questions,
        )

        self.assertEqual(finding["id"], "project-synthesis-1")
        self.assertEqual(comparison_table["columns"][0], "paperId")
        self.assertEqual(len(comparison_table["rows"]), 2)
        self.assertEqual(conflicts[0]["id"], "evidence-coverage-conflict")
        self.assertIn("graphContext", conflicts[0])
        self.assertTrue(open_questions)
        self.assertIn("# Agent Research Draft", report)
        self.assertIn("## Conflict Candidates", report)
        self.assertIn("Graph context", report)
        self.assertIn("not automatically adjudicated", report)
        self.assertIn("paper-a", report)

    def test_execute_run_returns_execution_result_shape(self):
        paper_contexts = [
            {
                "pdfId": "paper-a",
                "evidenceCount": 2,
                "sourceIds": ["a-1"],
                "preview": "method evidence",
                "status": "succeeded",
            }
        ]
        tool_calls = [{"name": "retrieve_current_paper", "status": "succeeded"}]
        evidence_items = [
            {
                "sourceId": "a-1",
                "text": "Method evidence for paper-a.",
                "pdfId": "paper-a",
                "sectionId": "method",
            }
        ]

        with patch(
            "services.agent_orchestrator.collect_project_evidence",
            return_value=(paper_contexts, tool_calls, evidence_items, []),
        ):
            result = execute_run("compare methods", ["paper-a"])

        self.assertEqual(result["paperContexts"], paper_contexts)
        self.assertEqual(result["toolCalls"], tool_calls)
        self.assertEqual(result["researchTimeline"], [])
        self.assertEqual(result["artifacts"]["evidenceItems"], evidence_items)
        self.assertTrue(result["artifacts"]["findings"])
        self.assertIn("# Agent Research Draft", result["artifacts"]["draftReport"])


    def test_should_try_external_search_returns_false_when_disabled(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 1, "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 0, "status": "fallback"},
        ]
        self.assertFalse(should_try_external_search(paper_contexts, allow_external_search=False))

    def test_should_try_external_search_returns_false_when_evidence_dense(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 3, "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 2, "status": "succeeded"},
        ]
        self.assertFalse(should_try_external_search(paper_contexts, allow_external_search=True))

    def test_should_try_external_search_returns_true_when_sparse_and_allowed(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 3, "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 1, "status": "succeeded"},
        ]
        self.assertTrue(should_try_external_search(paper_contexts, allow_external_search=True))

    def test_should_try_external_search_returns_true_when_fallback_and_allowed(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 2, "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 1, "status": "fallback"},
        ]
        self.assertTrue(should_try_external_search(paper_contexts, allow_external_search=True))

    def test_build_external_search_queries_generates_from_gaps(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 3, "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 0, "status": "fallback"},
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
        ]
        queries = build_external_search_queries(
            prompt="compare training methods for image classification",
            paper_contexts=paper_contexts,
            evidence_items=evidence_items,
        )
        self.assertIsInstance(queries, list)
        self.assertGreater(len(queries), 0)
        self.assertLessEqual(len(queries), 5)
        for query in queries:
            self.assertLessEqual(len(query), 256)
            self.assertNotIn("http", query)

    def test_collect_project_evidence_skips_external_when_disabled(self):
        trace_service.start_trace("agent_research")
        fake_registry = Mock()
        fake_registry.get.return_value.version = "1.0.0"
        fake_registry.get.return_value.safetyScope = {
            "access": "read_only",
            "dataScopes": ["current_paper"],
            "networkAccess": False,
            "sideEffects": False,
            "sensitiveOutput": True,
        }
        fake_registry.invoke.return_value = {"items": []}

        with patch("services.agent_evidence_collector._get_tool_registry", return_value=fake_registry):
            paper_contexts, tool_calls, evidence_items, _timeline = collect_project_evidence(
                prompt=ADVERSARIAL_FIXTURE["queryCases"][0]["input"],
                paper_ids=["paper-a"],
                allow_external_search=False,
            )

        self.assertEqual(len(paper_contexts), 1)
        self.assertEqual(paper_contexts[0]["pdfId"], "paper-a")
        self.assertEqual(paper_contexts[0]["status"], "succeeded")
        tool_names = [tc["name"] for tc in tool_calls]
        self.assertNotIn("retrieve_external_academic", tool_names)

    def test_external_tool_failure_is_sanitized_and_preserves_safety_scope(self):
        secret = ADVERSARIAL_FIXTURE["secretToken"]
        fake_registry = Mock()
        fake_registry.get.return_value.version = "1.0.0"
        fake_registry.get.return_value.safetyScope = {
            "access": "read_only",
            "dataScopes": ["external_academic_metadata"],
            "networkAccess": True,
            "sideEffects": False,
            "sensitiveOutput": True,
        }
        fake_registry.invoke.side_effect = RuntimeError(
            f"provider response contained credential {secret}"
        )

        with patch("services.agent_evidence_collector._get_tool_registry", return_value=fake_registry):
            result = retrieve_external_agent_evidence(["retrieval robustness"])

        serialized = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["degradation"], "External academic provider failed.")
        self.assertNotIn(secret, serialized)
        self.assertEqual(result["external_tool_calls"][0]["version"], "1.0.0")
        self.assertEqual(
            result["external_tool_calls"][0]["safetyScope"]["dataScopes"],
            ["external_academic_metadata"],
        )

    def test_collect_project_evidence_includes_external_when_allowed_with_sparse_evidence(self):
        trace_service.start_trace("agent_research")
        fake_registry = Mock()
        fake_registry.get.return_value.version = "1.0.0"
        fake_registry.get.return_value.safetyScope = {
            "access": "read_only",
            "dataScopes": ["current_paper", "external_academic_metadata"],
            "networkAccess": True,
            "sideEffects": False,
            "sensitiveOutput": True,
        }

        call_count = [0]

        def fake_invoke(name, payload):
            if name == "retrieve_current_paper":
                call_count[0] += 1
                if call_count[0] == 1:
                    return {"items": []}
                return {"items": [
                    {"sourceId": "b-1", "text": "result evidence", "pdfId": "paper-b", "sectionId": "results"},
                ]}
            if name == "retrieve_external_academic":
                return {
                    "status": "success",
                    "provider": "crossref",
                    "items": [
                        {
                            "sourceId": "external-doi-abc123",
                            "sourceType": "external_academic",
                            "provider": "crossref",
                            "title": "External Evidence Paper",
                            "authors": ["Author One"],
                            "year": 2024,
                            "abstract": "External abstract.",
                            "doi": "10.1234/abc123",
                            "url": "https://doi.org/10.1234/abc123",
                            "retrievedAt": "2025-01-01T00:00:00Z",
                            "query": "compare methods",
                            "license": "",
                        }
                    ],
                    "reason": "",
                }
            return {}

        fake_registry.invoke.side_effect = fake_invoke

        with patch("services.agent_evidence_collector._get_tool_registry", return_value=fake_registry):
            paper_contexts, tool_calls, evidence_items, _timeline = collect_project_evidence(
                prompt="compare methods",
                paper_ids=["paper-a", "paper-b"],
                allow_external_search=True,
            )

        self.assertEqual(len(paper_contexts), 2)
        tool_names = [tc["name"] for tc in tool_calls]
        self.assertIn("retrieve_external_academic", tool_names)
        external_sources = [ei for ei in evidence_items if ei.get("sourceType") == "external_academic"]
        self.assertGreater(len(external_sources), 0)
        self.assertEqual(external_sources[0]["provider"], "crossref")
        self.assertEqual(external_sources[0]["doi"], "10.1234/abc123")

    def test_report_distinguishes_external_sources(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 2, "sourceIds": ["a-1"], "preview": "method evidence", "status": "succeeded"},
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
            {
                "sourceId": "external-doi-abc123",
                "sourceType": "external_academic",
                "provider": "crossref",
                "title": "External Title",
                "authors": ["Author One"],
                "year": 2024,
                "doi": "10.1234/abc123",
                "url": "https://doi.org/10.1234/abc123",
                "retrievedAt": "2025-01-01T00:00:00Z",
                "query": "compare methods",
            },
        ]
        conflicts = [
            {
                "id": "no-major-conflict",
                "severity": "low",
                "claim": "No major conflict.",
                "papers": ["paper-a"],
                "summary": "No conflict detected.",
                "sourceIds": ["a-1"],
                "resolutionHint": "Continue.",
            }
        ]
        open_questions = ["Need more evidence."]

        report = build_minimal_report(
            prompt="compare methods",
            project={"title": "Project A"},
            paper_contexts=paper_contexts,
            evidence_items=evidence_items,
            conflicts=conflicts,
            open_questions=open_questions,
        )

        self.assertIn("# Agent Research Draft", report)
        self.assertIn("## External Academic Evidence", report)
        self.assertIn("crossref", report)
        self.assertIn("External Title", report)
        self.assertIn("10.1234/abc123", report)
        self.assertIn("（含外部学术检索）", report)

    def test_build_agent_outputs_includes_external_evidence_count(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 2, "sourceIds": ["a-1"], "preview": "method", "status": "succeeded"},
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
            {
                "sourceId": "external-doi-abc123",
                "sourceType": "external_academic",
                "provider": "crossref",
                "title": "External Title",
                "authors": ["Author One"],
                "year": 2024,
                "doi": "10.1234/abc123",
            },
        ]

        finding, comparison_table, conflicts, open_questions = build_agent_outputs(
            "compare methods",
            paper_contexts,
            evidence_items,
        )

        self.assertIn("externalEvidenceCount", finding)
        self.assertEqual(finding["externalEvidenceCount"], 1)
        self.assertIn("external-doi-abc123", finding["sourceIds"])

    def test_build_code_execution_proposal_produces_valid_structure(self):
        proposal = build_code_execution_proposal("artifact-abc123", "Test analysis of CSV data.")

        self.assertIn("artifactId", proposal)
        self.assertEqual(proposal["artifactId"], "artifact-abc123")
        self.assertIn("description", proposal)
        self.assertEqual(proposal["templateId"], "descriptive-statistics-v1")
        self.assertIn("createdAt", proposal)
        self.assertEqual(proposal["description"], "Test analysis of CSV data.")

    def test_build_code_execution_proposal_truncates_long_description(self):
        proposal = build_code_execution_proposal("artifact-x", "a" * 500)

        self.assertEqual(proposal["artifactId"], "artifact-x")
        self.assertLessEqual(len(proposal["description"]), 300)

    def test_build_review_plan_items_includes_code_execution_field(self):
        items = build_review_plan_items("compare methods", ["paper-a", "paper-b"])

        experiment_items = [item for item in items if item.get("id") == "experiment"]
        self.assertEqual(len(experiment_items), 1)
        experiment = experiment_items[0]
        self.assertIn("allowCodeExecution", experiment)
        self.assertFalse(experiment["allowCodeExecution"])
        self.assertEqual(experiment["label"], "Code execution experiment")

    def test_build_minimal_report_includes_code_artifacts_section(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 2, "sourceIds": ["a-1"], "preview": "method", "status": "succeeded"},
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
        ]
        conflicts = [
            {"id": "no-major-conflict", "severity": "low", "claim": "No conflict.",
             "papers": ["paper-a"], "summary": "No conflict.", "sourceIds": ["a-1"], "resolutionHint": "Continue."}
        ]
        open_questions = ["Need more evidence."]
        code_execution_results = [
            {"artifactId": "artifact-abc", "jobId": "job-test", "rowCount": 150, "columns": 8}
        ]

        report = build_minimal_report(
            prompt="compare methods",
            project={"title": "Project A"},
            paper_contexts=paper_contexts,
            evidence_items=evidence_items,
            conflicts=conflicts,
            open_questions=open_questions,
            code_execution_results=code_execution_results,
        )

        self.assertIn("## Code-Computed Artifacts", report)
        self.assertIn("artifact-abc", report)
        self.assertIn("job-test", report)

    def test_build_minimal_report_no_code_section_when_no_results(self):
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 2, "sourceIds": ["a-1"], "preview": "method", "status": "succeeded"},
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
        ]
        conflicts = [
            {"id": "no-major-conflict", "severity": "low", "claim": "No conflict.",
             "papers": ["paper-a"], "summary": "No conflict.", "sourceIds": ["a-1"], "resolutionHint": "Continue."}
        ]
        open_questions = ["Need more evidence."]

        report = build_minimal_report(
            prompt="compare methods",
            project={"title": "Project A"},
            paper_contexts=paper_contexts,
            evidence_items=evidence_items,
            conflicts=conflicts,
            open_questions=open_questions,
        )

        self.assertNotIn("## Code-Computed Artifacts", report)


if __name__ == "__main__":
    unittest.main()
