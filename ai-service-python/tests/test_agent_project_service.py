import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from schemas.requests import (
    AgentProjectCreateRequest,
    AgentProjectPapersRequest,
    AgentProjectUpdateRequest,
    AgentRunCreateRequest,
    AgentRunFinalReviewRequest,
    AgentRunPlanReviewRequest,
    AgentTaskCreateRequest,
    AgentFinalReviewRequest,
    AgentPlanReviewRequest,
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

    def _create_task_without_worker(self, project_id, allow_external_search=False):
        with patch("services.agent_project_service.threading.Thread", _NoopThread):
            response = agent_project_service.create_agent_task(
                project_id,
                AgentTaskCreateRequest(
                    prompt="Compare methods and evidence.",
                    focusedPaperIds=["paper-a", "paper-b"],
                    constraints="Use evidence first.",
                    context={"activePaperId": "paper-a"},
                    allowExternalSearch=allow_external_search,
                ),
            )
        return response["task"]

    def test_agent_task_requires_plan_and_final_review(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        with patch.object(agent_project_service, "_start_agent_worker"):
            planned = agent_project_service.prepare_agent_task_now(task["taskId"])
            self.assertEqual(planned["status"], "awaiting_plan_review")
            approved = agent_project_service.review_agent_plan(
                task["taskId"],
                AgentPlanReviewRequest(
                    planItems=[{"id": "methods", "label": "Compare methods", "detail": "Compare training methods"}],
                    focusedPaperIds=["paper-a"],
                    constraints="Only methods",
                    reviewNotes="缩小范围",
                ),
            )["task"]
        self.assertEqual(approved["status"], "running")
        self.assertEqual(approved["focusedPaperIds"], ["paper-a"])
        self.assertEqual(approved["constraints"], "Only methods")

        agent_project_service._update_task(
            task["taskId"],
            status="awaiting_final_review",
            reviewRisks=[{"riskId": "open:1", "type": "open_question", "label": "开放问题", "detail": "more evidence", "sourceIds": [], "reviewStatus": "pending"}],
        )
        completed = agent_project_service.review_agent_final(
            task["taskId"],
            AgentFinalReviewRequest(reviewNotes="已检查", riskReviews=[{"riskId": "open:1", "reviewStatus": "reviewed"}]),
        )["task"]
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["humanReview"]["final"]["reviewNotes"], "已检查")

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
        tool_calls = [{
            "id": "retrieve-current-paper-1",
            "name": "retrieve_current_paper",
            "version": "1.0.0",
            "safetyScope": {
                "access": "read_only",
                "dataScopes": ["current_paper_index"],
                "networkAccess": False,
                "sideEffects": False,
                "sensitiveOutput": True,
            },
            "status": "succeeded",
            "target": "paper-a",
            "result": "Collected evidence.",
        }]
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
        self.assertEqual(completed["status"], "awaiting_final_review")
        completed = agent_project_service.review_agent_final(
            task["taskId"], AgentFinalReviewRequest(reviewNotes="reviewed", riskReviews=[])
        )["task"]
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["traceSummary"]["traceId"], completed["traceId"])
        self.assertEqual(completed["traceSummary"]["taskType"], "agent_research")
        self.assertEqual(completed["traceSummary"]["responseMeta"]["taskId"], task["taskId"])
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
        trace_response = trace_service.get_trace_summary(completed["traceId"])
        self.assertEqual(restored["status"], "succeeded")
        self.assertEqual(latest["taskId"], task["taskId"])
        self.assertEqual(restored["traceSummary"], completed["traceSummary"])
        self.assertEqual(trace_response["trace"]["traceId"], completed["traceId"])
        self.assertEqual(trace_response["trace"]["responseMeta"]["taskId"], task["taskId"])
        self.assertEqual(restored["events"][-1]["type"], "final_review_approved")
        self.assertEqual(restored["toolCalls"], completed["toolCalls"])
        self.assertEqual(restored["toolCalls"][0]["version"], "1.0.0")
        self.assertEqual(restored["toolCalls"][0]["safetyScope"]["access"], "read_only")
        self.assertEqual(restored["evidenceItems"], completed["evidenceItems"])
        self.assertEqual(restored["findings"], completed["findings"])
        self.assertEqual(restored["comparisonTable"], completed["comparisonTable"])
        self.assertEqual(restored["conflicts"], completed["conflicts"])
        self.assertEqual(restored["openQuestions"], completed["openQuestions"])
        self.assertEqual(restored["draftReport"], completed["draftReport"])

    def test_legacy_tool_call_without_contract_metadata_still_restores(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        legacy_tool_call = {"name": "retrieve_current_paper", "status": "succeeded"}
        agent_project_service._update_task(task["taskId"], toolCalls=[legacy_tool_call])

        agent_project_service.reload_agent_state_from_storage()

        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(restored["toolCalls"], [legacy_tool_call])

    def test_legacy_agent_execution_path_records_contract_metadata_on_success_and_fallback(self):
        registry = Mock()
        registry.get.return_value.version = "1.0.0"
        registry.get.return_value.safetyScope = {
            "access": "read_only",
            "dataScopes": ["current_paper_index"],
            "networkAccess": False,
            "sideEffects": False,
            "sensitiveOutput": True,
        }
        registry.invoke.return_value = {"items": []}

        with patch("services.agent_project_service.get_tool_registry", return_value=registry):
            _result, success_call = agent_project_service._invoke_agent_tool(
                "retrieve_current_paper", {"pdfId": "paper-a", "query": "method"}, {"items": []}
            )
            registry.invoke.side_effect = RuntimeError("index unavailable")
            _result, fallback_call = agent_project_service._invoke_agent_tool(
                "retrieve_current_paper", {"pdfId": "paper-a", "query": "method"}, {"items": []}
            )

        self.assertEqual(success_call["version"], "1.0.0")
        self.assertEqual(success_call["safetyScope"]["access"], "read_only")
        self.assertEqual(fallback_call["version"], "1.0.0")
        self.assertEqual(fallback_call["safetyScope"]["access"], "read_only")

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

    def test_project_task_history_lists_tasks_by_updated_time_and_limit(self):
        project = self._create_project()
        older_task = self._create_task_without_worker(project["projectId"])
        newer_task = self._create_task_without_worker(project["projectId"])

        history = agent_project_service.list_agent_project_tasks(project["projectId"], limit=1)

        self.assertEqual(history["status"], "success")
        self.assertEqual(history["projectId"], project["projectId"])
        self.assertEqual(history["limit"], 1)
        self.assertEqual([task["taskId"] for task in history["tasks"]], [newer_task["taskId"]])
        self.assertEqual(history["tasks"][0]["projectId"], project["projectId"])
        self.assertGreaterEqual(history["tasks"][0]["updatedAt"], older_task["updatedAt"])

    def test_project_task_history_normalizes_limit_and_empty_state(self):
        project = self._create_project()

        empty_history = agent_project_service.list_agent_project_tasks(project["projectId"], limit=0)

        self.assertEqual(empty_history["limit"], 20)
        self.assertEqual(empty_history["tasks"], [])

        self._create_task_without_worker(project["projectId"])
        large_limit_history = agent_project_service.list_agent_project_tasks(project["projectId"], limit=500)

        self.assertEqual(large_limit_history["limit"], 100)
        self.assertEqual(len(large_limit_history["tasks"]), 1)

    def test_project_task_history_restores_failed_interrupted_tasks_from_sqlite(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        agent_project_service.reload_agent_state_from_storage()

        history = agent_project_service.list_agent_project_tasks(project["projectId"], limit=20)

        self.assertEqual(len(history["tasks"]), 1)
        self.assertEqual(history["tasks"][0]["taskId"], task["taskId"])
        self.assertEqual(history["tasks"][0]["status"], "failed")
        self.assertEqual(history["tasks"][0]["events"][-1]["type"], "task_expired")

    def test_project_task_history_missing_project_raises(self):
        with self.assertRaises(agent_project_service.AgentProjectNotFoundError):
            agent_project_service.list_agent_project_tasks("missing-project", limit=20)

    def test_delete_project_removes_persisted_tasks_and_events(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        agent_project_service.delete_agent_project(project["projectId"])
        agent_project_service.reload_agent_state_from_storage()

        with self.assertRaises(agent_project_service.AgentProjectNotFoundError):
            agent_project_service.get_agent_project(project["projectId"])
        with self.assertRaises(agent_project_service.AgentTaskNotFoundError):
            agent_project_service.get_agent_task(task["taskId"])

    def test_legacy_project_service_returns_task_shaped_adapter_for_old_callers(self):
        project = {"projectId": "project-1", "title": "Project", "paperIds": ["paper-a"]}
        run = {
            "runId": "run-1",
            "projectId": "project-1",
            "status": "awaiting_plan_review",
            "prompt": "Compare methods.",
        }
        review = {
            "runId": "run-1",
            "status": "pending",
            "planItems": [{"id": "evidence", "label": "Collect evidence"}],
        }

        adapted = agent_project_service._build_legacy_task_snapshot(project, run, review, None, [])

        self.assertEqual(adapted["taskId"], "run-1")
        self.assertEqual(adapted["projectId"], "project-1")
        self.assertEqual(adapted["status"], "awaiting_plan_review")
        self.assertEqual(adapted["planItems"][0]["id"], "evidence")

    def test_create_agent_run_returns_run_shape_and_legacy_task_reads_same_resource(self):
        project = self._create_project()
        with patch("services.agent_project_service.threading.Thread", _NoopThread):
            run_response = agent_project_service.create_agent_run(
                project["projectId"],
                AgentRunCreateRequest(
                    prompt="Compare methods and evidence.",
                    focusedPaperIds=["paper-a", "paper-b"],
                    constraints="Use evidence first.",
                    context={"activePaperId": "paper-a"},
                    allowExternalSearch=False,
                ),
            )

        run = run_response["run"]
        legacy_task = agent_project_service.get_agent_task(run["runId"])["task"]
        self.assertEqual(run["runId"], legacy_task["taskId"])
        self.assertEqual(run["projectId"], legacy_task["projectId"])
        self.assertEqual(run["prompt"], legacy_task["prompt"])

    def test_get_agent_workspace_aggregates_project_run_review_artifacts_and_timeline(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        with patch.object(agent_project_service, "_start_agent_worker"):
            planned = agent_project_service.prepare_agent_task_now(task["taskId"])

        workspace = agent_project_service.get_agent_workspace(project["projectId"])["workspace"]
        self.assertEqual(workspace["project"]["projectId"], project["projectId"])
        self.assertEqual(workspace["activeRun"]["runId"], planned["taskId"])
        self.assertEqual(workspace["pendingReview"]["runId"], planned["taskId"])
        self.assertTrue(isinstance(workspace["latestArtifacts"], dict))
        self.assertTrue(isinstance(workspace["timeline"], list))

    def test_run_review_paths_return_run_resources(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        with patch.object(agent_project_service, "_start_agent_worker"):
            planned = agent_project_service.prepare_agent_task_now(task["taskId"])
            reviewed = agent_project_service.review_agent_run_plan(
                planned["taskId"],
                AgentRunPlanReviewRequest(
                    planItems=[{"id": "methods", "label": "Compare methods", "detail": "Compare training methods"}],
                    focusedPaperIds=["paper-a"],
                    constraints="Only methods",
                    reviewNotes="approved",
                    allowExternalSearch=False,
                ),
            )

        self.assertEqual(reviewed["run"]["runId"], planned["taskId"])
        self.assertEqual(reviewed["run"]["status"], "running")

        agent_project_service._update_task(
            planned["taskId"],
            status="awaiting_final_review",
            reviewRisks=[{"riskId": "open:1", "type": "open_question", "label": "Open", "detail": "more evidence", "sourceIds": [], "reviewStatus": "pending"}],
        )
        finalized = agent_project_service.review_agent_run_final(
            planned["taskId"],
            AgentRunFinalReviewRequest(reviewNotes="done", riskReviews=[{"riskId": "open:1", "reviewStatus": "reviewed"}]),
        )
        self.assertEqual(finalized["run"]["status"], "succeeded")
        self.assertEqual(finalized["artifacts"]["runId"], planned["taskId"])


    def test_external_search_disabled_by_default_in_plan(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        with patch.object(agent_project_service, "_start_agent_worker"):
            planned = agent_project_service.prepare_agent_task_now(task["taskId"])
        plan_items = planned.get("planItems", [])
        external_items = [pi for pi in plan_items if pi.get("id") == "external"]
        self.assertEqual(len(external_items), 1)
        self.assertFalse(external_items[0].get("allowExternalSearch", True))

    def test_external_search_enabled_in_plan_produces_external_evidence(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 3, "sourceIds": ["a-1"], "preview": "method evidence", "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 1, "sourceIds": ["b-1"], "preview": "", "status": "succeeded"},
        ]
        internal_tool_calls = [
            {
                "id": "retrieve-current-paper-1",
                "name": "retrieve_current_paper",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["current_paper_index"], "networkAccess": False, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "target": "paper-a",
                "result": "Collected 1 evidence items for paper-a.",
            }
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
            {"sourceId": "b-1", "text": "result evidence", "pdfId": "paper-b", "sectionId": "results"},
            {
                "sourceId": "external-doi-abc123",
                "sourceType": "external_academic",
                "provider": "crossref",
                "title": "External Evidence Paper",
                "authors": ["Author One"],
                "year": 2024,
                "doi": "10.1234/abc123",
                "url": "https://doi.org/10.1234/abc123",
                "retrievedAt": "2025-01-01T00:00:00Z",
                "query": "compare methods",
            },
        ]
        combined_tool_calls = internal_tool_calls + [
            {
                "id": "retrieve-external-academic-1",
                "name": "retrieve_external_academic",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["external_academic_metadata"], "networkAccess": True, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "meta": {},
            }
        ]

        with (
            patch.object(agent_project_service, "_agent_step_delay", return_value=None),
            patch.object(
                agent_project_service.agent_orchestrator,
                "collect_project_evidence",
                return_value=(paper_contexts, combined_tool_calls, evidence_items),
            ),
        ):
            agent_project_service._run_minimal_agent_task(task["taskId"])

        completed = agent_project_service.get_agent_task(task["taskId"])["task"]
        external_sources = [ei for ei in completed.get("evidenceItems", []) if ei.get("sourceType") == "external_academic"]
        self.assertGreater(len(external_sources), 0)
        self.assertEqual(external_sources[0]["doi"], "10.1234/abc123")
        self.assertIn("External Academic Evidence", completed["draftReport"])
        self.assertIn("externalEvidenceCount", completed["findings"][0])

    def test_authorized_external_search_survives_plan_execution_restore_and_final_review(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"], allow_external_search=True)
        with patch.object(agent_project_service, "_start_agent_worker"):
            planned = agent_project_service.prepare_agent_task_now(task["taskId"])
            approved = agent_project_service.review_agent_plan(
                task["taskId"],
                AgentPlanReviewRequest(
                    planItems=[
                        {"id": "methods", "label": "Compare methods", "detail": "Read internal evidence"},
                        {"id": "external", "label": "External academic search", "detail": "Fill evidence gaps", "allowExternalSearch": True},
                    ],
                    focusedPaperIds=["paper-a", "paper-b"],
                    constraints="Use external search only for evidence gaps.",
                    reviewNotes="Allow Crossref metadata lookup.",
                ),
            )["task"]

        self.assertEqual(planned["status"], "awaiting_plan_review")
        self.assertTrue(approved["externalSearchConfig"]["allowExternalSearch"])
        self.assertEqual(approved["humanReview"]["plan"]["status"], "approved")

        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 1, "sourceIds": ["a-1"], "preview": "sparse", "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 1, "sourceIds": ["b-1"], "preview": "sparse", "status": "succeeded"},
        ]
        tool_calls = [{
            "id": "retrieve-external-academic-lifecycle",
            "name": "retrieve_external_academic",
            "version": "1.0.0",
            "safetyScope": {"access": "read_only", "dataScopes": ["external_academic_metadata"], "networkAccess": True, "sideEffects": False, "sensitiveOutput": True},
            "status": "succeeded",
            "meta": {},
        }]
        evidence_items = [
            {"sourceId": "a-1", "text": "internal method evidence", "pdfId": "paper-a", "sectionId": "method"},
            {"sourceId": "b-1", "text": "internal result evidence", "pdfId": "paper-b", "sectionId": "results"},
            {
                "sourceId": "external-doi-lifecycle",
                "sourceType": "external_academic",
                "provider": "crossref",
                "title": "Deep Residual Learning for Image Recognition: A Survey",
                "year": 2022,
                "doi": "10.3390/app12188972",
                "url": "https://doi.org/10.3390/app12188972",
                "retrievedAt": "2026-06-29T00:00:00Z",
                "text": "External survey evidence.",
            },
        ]
        with (
            patch.object(agent_project_service, "_agent_step_delay", return_value=None),
            patch.object(agent_project_service.agent_orchestrator, "collect_project_evidence", return_value=(paper_contexts, tool_calls, evidence_items)),
        ):
            agent_project_service._run_minimal_agent_task(task["taskId"])

        awaiting_review = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(awaiting_review["status"], "awaiting_final_review")
        self.assertIn("External Academic Evidence", awaiting_review["draftReport"])
        self.assertIn("external-doi-lifecycle", [item["sourceId"] for item in awaiting_review["evidenceItems"]])

        agent_project_service.reload_agent_state_from_storage()
        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertIn("external-doi-lifecycle", [item["sourceId"] for item in restored["evidenceItems"]])

        completed = agent_project_service.review_agent_final(
            task["taskId"],
            AgentFinalReviewRequest(reviewNotes="External DOI checked.", riskReviews=[]),
        )["task"]
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["humanReview"]["final"]["status"], "approved")

    def test_external_search_tool_calls_record_version_and_safety_scope(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 2, "sourceIds": ["a-1"], "preview": "method", "status": "succeeded"},
        ]
        tool_calls = [
            {
                "id": "retrieve-current-paper-1",
                "name": "retrieve_current_paper",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["current_paper_index"], "networkAccess": False, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "target": "paper-a",
                "result": "Collected evidence.",
            },
            {
                "id": "retrieve-external-academic-1",
                "name": "retrieve_external_academic",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["external_academic_metadata"], "networkAccess": True, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "meta": {},
            },
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
        ]

        with (
            patch.object(agent_project_service, "_agent_step_delay", return_value=None),
            patch.object(agent_project_service.agent_orchestrator, "collect_project_evidence", return_value=(paper_contexts, tool_calls, evidence_items)),
        ):
            agent_project_service._run_minimal_agent_task(task["taskId"])

        completed = agent_project_service.get_agent_task(task["taskId"])["task"]
        external_tool_call = [tc for tc in completed.get("toolCalls", []) if tc.get("name") == "retrieve_external_academic"]
        self.assertEqual(len(external_tool_call), 1)
        self.assertEqual(external_tool_call[0]["version"], "1.0.0")
        self.assertEqual(external_tool_call[0]["safetyScope"]["access"], "read_only")
        self.assertEqual(external_tool_call[0]["safetyScope"]["dataScopes"], ["external_academic_metadata"])
        self.assertTrue(external_tool_call[0]["safetyScope"]["networkAccess"])

    def test_external_search_events_recorded_in_task_lifecycle(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 3, "sourceIds": ["a-1"], "preview": "method evidence", "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 1, "sourceIds": ["b-1"], "preview": "", "status": "succeeded"},
        ]
        tool_calls = [
            {
                "id": "retrieve-current-paper-1",
                "name": "retrieve_current_paper",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["current_paper_index"], "networkAccess": False, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "target": "paper-a",
                "result": "Collected evidence.",
            },
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
            {"sourceId": "b-1", "text": "result evidence", "pdfId": "paper-b", "sectionId": "results"},
        ]

        with (
            patch.object(agent_project_service, "_agent_step_delay", return_value=None),
            patch.object(agent_project_service.agent_orchestrator, "collect_project_evidence", return_value=(paper_contexts, tool_calls, evidence_items)),
        ):
            agent_project_service._run_minimal_agent_task(task["taskId"])

        completed = agent_project_service.get_agent_task(task["taskId"])["task"]
        events = completed.get("events", [])
        event_types = [e["type"] for e in events]
        self.assertIn("tool_completed", event_types)
        self.assertIn("judgement_completed", event_types)

        agent_project_service.reload_agent_state_from_storage()
        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(restored["status"], completed["status"])
        self.assertEqual(len(restored["events"]), len(completed["events"]))

    def test_external_search_degradation_preserved_in_snapshot(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 1, "sourceIds": ["a-1"], "preview": "sparse", "status": "succeeded"},
        ]
        degradation_tool_call = {
            "id": "retrieve-external-academic-1",
            "name": "retrieve_external_academic",
            "version": "1.0.0",
            "safetyScope": {"access": "read_only", "dataScopes": ["external_academic_metadata"], "networkAccess": True, "sideEffects": False, "sensitiveOutput": True},
            "status": "failed",
            "meta": {"reason": "External search degradation."},
        }
        tool_calls = [
            {
                "id": "retrieve-current-paper-1",
                "name": "retrieve_current_paper",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["current_paper_index"], "networkAccess": False, "sideEffects": False, "sensitiveOutput": True},
                "status": "fallback",
                "target": "paper-a",
                "result": "Collected fallback evidence.",
                "meta": {},
            },
            degradation_tool_call,
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "fallback evidence", "pdfId": "paper-a", "sectionId": "unknown", "metadata": {"fallback": True}},
        ]

        with (
            patch.object(agent_project_service, "_agent_step_delay", return_value=None),
            patch.object(agent_project_service.agent_orchestrator, "collect_project_evidence", return_value=(paper_contexts, tool_calls, evidence_items)),
        ):
            agent_project_service._run_minimal_agent_task(task["taskId"])

        agent_project_service.reload_agent_state_from_storage()
        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        restored_tool_calls = restored.get("toolCalls", [])
        external_tc = [tc for tc in restored_tool_calls if tc.get("name") == "retrieve_external_academic"]
        self.assertEqual(len(external_tc), 1)
        self.assertEqual(external_tc[0]["status"], "failed")

    def test_legacy_snapshot_without_external_evidence_still_loads(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        legacy_evidence = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
            {"sourceId": "b-1", "text": "result evidence", "pdfId": "paper-b", "sectionId": "results"},
        ]
        legacy_tool_calls = [
            {"name": "retrieve_current_paper", "status": "succeeded"},
        ]
        legacy_findings = [{"id": "synth-1", "summary": "legacy", "sourceIds": ["a-1"], "status": "draft"}]
        agent_project_service._update_task(
            task["taskId"],
            evidenceItems=legacy_evidence,
            toolCalls=legacy_tool_calls,
            findings=legacy_findings,
            status="succeeded",
            stage="done",
            progress=1.0,
        )

        agent_project_service.reload_agent_state_from_storage()

        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(restored["status"], "succeeded")
        self.assertEqual(restored["evidenceItems"], legacy_evidence)
        self.assertEqual(restored["toolCalls"], legacy_tool_calls)
        self.assertEqual(restored["findings"], legacy_findings)

    def test_cancel_during_external_search_preserves_partial_results(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        cancelled = agent_project_service.cancel_agent_task(task["taskId"])["task"]
        self.assertEqual(cancelled["status"], "cancelled")

        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 1, "sourceIds": ["a-1"], "preview": "sparse", "status": "succeeded"},
        ]
        partial_tool_calls = [
            {
                "id": "retrieve-current-paper-1",
                "name": "retrieve_current_paper",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["current_paper_index"], "networkAccess": False, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "target": "paper-a",
                "result": "Collected evidence.",
            },
        ]
        partial_evidence = [
            {"sourceId": "a-1", "text": "partial evidence", "pdfId": "paper-a", "sectionId": "method"},
        ]
        agent_project_service._update_task(
            task["taskId"],
            toolCalls=partial_tool_calls,
            evidenceItems=partial_evidence,
            status="cancelled",
        )

        agent_project_service.reload_agent_state_from_storage()
        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(restored["status"], "cancelled")
        self.assertEqual(restored["toolCalls"], partial_tool_calls)
        self.assertEqual(restored["evidenceItems"], partial_evidence)

    def test_restart_after_external_search_recovers_state(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])

        paper_contexts = [
            {"pdfId": "paper-a", "evidenceCount": 3, "sourceIds": ["a-1"], "preview": "method", "status": "succeeded"},
            {"pdfId": "paper-b", "evidenceCount": 1, "sourceIds": ["b-1"], "preview": "", "status": "succeeded"},
        ]
        tool_calls = [
            {
                "id": "retrieve-current-paper-1",
                "name": "retrieve_current_paper",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["current_paper_index"], "networkAccess": False, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "target": "paper-a",
                "result": "Collected evidence.",
            },
            {
                "id": "retrieve-external-academic-1",
                "name": "retrieve_external_academic",
                "version": "1.0.0",
                "safetyScope": {"access": "read_only", "dataScopes": ["external_academic_metadata"], "networkAccess": True, "sideEffects": False, "sensitiveOutput": True},
                "status": "succeeded",
                "meta": {},
            },
        ]
        evidence_items = [
            {"sourceId": "a-1", "text": "method evidence", "pdfId": "paper-a", "sectionId": "method"},
            {
                "sourceId": "external-doi-abc123",
                "sourceType": "external_academic",
                "provider": "crossref",
                "title": "External Paper",
                "authors": ["Author One"],
                "year": 2024,
                "doi": "10.1234/abc123",
            },
        ]

        with (
            patch.object(agent_project_service, "_agent_step_delay", return_value=None),
            patch.object(agent_project_service.agent_orchestrator, "collect_project_evidence", return_value=(paper_contexts, tool_calls, evidence_items)),
        ):
            agent_project_service._run_minimal_agent_task(task["taskId"])

        trace_service.clear_traces()
        agent_project_service.reload_agent_state_from_storage()
        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        self.assertEqual(restored["status"], "awaiting_final_review")
        self.assertEqual(len(restored["evidenceItems"]), 2)
        self.assertIn("External Academic Evidence", restored["draftReport"])


    def test_external_search_config_survives_sqlite_roundtrip(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        agent_project_service._update_task(
            task["taskId"],
            externalSearchConfig={
                "allowExternalSearch": True,
                "provider": "crossref",
                "budget": {"callLimit": 3, "evidenceLimit": 15, "callsUsed": 2, "evidenceUsed": 8},
                "status": "success",
                "degradation": "",
            },
        )
        agent_project_service.reload_agent_state_from_storage()
        restored = agent_project_service.get_agent_task(task["taskId"])["task"]
        config = restored.get("externalSearchConfig") or {}
        self.assertTrue(config.get("allowExternalSearch"))
        self.assertEqual(config["provider"], "crossref")
        self.assertEqual(config["status"], "success")

    def test_external_search_config_default_when_disabled(self):
        project = self._create_project()
        task = self._create_task_without_worker(project["projectId"])
        config = task.get("externalSearchConfig") or {}
        self.assertFalse(config.get("allowExternalSearch"))
        self.assertEqual(config.get("provider"), "disabled")
        self.assertEqual(config.get("status"), "disabled")


if __name__ == "__main__":
    unittest.main()
