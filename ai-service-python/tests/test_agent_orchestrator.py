import unittest
from unittest.mock import Mock, patch

from services import trace_service
from services.agent_orchestrator import (
    build_agent_outputs,
    build_minimal_report,
    build_plan_items,
    collect_project_evidence,
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

        with patch("services.agent_orchestrator.get_tool_registry", return_value=fake_registry):
            paper_contexts, tool_calls, evidence_items = collect_project_evidence(
                prompt="compare methods",
                paper_ids=["paper-a"],
            )

        snapshot = trace_service.get_trace_snapshot(trace_service.get_current_trace_id())
        self.assertEqual(snapshot["counters"]["retrievalCalls"], 1)
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

        with patch("services.agent_orchestrator.get_tool_registry", return_value=fake_registry):
            paper_contexts, tool_calls, evidence_items = collect_project_evidence(
                prompt="compare methods",
                paper_ids=["paper-a"],
            )

        self.assertEqual(paper_contexts[0]["status"], "fallback")
        self.assertEqual(tool_calls[0]["status"], "fallback")
        self.assertEqual(tool_calls[0]["version"], "1.0.0")
        self.assertEqual(tool_calls[0]["safetyScope"]["access"], "read_only")
        self.assertIn("Collected 1 evidence items", tool_calls[0]["result"])
        self.assertTrue(evidence_items[0]["metadata"]["fallback"])

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
        self.assertTrue(open_questions)
        self.assertIn("# Agent Research Draft", report)
        self.assertIn("## Conflict Candidates", report)
        self.assertIn("paper-a", report)


if __name__ == "__main__":
    unittest.main()
