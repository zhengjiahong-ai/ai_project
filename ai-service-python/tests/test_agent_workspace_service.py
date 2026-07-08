import unittest

from services.agent_workspace_service import build_workspace_view


class AgentWorkspaceServiceTests(unittest.TestCase):
    def test_build_workspace_view_joins_project_run_review_artifacts_and_timeline(self):
        workspace = build_workspace_view(
            project={"projectId": "project-1", "title": "Project"},
            active_run={"runId": "run-1", "status": "awaiting_plan_review"},
            pending_review={"runId": "run-1", "status": "pending"},
            latest_artifacts={"runId": "run-1", "findings": []},
            recent_runs=[{"runId": "run-1", "status": "awaiting_plan_review"}],
            timeline=[{"id": "entry-1", "type": "plan_prepared"}],
        )

        self.assertEqual(workspace["project"]["projectId"], "project-1")
        self.assertEqual(workspace["activeRun"]["runId"], "run-1")
        self.assertEqual(workspace["pendingReview"]["status"], "pending")
        self.assertEqual(workspace["timeline"][0]["type"], "plan_prepared")
