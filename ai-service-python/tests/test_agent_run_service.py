import unittest

from services.agent_run_service import (
    ALLOWED_RUN_TRANSITIONS,
    AgentRunStateError,
    transition_run_status,
)


class AgentRunServiceTests(unittest.TestCase):
    def test_transition_run_status_allows_happy_path(self):
        run = {"runId": "run-1", "status": "draft", "executionPhase": ""}

        run = transition_run_status(run, "awaiting_plan_review")
        self.assertEqual(run["status"], "awaiting_plan_review")

        run = transition_run_status(run, "queued")
        self.assertEqual(run["status"], "queued")

        run = transition_run_status(
            run,
            "running",
            execution_phase="retrieving_evidence",
        )
        self.assertEqual(run["status"], "running")
        self.assertEqual(run["executionPhase"], "retrieving_evidence")

        run = transition_run_status(run, "awaiting_final_review")
        self.assertEqual(run["status"], "awaiting_final_review")
        self.assertEqual(run["executionPhase"], "")

        run = transition_run_status(run, "completed")
        self.assertEqual(run["status"], "completed")

    def test_transition_run_status_rejects_illegal_jump(self):
        run = {"runId": "run-2", "status": "awaiting_plan_review", "executionPhase": ""}

        with self.assertRaises(AgentRunStateError) as context:
            transition_run_status(run, "completed")

        self.assertIn("Illegal Agent run transition", str(context.exception))

    def test_allowed_transition_table_is_explicit(self):
        self.assertEqual(ALLOWED_RUN_TRANSITIONS["draft"], {"awaiting_plan_review"})
        self.assertNotIn("completed", ALLOWED_RUN_TRANSITIONS["awaiting_plan_review"])
