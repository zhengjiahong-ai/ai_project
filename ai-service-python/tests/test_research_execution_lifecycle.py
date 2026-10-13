"""Worker lifecycle and persisted crash windows; no live provider calls."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from schemas.requests import ResearchTaskCreateRequest
from services import research_task_service as research
from services.operation_control import check_cancelled
from services.task_operation_service import OperationStore


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_TASK_DB_PATH", str(tmp_path / "research.sqlite3"))
    research.clear_research_tasks(clear_storage=False)
    yield
    research.clear_research_tasks(clear_storage=False)


@pytest.mark.parametrize("cancelled", [False, True])
def test_created_child_is_recovered_after_receipt_crash(storage, tmp_path, cancelled):
    store = OperationStore(tmp_path / "operations.sqlite3", lambda *_: pytest.fail("must not replay"))
    store.executor.submit = lambda *_: None
    payload = {"upstream": {"question": "Explain the method", "pdfId": "A", "operationKey": "task:request"}}
    try:
        store.submit("task", "request", "research.start", payload)
        store._set("task", "request", "running")
        child = research.create_research_task(ResearchTaskCreateRequest(**payload["upstream"]), start_async=False)
        if cancelled:
            store.cancel("task", "request")
        # Reload the actual persisted research database, rather than reuse memory.
        research.clear_research_tasks(clear_storage=False)
        store.recover_after_restart()
        receipt = store.get("task", "request")
        assert receipt["status"] == ("cancelled" if cancelled else "succeeded")
        assert receipt["result"]["task"]["taskId"] == child["task"]["taskId"]
        assert receipt["result"]["task"]["status"] == ("cancelled" if cancelled else "failed")
        assert store.submit("task", "request", "research.start", payload)["status"] == receipt["status"]
    finally:
        store.close()


def test_cancel_waits_for_actual_research_worker(storage, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    next_step = []
    def blocked_evidence(_):
        entered.set()
        assert release.wait(3)
        check_cancelled()
        next_step.append(True)
        return [], "A"
    monkeypatch.setattr(research, "_load_current_paper_documents", blocked_evidence)
    task_id = research.create_research_task(ResearchTaskCreateRequest(question="Explain", pdfId="A"), start_async=False)["task"]["taskId"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = executor.submit(research.prepare_research_task_now, task_id)
        try:
            assert entered.wait(3)
            assert research.cancel_research_task(task_id)["task"]["status"] == "cancelling"
            assert not worker.done()
        finally:
            release.set()
        worker.result(timeout=3)
    assert research.get_research_task(task_id)["task"]["status"] == "cancelled"
    assert next_step == []


def test_duplicate_creation_keeps_one_persisted_child(storage):
    request = ResearchTaskCreateRequest(question="Explain", pdfId="A", operationKey="task:one")
    with ThreadPoolExecutor(max_workers=8) as executor:
        children = list(executor.map(lambda _: research.create_research_task(request, start_async=False), range(8)))
    assert len({child["task"]["taskId"] for child in children}) == 1
    assert len(research._TASKS) == 1
    with pytest.raises(research.ResearchReviewConflictError):
        research.create_research_task(request.model_copy(update={"question": "Different"}), start_async=False)


def test_explicit_resume_skips_saved_completed_work_and_schedules_once(storage, monkeypatch):
    task_id = research.create_research_task(ResearchTaskCreateRequest(question="Explain", pdfId="A"), start_async=False)["task"]["taskId"]
    plan = [{"question": "already done", "status": "done", "kind": "initial"},
            {"question": "remaining", "status": "running", "kind": "initial"}]
    research._TASK_CONTEXTS[task_id]["approvedPlan"] = plan
    research._update_task_snapshot(task_id, status="running", plan=plan, findings=[{"subQuestion": "already done", "summary": "saved"}])
    research.reload_research_tasks_from_storage()
    assert research.get_research_task(task_id)["task"]["status"] == "failed"
    scheduled = []
    monkeypatch.setattr(research._TASK_EXECUTOR, "submit", lambda fn, identity: scheduled.append((fn, identity)))
    research.resume_research_task(task_id)
    research.resume_research_task(task_id)
    assert len(scheduled) == 1
    monkeypatch.setattr(research, "_load_current_paper_documents", lambda _: ([{"text": "evidence"}], "A"))
    queries = []
    def answer(**kwargs):
        queries.append(kwargs["sub_question"])
        return {"subQuestion": kwargs["sub_question"], "summary": "new", "sources": []}
    monkeypatch.setattr(research, "_research_sub_question", answer)
    monkeypatch.setattr(research, "_should_create_follow_up", lambda _: False)
    monkeypatch.setattr(research, "_detect_research_conflicts", lambda _: [])
    monkeypatch.setattr(research, "_build_research_report", lambda *args, **kwargs: "report")
    research.run_research_task_now(task_id)
    result = research.get_research_task(task_id)["task"]
    assert queries == ["remaining"]
    assert [item["summary"] for item in result["findings"]] == ["saved", "new"]
    assert result["status"] == "awaiting_final_review"


def test_resume_without_plan_does_not_silently_call_provider(storage):
    task_id = research.create_research_task(ResearchTaskCreateRequest(question="Explain", pdfId="A"), start_async=False)["task"]["taskId"]
    research.cancel_research_task(task_id)
    with pytest.raises(research.ResearchReviewConflictError):
        research.resume_research_task(task_id)
    assert research.get_research_task(task_id)["task"]["status"] == "cancelled"


def test_concurrent_plan_confirmation_schedules_one_worker(storage, monkeypatch):
    from schemas.requests import ResearchPlanReviewRequest
    task_id = research.create_research_task(ResearchTaskCreateRequest(question="Explain", pdfId="A"), start_async=False)["task"]["taskId"]
    research._update_task_snapshot(task_id, status="awaiting_plan_review", plan=[{"question": "Question"}])
    submitted = []
    monkeypatch.setattr(research._TASK_EXECUTOR, "submit", lambda *args: submitted.append(args))
    request = ResearchPlanReviewRequest(subQuestions=["Question"])
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: research.review_research_plan(task_id, request), range(8)))
    assert len(submitted) == 1
    assert all(result["task"]["status"] == "running" for result in results)
