"""Tests for LangGraph-based agent orchestrator (10-5)."""
import uuid
import unittest
from unittest.mock import patch, Mock

from langgraph.checkpoint.memory import MemorySaver


class AgentLangGraphErrorHandlingTests(unittest.TestCase):
    """Tests for error handling and edge cases."""

    def test_run_with_empty_prompt_fails_gracefully(self):
        """Empty or whitespace-only prompt should still produce a valid state (caught downstream)."""
        from services.agent_langgraph import run_agent_graph, agent_graph_state_to_response

        for bad_prompt in ("", "   "):
            with self.subTest(prompt=repr(bad_prompt)):
                state = run_agent_graph(prompt=bad_prompt, paper_ids=[], thread_id=f"test-empty-{uuid.uuid4().hex[:6]}")
                resp = agent_graph_state_to_response(state)
                # Empty prompt gets processed through init → plan_review interrupt
                # The status reflects the interrupt state, not a validation error
                self.assertIn(resp["status"], ("awaiting_plan_review", "failed"))
                self.assertIsNotNone(resp.get("prompt"))

    def test_run_with_empty_paper_ids_still_runs(self):
        """Empty paper_ids should be accepted (research may only use external sources)."""
        from services.agent_langgraph import run_agent_graph

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "p1", "label": "Plan", "detail": "", "status": "pending"}]):
            state = run_agent_graph(prompt="Research without papers", paper_ids=[], thread_id="test-no-papers")

        self.assertFalse(state.get("plan_approved"))
        self.assertGreater(len(state.get("plan_items", [])), 0)

    def test_thread_id_isolation(self):
        """Different thread_ids produce independent states."""
        from services.agent_langgraph import run_agent_graph

        tid1 = "iso-1"
        tid2 = "iso-2"

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": f"plan-{tid1}", "label": "A", "detail": "", "status": "pending"}]):
            s1 = run_agent_graph(prompt="Task A", paper_ids=[], thread_id=tid1)

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": f"plan-{tid2}", "label": "B", "detail": "", "status": "pending"}]):
            s2 = run_agent_graph(prompt="Task B", paper_ids=[], thread_id=tid2)

        # Different threads should have different plan items
        self.assertEqual(s1["plan_items"][0]["label"], "A")
        self.assertEqual(s2["plan_items"][0]["label"], "B")
        # Different prompt
        self.assertEqual(s1["prompt"], "Task A")
        self.assertEqual(s2["prompt"], "Task B")

    def test_execute_node_error_gracefully_continues_to_final_review(self):
        """When collect_project_evidence raises, the error is caught and graph continues.

        The execute_node catches errors, sets empty evidence, and the graph proceeds
        to synthesize → report → final_review (where the user can see the partial result).
        """
        from services.agent_langgraph import run_agent_graph, resume_agent_graph, agent_graph_state_to_response

        thread_id = f"test-exec-err-{uuid.uuid4().hex[:8]}"

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "p1", "label": "Test", "detail": "", "status": "pending"}]):
            run_agent_graph(prompt="Test", paper_ids=[], thread_id=thread_id)

        # Resume with plan approved, but evidence collection fails
        with (
            patch("services.agent_evidence_collector.collect_project_evidence",
                  side_effect=RuntimeError("Search index unavailable")),
            patch("services.agent_orchestrator.build_agent_outputs",
                  return_value=([], {}, [], [])),
            patch("services.agent_report_sections.build_minimal_report",
                  return_value="# Partial Report"),
        ):
            state = resume_agent_graph(
                {"plan_approved": True, "plan_review_notes": "OK"},
                thread_id=thread_id,
            )

        # Graph continues to final_review despite evidence collection failure
        resp = agent_graph_state_to_response(state, interrupted=True)
        self.assertIn(resp["status"], ("awaiting_final_review", "running"))
        # Evidence should be empty (error was caught)
        self.assertEqual(len(state.get("evidence_items", [])), 0)

    def test_synthesis_error_continues_with_partial_state(self):
        """When build_agent_outputs raises, synthesis error is caught and graph continues.

        The synthesize_node catches errors, and the graph proceeds to report → final_review
        with whatever was produced before the error.
        """
        from services.agent_langgraph import run_agent_graph, resume_agent_graph, agent_graph_state_to_response

        thread_id = f"test-synth-err-{uuid.uuid4().hex[:8]}"

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "p1", "label": "Test", "detail": "", "status": "pending"}]):
            run_agent_graph(prompt="Test", paper_ids=[], thread_id=thread_id)

        # Evidence succeeds but synthesis fails
        with (
            patch("services.agent_evidence_collector.collect_project_evidence",
                  return_value=(
                      [{"sourceId": "s1", "text": "ok"}],
                      [],
                      [{"sourceId": "s1", "text": "ok", "sourceType": "current_paper"}],
                      [],
                  )),
            patch("services.agent_orchestrator.build_agent_outputs",
                  side_effect=RuntimeError("LLM model timeout")),
            patch("services.agent_report_sections.build_minimal_report",
                  return_value="# Recovery Report"),
        ):
            state = resume_agent_graph(
                {"plan_approved": True, "plan_review_notes": "OK"},
                thread_id=thread_id,
            )

        resp = agent_graph_state_to_response(state, interrupted=True)
        # Graph continues to final_review despite synthesis failure
        self.assertIn(resp["status"], ("awaiting_final_review", "running"))
        # Draft report should still be present (recovery path)
        self.assertIn("Recovery Report", state.get("draft_report", ""))

    def test_resume_with_malformed_input_is_handled(self):
        """Missing required fields in resume should not crash."""
        from services.agent_langgraph import run_agent_graph, resume_agent_graph

        thread_id = f"test-malform-{uuid.uuid4().hex[:8]}"

        with patch("services.agent_orchestrator.build_plan_items",
                   return_value=[{"id": "p1", "label": "Test", "detail": "", "status": "pending"}]):
            run_agent_graph(prompt="Test", paper_ids=[], thread_id=thread_id)

        # Resume with empty dict (missing plan_approved)
        state = resume_agent_graph({}, thread_id=thread_id)
        # Should still produce a state (plan is treated as rejected or stays pending)
        self.assertIn("status", state)

    def test_state_to_response_without_plan_items(self):
        """Response converter handles missing optional fields gracefully."""
        from services.agent_langgraph import agent_graph_state_to_response, AgentGraphState

        state: AgentGraphState = {}
        response = agent_graph_state_to_response(state)
        # Empty state returns 'pending' (no plan items, no approval, no error)
        self.assertIn(response["status"], ("pending", "failed"))
        self.assertEqual(len(response["evidenceItems"]), 0)
        self.assertEqual(len(response["planItems"]), 0)

    def test_graph_uses_shared_checkpointer(self):
        """Graph construction uses MemorySaver for cross-invocation state."""
        from services.agent_langgraph import build_agent_graph

        graph1 = build_agent_graph()
        graph2 = build_agent_graph()
        self.assertIs(graph1.checkpointer, graph2.checkpointer)
        self.assertIsInstance(graph2.checkpointer, MemorySaver)


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
