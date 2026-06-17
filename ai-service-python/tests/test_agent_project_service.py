import os
import tempfile
import unittest
from unittest.mock import patch

from schemas.requests import (
    AgentProjectCreateRequest,
    AgentProjectPapersRequest,
    AgentProjectUpdateRequest,
    AgentTaskCreateRequest,
)
from services import agent_project_service, trace_service


class _NoopThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon

    def start(self):
        return None


class AgentProjectPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("AGENT_STATE_DB_PATH")
        os.environ["AGENT_STATE_DB_PATH"] = os.path.join(self.temp_dir.name, "agent_state.sqlite3")
        agent_project_service.clear_agent_state(clear_storage=True)

    def tearDown(self):
        trace_service.clear_traces()
        agent_project_service.clear_agent_state(clear_storage=True)
        if self.previous_db_path is None:
            os.environ.pop("AGENT_STATE_DB_PATH", None)
        else:
            os.environ["AGENT_STATE_DB_PATH"] = self.previous_db_path
        self.temp_dir.cleanup()

    def _create_project(self):
        response = agent_project_service.create_agent_project(
            AgentProjectCreateRequest(
                title="Persistent Agent Project",
                goal="Compare project papers",
                paperIds=["paper-a", "paper-b"],
            )
        )
        return response["project"]

    def _create_task_without_worker(self, project_id):
        with patch("services.agent_project_service.threading.Thread", _NoopThread):
            response = agent_project_service.create_agent_task(
                project_id,
                AgentTaskCreateRequest(
                    prompt="Compare methods and evidence.",
                    focusedPaperIds=["paper-a", "paper-b"],
                    constraints="Use evidence first.",
                    context={"activePaperId": "paper-a"},
                ),
            )
        return response["task"]

    def test_project_updates_and_paper_changes_restore_from_sqlite(self):
        project = self._create_project()
        project_id = project["projectId"]

        agent_project_service.update_agent_project(
            project_id,
            AgentProjectUpdateRequest(
                title="Updated Agent Project",
                goal="Updated goal",
                defaultConstraints="Prefer method sections.",
            ),
        )
        agent_project_service.add_project_papers(project_id, AgentProjectPapersRequest(paperIds=["paper-c"]))
        agent_project_service.remove_project_paper(project_id, "paper-b")

        agent_project_service.reload_agent_state_from_storage()

        restored = agent_project_service.get_agent_project(project_id)["project"]
        self.assertEqual(restored["title"], "Updated Agent Project")
        self.assertEqual(restored["goal"], "Updated goal")
        self.assertEqual(restored["defaultConstraints"], "Prefer method sections.")
        self.assertEqual(restored["paperIds"], ["paper-a", "paper-c"])
        self.assertEqual([paper["pdfId"] for paper in restored["papers"]], ["paper-a", "paper-c"])
        self.assertEqual(agent_project_service.list_agent_projects()["projects"][0]["projectId"], project_id)

    def test_completed_task_outputs_and_latest_task_restore_from_sqlite(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 2, "sourceIds": ["source-a"], "preview": "method evidence", "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 1, "sourceIds": ["source-b"], "preview": "result evidence", "status": "succeeded"},
        ]
        tool_calls = [{"id": "retrieve-current-paper-1", "name": "retrieve_current_paper", "status": "succeeded", "target": "paper-a", "result": "Collected evidence."}]
        evidence_items = [
            {"sourceId": "source-a", "text": "Method evidence.", "pdfId": "paper-a", "sectionId": "method"},
            {"sourceId": "source-b", "text": "Result evidence.", "pdfId": "paper-b", "sectionId": "results"},
        ]

        with (
            patch.object(agent_project_service, "_agent_step_delay", return_value=None),
            patch.object(agent_project_service.agent_orchestrator, "collect_project_evidence", return_value=(paper_contexts, tool_calls, evidence_items)),
        ):
            agent_project_service._run_minimal_agent_task(task["taskId"])

        completed = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(completed["status"], "succeeded")
        self.assertTrue(completed["events"])
        self.assertTrue(completed["toolCalls"])
        self.assertTrue(completed["evidenceItems"])
        self.assertTrue(completed["findings"])
        self.assertTrue(completed["comparisonTable"]["columns"])
        self.assertTrue(completed["conflicts"])
        self.assertTrue(completed["openQuestions"])
        self.assertIn("# Agent Research Draft", completed["draftReport"])

        trace_service.clear_traces()
        agent_project_service.reload_agent_state_from_storage()

        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        latest = agent_project_service.get_latest_agent_task(project["projectId"])["task"]
        self.assertEqual(restored["status"], "succeeded")
        self.assertEqual(latest["taskId"], task["taskId"])
        self.assertEqual(restored["events"][-1]["type"], "task_completed")
        self.assertEqual(restored["toolCalls"], completed["toolCalls"])
        self.assertEqual(restored["evidenceItems"], completed["evidenceItems"])
        self.assertEqual(restored["findings"], completed["findings"])
        self.assertEqual(restored["comparisonTable"], completed["comparisonTable"])
        self.assertEqual(restored["conflicts"], completed["conflicts"])
        self.assertEqual(restored["openQuestions"], completed["openQuestions"])
        self.assertEqual(restored["draftReport"], completed["draftReport"])

    def test_cancelled_task_restores_with_cancel_event(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        cancelled = agent_project_service.cancel_agent_task(task["taskId"])["task"]
        self.assertEqual(cancelled["status"], "cancelled")

        agent_project_service.reload_agent_state_from_storage()

        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(restored["status"], "cancelled")
        self.assertEqual(restored["events"][-1]["type"], "task_cancelled")

    def test_running_task_is_marked_failed_after_restart(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        agent_project_service.reload_agent_state_from_storage()

        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        latest = agent_project_service.get_latest_agent_task(project["projectId"])["task"]
        self.assertEqual(restored["status"], "failed")
        self.assertEqual(restored["stage"], "done")
        self.assertEqual(restored["progress"], 1.0)
        self.assertEqual(restored["error"], "Agent task was interrupted by service restart.")
        self.assertEqual(restored["events"][-1]["type"], "task_expired")
        self.assertEqual(latest["taskId"], task["taskId"])

    def test_delete_project_removes_persisted_tasks_and_events(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        agent_project_service.delete_agent_project(project["projectId"])
        agent_project_service.reload_agent_state_from_storage()

        with self.assertRaises(agent_project_service.AgentProjectNotFoundError):
            agent_project_service.get_agent_project(project["projectId"])
        with self.assertRaises(agent_project_service.AgentTaskNotFoundError):
            agent_project_service.get_agent_task(task["taskId"])


if __name__ == "__main__":
    unittest.main()
