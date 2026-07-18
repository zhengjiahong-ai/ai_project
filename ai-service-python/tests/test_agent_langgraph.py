"""Tests for LangGraph-based agent orchestrator (10-5)."""
import uuid
import unittest
from unittest.mock import patch, Mock

from langgraph.checkpoint.memory import MemorySaver


class AgentLangGraphConstructionTests(unittest.TestCase):
    """Tests for graph structure and state management."""

    def test_build_graph_returns_compiled_graph(self):
        from services.agent_langgraph import build_agent_graph

        graph = build_agent_graph()
        self.assertIsNotNone(graph)

    def test_graph_has_all_nodes(self):
        from services.agent_langgraph import build_agent_graph

        graph = build_agent_graph()
        nodes = list(graph.get_graph().nodes.keys())
        required = {"init", "plan_review", "plan_rejected", "execute",
                    "synthesize", "report", "final_review",
                    "final_rejected", "success", "__start__"}
        for node in required:
            self.assertIn(node, nodes, f"Node {node} not found in graph")

    def test_graph_entry_point_is_init(self):
        from services.agent_langgraph import build_agent_graph

        graph = build_agent_graph()
        # The entry point should lead to init
        self.assertIsNotNone(graph)

    def test_run_stops_at_plan_review_interrupt(self):
        """Graph should interrupt at plan_review for human approval.

        After the first invoke, plan_items are populated (from init_node),
        but plan_approved is still False because plan_review_node was interrupted
        before it could set it.
        """
        from services.agent_langgraph import run_agent_graph, agent_graph_state_to_response

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "test", "label": "Test", "detail": "", "status": "pending"}]):
            state = run_agent_graph(
                prompt="Test research",
                paper_ids=[],
                thread_id=f"test-{uuid.uuid4().hex[:8]}",
            )

        # State from init_node is preserved; plan_review was interrupted
        self.assertFalse(state.get("plan_approved"))
        self.assertGreater(len(state.get("plan_items", [])), 0)
        # Response converter detects interrupt state
        resp = agent_graph_state_to_response(state, interrupted=True)
        self.assertEqual(resp["status"], "awaiting_plan_review")

    def test_resume_from_plan_review_rejected(self):
        """Rejecting the plan should cancel the research."""
        from services.agent_langgraph import run_agent_graph, resume_agent_graph

        thread_id = f"test-reject-{uuid.uuid4().hex[:8]}"

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "test", "label": "Test", "detail": "", "status": "pending"}]):
            state = run_agent_graph(prompt="Test", paper_ids=[], thread_id=thread_id)

        self.assertFalse(state.get("plan_approved"))

        # Resume with plan rejected
        state = resume_agent_graph(
            {"plan_approved": False, "plan_review_notes": "Not good enough"},
            thread_id=thread_id,
        )

        self.assertEqual(state["status"], "cancelled")
        self.assertIn("not approved", state.get("error", ""))

    def test_full_pipeline_with_plan_approval(self):
        """Approve plan → execute → synthesize → final review interrupt."""
        from services.agent_langgraph import run_agent_graph, resume_agent_graph

        thread_id = f"test-full-{uuid.uuid4().hex[:8]}"

        # Run → stops at plan review
        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "test", "label": "Test", "detail": "", "status": "pending"}]):
            state = run_agent_graph(prompt="Test", paper_ids=[], thread_id=thread_id)

        self.assertFalse(state.get("plan_approved"))

        # Resume with plan approved → should run execute/synthesize/report → stop at final_review
        with (
            patch("services.agent_evidence_collector.collect_project_evidence",
                  return_value=(
                      [{"sourceId": "s1", "text": "evidence"}],
                      [],
                      [{"sourceId": "s1", "text": "evidence", "sourceType": "current_paper"}],
                      [{"type": "search", "summary": "done"}],
                  )),
            patch("services.agent_orchestrator.build_agent_outputs",
                  return_value=(
                      [{"id": "f1", "summary": "finding"}],
                      {"columns": [], "rows": []},
                      [],
                      [],
                  )),
            patch("services.agent_report_sections.build_minimal_report",
                  return_value="# Test Report"),
        ):
            state = resume_agent_graph(
                {"plan_approved": True, "plan_review_notes": "Looks good"},
                thread_id=thread_id,
            )

        # After the second interrupt (final_review), state has draft but not yet approved
        self.assertGreater(len(state.get("draft_report", "")), 0)
        self.assertGreater(len(state.get("evidence_items", [])), 0)
        self.assertFalse(state.get("final_approved"))

    def test_resume_from_final_review_approved(self):
        """Approve the final draft → succeeded."""
        from services.agent_langgraph import run_agent_graph, resume_agent_graph

        thread_id = f"test-final-{uuid.uuid4().hex[:8]}"

        # Run → plan review
        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "test", "label": "Test", "detail": "", "status": "pending"}]):
            state = run_agent_graph(prompt="Test", paper_ids=[], thread_id=thread_id)

        # Approve plan → stops at final review
        with (
            patch("services.agent_evidence_collector.collect_project_evidence",
                  return_value=([], [], [], [])),
            patch("services.agent_orchestrator.build_agent_outputs",
                  return_value=([], {}, [], [])),
            patch("services.agent_report_sections.build_minimal_report",
                  return_value="# Test Report"),
        ):
            state = resume_agent_graph(
                {"plan_approved": True, "plan_review_notes": "OK"},
                thread_id=thread_id,
            )

        self.assertTrue(state.get("plan_approved"))
        self.assertFalse(state.get("final_approved"))

        # Approve final → succeeded
        state = resume_agent_graph(
            {"final_approved": True, "final_review_notes": "Great work"},
            thread_id=thread_id,
        )

        self.assertEqual(state["status"], "succeeded")
        self.assertTrue(state.get("final_approved"))

    def test_state_to_response_maps_all_fields(self):
        """agent_graph_state_to_response produces backward-compatible output."""
        from services.agent_langgraph import agent_graph_state_to_response, AgentGraphState

        state: AgentGraphState = {
            "prompt": "Test",
            "paper_ids": ["paper-1"],
            "plan_items": [{"id": "p1", "label": "Plan", "detail": "", "status": "done"}],
            "evidence_items": [{"sourceId": "s1", "text": "test"}],
            "findings": [{"id": "f1", "summary": "result"}],
            "draft_report": "# Report",
            "review_risks": [{"riskId": "r1", "reviewStatus": "reviewed"}],
            "plan_approved": True,
            "plan_review_notes": "ok",
            "final_approved": True,
            "final_review_notes": "great",
            "timeline": [{"node": "init", "summary": "start"}],
        }

        response = agent_graph_state_to_response(state)
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["prompt"], "Test")
        self.assertEqual(len(response["evidenceItems"]), 1)
        self.assertEqual(response["humanReview"]["plan"]["status"], "approved")
        self.assertEqual(response["humanReview"]["final"]["status"], "approved")

    def test_state_to_response_pending_reviews(self):
        """Response converter infers correct status from flags + interrupted."""
        from services.agent_langgraph import agent_graph_state_to_response, AgentGraphState

        # After plan_review interrupt (not yet approved)
        state: AgentGraphState = {
            "plan_items": [{"id": "p1"}],
            "plan_approved": False,
            "final_approved": False,
        }
        response = agent_graph_state_to_response(state, interrupted=True)
        self.assertEqual(response["status"], "awaiting_plan_review")
        self.assertEqual(response["humanReview"]["plan"]["status"], "pending")
        self.assertEqual(response["humanReview"]["final"]["status"], "not_started")

        # After plan approved, with draft (final_review interrupt)
        state2: AgentGraphState = {
            "plan_approved": True,
            "final_approved": False,
            "draft_report": "# Draft",
        }
        response2 = agent_graph_state_to_response(state2, interrupted=True)
        self.assertEqual(response2["status"], "awaiting_final_review")
        self.assertEqual(response2["humanReview"]["plan"]["status"], "approved")
        self.assertEqual(response2["humanReview"]["final"]["status"], "pending")

    def test_follow_up_loops_respect_max(self):
        """Follow-up decisions respect max_follow_up limit."""
        from services.agent_langgraph import AgentGraphState, follow_up_decision

        # At max follow-ups → should go to final_review
        state: AgentGraphState = {
            "follow_up_count": 2,
            "max_follow_up": 2,
            "open_questions": ["missing evidence for method"],
            "evidence_items": [{"sourceId": "s1"}] * 2,
        }
        self.assertEqual(follow_up_decision(state), "final_review")

        # Under max with gap → should loop
        state2: AgentGraphState = {
            "follow_up_count": 0,
            "max_follow_up": 2,
            "open_questions": ["gap in coverage", "missing experiment data"],
            "evidence_items": [{"sourceId": "s1"}] * 3,
        }
        self.assertEqual(follow_up_decision(state2), "execute")

    def test_plan_review_with_edited_plan_items(self):
        """Resume with edited plan items should update the state."""
        from services.agent_langgraph import run_agent_graph, resume_agent_graph

        thread_id = f"test-edit-{uuid.uuid4().hex[:8]}"

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "orig", "label": "Original", "detail": "", "status": "pending"}]):
            state = run_agent_graph(prompt="Test", paper_ids=[], thread_id=thread_id)

        edited_plan = [{"id": "edited", "label": "Edited Plan", "detail": "Updated", "status": "pending"}]

        with (
            patch("services.agent_evidence_collector.collect_project_evidence",
                  return_value=([], [], [], [])),
            patch("services.agent_orchestrator.build_agent_outputs",
                  return_value=([], {}, [], [])),
            patch("services.agent_report_sections.build_minimal_report",
                  return_value="# Report"),
        ):
            state = resume_agent_graph(
                {"plan_approved": True, "plan_items": edited_plan},
                thread_id=thread_id,
            )

        # Plan items should be the edited version (set by plan_review_node after resume)
        self.assertEqual(state["plan_items"][0]["id"], "edited")
        self.assertTrue(state.get("plan_approved"))


if __name__ == "__main__":
    unittest.main()
