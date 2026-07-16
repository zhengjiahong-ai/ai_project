import copy
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from schemas.requests import (
    AgentFinalReviewRequest,
    AgentPlanReviewRequest,
    AgentProjectCreateRequest,
    AgentProjectPapersRequest,
    AgentProjectUpdateRequest,
    AgentRunCreateRequest,
    AgentRunFinalReviewRequest,
    AgentRunPlanReviewRequest,
    AgentTaskCreateRequest,
)
from services import agent_orchestrator
from services.agent_report_builder import (
    _build_conflict_lines,
    _build_conclusion_lines,
    _build_evidence_snapshot_lines,
    _build_finding_summary,
    _build_minimal_report,
    _build_paper_judgement,
    _build_paper_support_profiles,
    _build_scope_lines,
    _detect_conflicts,
    _evidence_preview,
    _extract_common_themes,
    _extract_keywords,
    _infer_theme_from_evidence,
    _stabilize_source_ids,
)
from services.agent_legacy_adapter import (
    AgentProjectNotFoundError,
    _build_artifacts_resource,
    _build_legacy_task_snapshot,
    _build_legacy_task_snapshot_from_run_id,
    _build_pending_review_record,
    _build_run_record,
    _build_task_snapshot_from_resources,
    _build_timeline_resource,
)
from services.agent_state_repository import AgentStateRepository
from services.agent_workspace_service import build_workspace_view
from services.evidence_service import normalize_evidence_items
from services.trace_service import (
    build_public_trace_summary,
    finalize_trace,
    record_counter,
    record_metric,
    sanitize_text,
    start_trace,
    trace_step,
    use_trace,
)


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
PLANNING_STAGE = "planning"
RETRIEVING_STAGE = "retrieving"
SYNTHESIZING_STAGE = "synthesizing"
DONE_STAGE = "done"
AGENT_STEP_DELAY_SECONDS = 0.12
INTERRUPTED_RESTART_ERROR = "Agent task was interrupted by service restart."

_LOCK = threading.RLock()
_PROJECTS: Dict[str, Dict[str, Any]] = {}
_TASKS: Dict[str, Dict[str, Any]] = {}
_STORAGE_LOADED = False


def get_tool_registry():
    from services.tool_registry import get_tool_registry as _get_tool_registry

    return _get_tool_registry()


def _get_agent_state_repository() -> AgentStateRepository:
    repository = AgentStateRepository(str(_agent_state_db_path()))
    repository.initialize()
    return repository


class AgentTaskNotFoundError(Exception):
    pass


class AgentReviewConflictError(Exception):
    pass


def create_agent_project(request: AgentProjectCreateRequest) -> Dict[str, Any]:
    _ensure_storage_loaded()
    title = _clean_text(request.title) or "Agent Research Project"
    goal = _clean_text(request.goal) or "Build a project-scoped research workspace across multiple papers."
    paper_ids = _normalize_id_list(request.paperIds)
    now = _utc_now()
    project = {
        "projectId": str(uuid.uuid4()),
        "title": title,
        "goal": goal,
        "paperIds": paper_ids,
        "papers": [_paper_stub(pdf_id) for pdf_id in paper_ids],
        "latestTaskId": "",
        "defaultConstraints": "",
        "createdAt": now,
        "updatedAt": now,
    }
    with _LOCK:
        _PROJECTS[project["projectId"]] = copy.deepcopy(project)
        _persist_project_locked(project)
    return {"status": "success", "project": copy.deepcopy(project)}


def list_agent_projects() -> Dict[str, Any]:
    _ensure_storage_loaded()
    with _LOCK:
        projects = sorted(
            (copy.deepcopy(project) for project in _PROJECTS.values()),
            key=lambda item: str(item.get("updatedAt") or ""),
            reverse=True,
        )
    return {"status": "success", "projects": projects}


def get_agent_project(project_id: str) -> Dict[str, Any]:
    return {"status": "success", "project": _copy_project(project_id)}


def update_agent_project(project_id: str, request: AgentProjectUpdateRequest) -> Dict[str, Any]:
    _ensure_storage_loaded()
    with _LOCK:
        project = _PROJECTS.get(project_id)
        if project is None:
            raise AgentProjectNotFoundError("Agent project not found.")
        if request.title is not None:
            project["title"] = _clean_text(request.title) or project["title"]
        if request.goal is not None:
            project["goal"] = _clean_text(request.goal)
        if request.defaultConstraints is not None:
            project["defaultConstraints"] = _clean_text(request.defaultConstraints)
        project["updatedAt"] = _utc_now()
        _PROJECTS[project_id] = copy.deepcopy(project)
        _persist_project_locked(project)
    return {"status": "success", "project": _copy_project(project_id)}


def delete_agent_project(project_id: str) -> Dict[str, Any]:
    _ensure_storage_loaded()
    normalized_project_id = _clean_text(project_id)
    with _LOCK:
        if normalized_project_id not in _PROJECTS:
            raise AgentProjectNotFoundError("Agent project not found.")
        del _PROJECTS[normalized_project_id]
        task_ids = [
            task_id
            for task_id, task in _TASKS.items()
            if _clean_text(task.get("projectId")) == normalized_project_id
        ]
        for task_id in task_ids:
            del _TASKS[task_id]
        _delete_persisted_project_locked(normalized_project_id)
    return {"status": "success", "projectId": normalized_project_id}


def add_project_papers(project_id: str, request: AgentProjectPapersRequest) -> Dict[str, Any]:
    _ensure_storage_loaded()
    incoming_ids = _normalize_id_list(request.paperIds)
    with _LOCK:
        project = _PROJECTS.get(project_id)
        if project is None:
            raise AgentProjectNotFoundError("Agent project not found.")
        paper_ids = _normalize_id_list([*project.get("paperIds", []), *incoming_ids])
        project["paperIds"] = paper_ids
        project["papers"] = [_paper_stub(pdf_id) for pdf_id in paper_ids]
        project["updatedAt"] = _utc_now()
        _PROJECTS[project_id] = copy.deepcopy(project)
        _persist_project_locked(project)
    return {"status": "success", "project": _copy_project(project_id)}


def remove_project_paper(project_id: str, pdf_id: str) -> Dict[str, Any]:
    _ensure_storage_loaded()
    normalized_pdf_id = _clean_text(pdf_id)
    with _LOCK:
        project = _PROJECTS.get(project_id)
        if project is None:
            raise AgentProjectNotFoundError("Agent project not found.")
        paper_ids = [item for item in _normalize_id_list(project.get("paperIds")) if item != normalized_pdf_id]
        project["paperIds"] = paper_ids
        project["papers"] = [_paper_stub(item) for item in paper_ids]
        project["updatedAt"] = _utc_now()
        _PROJECTS[project_id] = copy.deepcopy(project)
        _persist_project_locked(project)
    return {"status": "success", "project": _copy_project(project_id)}


def create_agent_run(project_id: str, request: AgentRunCreateRequest | Dict[str, Any]) -> Dict[str, Any]:
    _ensure_storage_loaded()
    project = _copy_project(project_id)
    normalized_request = _normalize_run_request(request)
    prompt = _clean_text(normalized_request.prompt)
    if not prompt:
        raise ValueError("Prompt cannot be empty.")
    focused_paper_ids = _normalize_id_list(normalized_request.focusedPaperIds) or list(project.get("paperIds") or [])
    trace_id = start_trace(
        "agent_research",
        request_meta={
            "projectId": sanitize_text(project_id, max_chars=120),
            "prompt": sanitize_text(prompt, max_chars=160),
            "paperIds": focused_paper_ids[:8],
        },
        activate=False,
        initial_status="pending",
    )
    now = _utc_now()
    task_id = str(uuid.uuid4())
    task = {
        "taskId": task_id,
        "projectId": project_id,
        "traceId": trace_id,
        "status": "running",
        "stage": PLANNING_STAGE,
        "progress": 0.1,
        "prompt": prompt,
        "focusedPaperIds": focused_paper_ids,
        "constraints": _clean_text(normalized_request.constraints),
        "context": {
            **dict(normalized_request.context or {}),
            "domain": _clean_text(getattr(normalized_request, "domain", "") or ""),
        },
        "planItems": [],
        "events": [_event("task_created", task_id, PLANNING_STAGE, "Created an Agent research task.")],
        "toolCalls": [],
        "evidenceItems": [],
        "findings": [],
        "comparisonTable": {"columns": [], "rows": []},
        "conflicts": [],
        "reviewRisks": [],
        "humanReview": {"plan": {"status": "pending", "reviewNotes": "", "reviewedAt": ""}, "final": {"status": "pending", "reviewNotes": "", "reviewedAt": "", "riskReviews": []}},
        "traceSummary": {},
        "externalSearchConfig": {
            "allowExternalSearch": bool(getattr(normalized_request, "allowExternalSearch", False)),
            "allowWebSearch": bool(getattr(normalized_request, "allowWebSearch", False)),
            "allowIterativeSearch": bool(getattr(normalized_request, "allowIterativeSearch", False)),
            "provider": "disabled",
            "budget": {"callLimit": 3, "evidenceLimit": 15, "callsUsed": 0, "evidenceUsed": 0},
            "status": "disabled",
            "degradation": "",
        },
        "codeExecutionConfig": {
            "allowCodeExecution": bool(getattr(normalized_request, "allowCodeExecution", False)),
            "proposal": None,
            "jobId": None,
            "jobStatus": None,
            "publishable": False,
            "degradation": "",
        },
        "openQuestions": [],
        "draftReport": "",
        "error": "",
        "createdAt": now,
        "updatedAt": now,
    }
    with _LOCK:
        _TASKS[task_id] = copy.deepcopy(task)
        _PROJECTS[project_id]["latestTaskId"] = task_id
        _PROJECTS[project_id]["updatedAt"] = now
        _persist_task_locked(task)
        _persist_project_locked(_PROJECTS[project_id])

    _start_agent_worker(prepare_agent_task_now, task_id)
    return {"status": "success", "run": _build_run_record(_copy_task(task_id))}


def create_agent_task(project_id: str, request: AgentTaskCreateRequest) -> Dict[str, Any]:
    created = create_agent_run(project_id, request)
    return {"status": "success", "task": _build_legacy_task_snapshot_from_run_id(created["run"]["runId"])}


def _start_agent_worker(target, task_id: str) -> None:
    worker = threading.Thread(target=target, args=(task_id,), daemon=True)
    worker.start()


def prepare_agent_task_now(task_id: str) -> Dict[str, Any]:
    task = _copy_task(task_id)
    paper_ids = list(task.get("focusedPaperIds") or [])
    plan_items = agent_orchestrator.build_review_plan_items(task.get("prompt") or "", paper_ids, task.get("constraints") or "")
    events = [*task.get("events", []), _event("plan_generated", task_id, PLANNING_STAGE, "Generated a research plan for human review.")]
    return _update_task(task_id, status="awaiting_plan_review", stage=PLANNING_STAGE, progress=0.2, planItems=plan_items, events=events)


def review_agent_plan(task_id: str, request: AgentPlanReviewRequest) -> Dict[str, Any]:
    reviewed = review_agent_run_plan(task_id, request)
    return {"status": "success", "task": _build_legacy_task_snapshot_from_run_id(reviewed["run"]["runId"])}


def review_agent_run_plan(run_id: str, request: AgentRunPlanReviewRequest | AgentPlanReviewRequest) -> Dict[str, Any]:
    task_id = _clean_text(run_id)
    task = _copy_task(task_id)
    if task.get("status") != "awaiting_plan_review":
        if task.get("status") in {"running", "awaiting_final_review", "succeeded"}:
            return {"status": "success", "run": _build_run_record(task)}
        raise AgentReviewConflictError("Agent task is not awaiting plan review.")
    project = _copy_project(str(task.get("projectId") or ""))
    paper_ids = _normalize_id_list(request.focusedPaperIds)
    if not paper_ids or any(item not in (project.get("paperIds") or []) for item in paper_ids):
        raise ValueError("focusedPaperIds must reference papers in the project.")
    plan_items = agent_orchestrator.normalize_review_plan_items([item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in request.planItems])
    if not plan_items:
        raise ValueError("At least one valid Agent plan item is required.")
    allow_code_execution = bool(getattr(request, "allowCodeExecution", False))
    code_execution_config = copy.deepcopy(task.get("codeExecutionConfig") or {})
    code_execution_config["allowCodeExecution"] = allow_code_execution
    human_review = copy.deepcopy(task.get("humanReview") or {})
    human_review["plan"] = {"status": "approved", "reviewNotes": _clean_text(request.reviewNotes), "reviewedAt": _utc_now()}
    updated = _update_task(task_id, status="running", focusedPaperIds=paper_ids, constraints=_clean_text(request.constraints), planItems=plan_items, humanReview=human_review, codeExecutionConfig=code_execution_config)
    _start_agent_worker(_run_minimal_agent_task, task_id)
    return {"status": "success", "run": _build_run_record(updated), "pendingReview": _build_pending_review_record(updated)}


def review_agent_final(task_id: str, request: AgentFinalReviewRequest) -> Dict[str, Any]:
    reviewed = review_agent_run_final(task_id, request)
    return {"status": "success", "task": _build_legacy_task_snapshot_from_run_id(reviewed["run"]["runId"])}


def review_agent_run_final(run_id: str, request: AgentRunFinalReviewRequest | AgentFinalReviewRequest) -> Dict[str, Any]:
    task_id = _clean_text(run_id)
    task = _copy_task(task_id)
    if task.get("status") == "succeeded":
        return {"status": "success", "run": _build_run_record(task)}
    if task.get("status") != "awaiting_final_review":
        raise AgentReviewConflictError("Agent task is not awaiting final review.")
    risk_reviews = _validate_agent_risk_reviews(task.get("reviewRisks") or [], request.riskReviews or [])
    human_review = copy.deepcopy(task.get("humanReview") or {})
    human_review["final"] = {"status": "approved", "reviewNotes": _clean_text(request.reviewNotes), "reviewedAt": _utc_now(), "riskReviews": risk_reviews}
    events = [*task.get("events", []), _event("final_review_approved", task_id, DONE_STAGE, "Human reviewer approved the final draft.")]
    status_by_id = {item["riskId"]: item["reviewStatus"] for item in risk_reviews}
    reviewed_risks = [{**item, "reviewStatus": status_by_id.get(_clean_text(item.get("riskId")), item.get("reviewStatus") or "pending")} for item in task.get("reviewRisks") or []]
    updated = _update_task(task_id, status="succeeded", stage=DONE_STAGE, progress=1.0, humanReview=human_review, reviewRisks=reviewed_risks, events=events)
    with use_trace(str(task.get("traceId") or "")):
        trace_snapshot = finalize_trace("success", response_meta={"taskId": task_id, "projectId": task.get("projectId")})
        _persist_trace_summary(task_id, trace_snapshot)
    finalized_task = _copy_task(task_id)
    return {"status": "success", "run": _build_run_record(finalized_task), "artifacts": _build_artifacts_resource(finalized_task)}


def answer_agent_clarification(run_id: str, request) -> Dict[str, Any]:
    """Process user's answer to a clarification question and resume the run."""
    from services.research_dialogue import incorporate_user_feedback
    from services.agent_run_service import transition_run_status

    task_id = _clean_text(run_id)
    task = _copy_task(task_id)
    if task.get("status") != "awaiting_clarification":
        raise AgentReviewConflictError("Agent task is not awaiting clarification.")

    user_answer = _clean_text(request.userAnswer)
    question = _clean_text((request.question or task.get("pendingClarificationQuestion") or ""))
    current_direction = _clean_text(request.currentDirection or task.get("prompt") or "")

    # Incorporate user feedback
    feedback_result = incorporate_user_feedback(question, user_answer, current_direction)

    # Record clarification in timeline
    events = [
        *task.get("events", []),
        _event(
            "clarification_answered", task_id,
            task.get("stage", "synthesizing"),
            f"User answered clarification: {user_answer[:200]}",
        ),
    ]

    # Transition back to running
    execution_phase = task.get("executionPhase") or task.get("stage") or "synthesizing"
    transitioned = transition_run_status(task, "running", execution_phase)
    with _LOCK:
        _TASKS[task_id] = {**transitioned, "updatedAt": _utc_now()}
        _persist_task_locked(_TASKS[task_id])

    # Also update the refined direction
    refined = feedback_result.get("refinedDirection") or ""
    refined_queries = feedback_result.get("refinedQueries") or []
    context = copy.deepcopy(_copy_task(task_id).get("context") or {})
    context["refinedDirection"] = refined
    context["refinedQueries"] = refined_queries
    context["clarificationRound"] = (context.get("clarificationRound") or 0) + 1
    updated = _update_task(task_id, context=context, events=events)

    return {"status": "success", "run": _build_run_record(updated),
            "refinedDirection": refined, "refinedQueries": refined_queries}



def get_latest_agent_task(project_id: str) -> Dict[str, Any]:
    project = _copy_project(project_id)
    task_id = _clean_text(project.get("latestTaskId"))
    if not task_id:
        raise AgentTaskNotFoundError("Agent task not found.")
    return {"status": "success", "task": _build_legacy_task_snapshot_from_run_id(task_id)}


def list_agent_project_tasks(project_id: str, limit: Any = 20) -> Dict[str, Any]:
    project = _copy_project(project_id)
    normalized_project_id = _clean_text(project.get("projectId"))
    normalized_limit = _normalize_history_limit(limit)
    with _LOCK:
        run_ids = [
            _clean_text(task.get("taskId"))
            for task in _TASKS.values()
            if _clean_text(task.get("projectId")) == normalized_project_id
        ]
    tasks = [
        _build_legacy_task_snapshot_from_run_id(run_id)
        for run_id in run_ids
        if run_id
    ]
    tasks.sort(key=lambda item: str(item.get("updatedAt") or item.get("createdAt") or ""), reverse=True)
    return {
        "status": "success",
        "projectId": normalized_project_id,
        "tasks": tasks[:normalized_limit],
        "limit": normalized_limit,
    }


def get_agent_task(task_id: str) -> Dict[str, Any]:
    return {"status": "success", "task": _build_legacy_task_snapshot_from_run_id(task_id)}


def get_agent_run(run_id: str) -> Dict[str, Any]:
    task = _copy_task(_clean_text(run_id))
    return {"status": "success", "run": _build_run_record(task)}


def get_agent_run_artifacts(run_id: str) -> Dict[str, Any]:
    task = _copy_task(_clean_text(run_id))
    return {"status": "success", "artifacts": _build_artifacts_resource(task)}


def get_agent_run_timeline(run_id: str) -> Dict[str, Any]:
    task = _copy_task(_clean_text(run_id))
    return {"status": "success", "timeline": _build_timeline_resource(task)}


def get_agent_workspace(project_id: str) -> Dict[str, Any]:
    project = _copy_project(project_id)
    recent_tasks = _list_project_tasks(project_id)
    active_task = recent_tasks[0] if recent_tasks else None
    pending_clarification = None
    if active_task and active_task.get("status") == "awaiting_clarification":
        clarification_question = (active_task.get("context") or {}).get("clarificationQuestion") or ""
        clarification_round = (active_task.get("context") or {}).get("clarificationRound") or 1
        if clarification_question:
            pending_clarification = {
                "runId": active_task.get("taskId"),
                "question": [{"question": clarification_question, "context": "Research needs clarification"}],
                "roundNumber": clarification_round,
            }

    workspace = build_workspace_view(
        project=copy.deepcopy(project),
        active_run=_build_run_record(active_task) if active_task else None,
        pending_review=_build_pending_review_record(active_task) if active_task else None,
        latest_artifacts=_build_artifacts_resource(active_task) if active_task else None,
        recent_runs=[_build_run_record(task) for task in recent_tasks[:20]],
        timeline=_build_timeline_resource(active_task) if active_task else [],
        pending_clarification=pending_clarification,
    )
    return {"status": "success", "workspace": workspace}


def get_persisted_trace_summary(trace_id: str) -> Dict[str, Any] | None:
    _ensure_storage_loaded()
    normalized_trace_id = _clean_text(trace_id)
    if not normalized_trace_id:
        return None

    with _LOCK:
        for task in _TASKS.values():
            if _clean_text(task.get("traceId")) != normalized_trace_id:
                continue
            summary = task.get("traceSummary")
            return copy.deepcopy(summary) if isinstance(summary, dict) and summary else None
    return None


def cancel_agent_task(task_id: str) -> Dict[str, Any]:
    _ensure_storage_loaded()
    should_finalize_cancelled = False
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise AgentTaskNotFoundError("Agent task not found.")
        if task.get("status") not in TERMINAL_STATUSES:
            task["status"] = "cancelled"
            task["stage"] = DONE_STAGE
            task["progress"] = 1.0
            task["events"] = [*task.get("events", []), _event("task_cancelled", task_id, DONE_STAGE, "Task was cancelled.")]
            task["updatedAt"] = _utc_now()
            _TASKS[task_id] = copy.deepcopy(task)
            _persist_task_locked(task)
            should_finalize_cancelled = True
    if should_finalize_cancelled:
        with use_trace(str(task.get("traceId") or "")):
            trace_snapshot = finalize_trace("cancelled", response_meta={"taskId": task_id, "projectId": task.get("projectId")})
            _persist_trace_summary(task_id, trace_snapshot)
    return {"status": "success", "task": _copy_task(task_id)}


def clear_agent_state(clear_storage: bool = False) -> None:
    global _STORAGE_LOADED
    with _LOCK:
        _PROJECTS.clear()
        _TASKS.clear()
        _STORAGE_LOADED = False
        if clear_storage:
            _delete_persisted_state_locked()
            _STORAGE_LOADED = True


def reload_agent_state_from_storage() -> None:
    global _STORAGE_LOADED
    with _LOCK:
        _PROJECTS.clear()
        _TASKS.clear()
        _STORAGE_LOADED = False
    _ensure_storage_loaded()


def _run_minimal_agent_task(task_id: str) -> None:
    try:
        task = _copy_task(task_id)
        project = _copy_project(str(task.get("projectId") or ""))
    except (AgentProjectNotFoundError, AgentTaskNotFoundError):
        return
    paper_ids = list(task.get("focusedPaperIds") or project.get("paperIds") or [])
    prompt = _clean_text(task.get("prompt"))
    constraints = _clean_text(task.get("constraints"))
    approved_plan = list(task.get("planItems") or [])
    execution_prompt = agent_orchestrator.build_execution_prompt(prompt, approved_plan, constraints)

    with use_trace(str(task.get("traceId") or "")):
        try:
            if _is_task_cancelled(task_id):
                return
            _update_task(
                task_id,
                status="running",
                stage=PLANNING_STAGE,
                progress=0.15,
                events=[*_copy_task(task_id).get("events", []), _event("task_started", task_id, PLANNING_STAGE, "Started staged Agent execution.")],
            )
            _agent_step_delay()
            with trace_step("agent_task_understanding", input_size=len(prompt)) as step:
                planning_context = agent_orchestrator.build_planning_context(project, paper_ids, constraints)
                step["outputSize"] = len(planning_context)

            if _is_task_cancelled(task_id):
                return
            plan_items = agent_orchestrator.update_plan_status(approved_plan, "running")
            events = [
                *_copy_task(task_id).get("events", []),
                _event("task_understood", task_id, PLANNING_STAGE, "Confirmed project scope and focused papers."),
                _event("plan_generated", task_id, PLANNING_STAGE, "Generated a lightweight execution plan."),
            ]
            _update_task(task_id, planItems=plan_items, events=events, progress=0.3)
            _agent_step_delay()

            if _is_task_cancelled(task_id):
                return
            _update_task(
                task_id,
                stage=RETRIEVING_STAGE,
                progress=0.42,
                planItems=agent_orchestrator.update_plan_status(approved_plan, "running"),
                events=[*_copy_task(task_id).get("events", []), _event("retrieval_started", task_id, RETRIEVING_STAGE, "Started per-paper evidence retrieval.")],
            )

            def update_retrieval_progress(tool_calls, evidence_items, _paper_contexts, progress, pdf_id):
                _update_task(
                    task_id,
                    toolCalls=tool_calls,
                    evidenceItems=evidence_items,
                    events=[
                        *_copy_task(task_id).get("events", []),
                        _event("paper_evidence_collected", task_id, RETRIEVING_STAGE, f"Collected evidence from {pdf_id}."),
                    ],
                    progress=progress,
                )
                _agent_step_delay()

            allow_external_search = any(
                bool(item.get("allowExternalSearch")) for item in approved_plan
            )
            allow_web_search = any(
                bool(item.get("allowWebSearch")) for item in approved_plan
            )
            allow_iterative_search = any(
                bool(item.get("allowIterativeSearch")) for item in approved_plan
            )
            task_context = _copy_task(task_id).get("context") or {}
            domain = task_context.get("domain") or ""
            domain_config = {}
            if domain:
                try:
                    from services.domain_specialists import activate_domain_specialist
                    domain_config = activate_domain_specialist(domain)
                except Exception:
                    domain_config = {}
            paper_contexts, tool_calls, evidence_items, _research_timeline = agent_orchestrator.collect_project_evidence(
                execution_prompt,
                paper_ids,
                allow_external_search=allow_external_search,
                allow_web_search=allow_web_search,
                allow_iterative_search=allow_iterative_search,
                should_cancel=lambda: _is_task_cancelled(task_id),
                on_progress=update_retrieval_progress,
                domain_config=domain_config,
            )
            if _is_task_cancelled(task_id):
                return
            events = [
                *_copy_task(task_id).get("events", []),
                _event(
                    "tool_completed",
                    task_id,
                    RETRIEVING_STAGE,
                    f"Collected evidence from {len(paper_contexts)} project papers.",
                ),
            ]
            _update_task(
                task_id,
                toolCalls=tool_calls,
                evidenceItems=evidence_items,
                events=events,
                progress=0.72,
                planItems=agent_orchestrator.update_plan_status(approved_plan, "running"),
                researchTimeline=_research_timeline,
            )
            _agent_step_delay()

            if _is_task_cancelled(task_id):
                return
            _update_task(task_id, stage=SYNTHESIZING_STAGE, progress=0.86)
            finding, comparison_table, conflicts, open_questions = agent_orchestrator.build_agent_outputs(execution_prompt, paper_contexts, evidence_items)
            draft_report = agent_orchestrator.build_minimal_report(execution_prompt, project, paper_contexts, evidence_items, conflicts, open_questions)
            events = [
                *_copy_task(task_id).get("events", []),
                _event("judgement_completed", task_id, SYNTHESIZING_STAGE, "Built cross-paper judgements and conflict candidates."),
                _event("report_updated", task_id, SYNTHESIZING_STAGE, "Built a project-level draft report."),
                _event("task_completed", task_id, DONE_STAGE, "Completed staged Agent orchestration."),
            ]
            _update_task(
                task_id,
                status="awaiting_final_review",
                stage=SYNTHESIZING_STAGE,
                progress=0.95,
                events=events,
                planItems=agent_orchestrator.update_plan_status(approved_plan, "done"),
                findings=[finding],
                comparisonTable=comparison_table,
                conflicts=conflicts,
                openQuestions=open_questions,
                draftReport=draft_report,
                reviewRisks=_build_agent_review_risks(conflicts, open_questions),
                error="",
            )
            record_metric("awaitingFinalReview", True)
        except Exception as error:
            try:
                current_task = _copy_task(task_id)
            except AgentTaskNotFoundError:
                return
            _update_task(
                task_id,
                status="failed",
                stage=DONE_STAGE,
                progress=1.0,
                error=_clean_text(error)[:240] or "Agent task failed.",
                events=[*current_task.get("events", []), _event("task_failed", task_id, DONE_STAGE, "Agent task failed.")],
            )
            trace_snapshot = finalize_trace(
                "error",
                error=error,
                response_meta={
                    "taskId": task_id,
                    "projectId": task.get("projectId"),
                    "paperIds": paper_ids,
                },
            )
            _persist_trace_summary(task_id, trace_snapshot)


def _collect_project_evidence(task_id: str, prompt: str, paper_ids: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    paper_contexts: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    evidence_items: List[Dict[str, Any]] = []

    for index, pdf_id in enumerate(paper_ids):
        if _is_task_cancelled(task_id):
            break
        with trace_step(
            "agent_collect_paper_evidence",
            input_size=len(prompt),
            meta={"pdfId": sanitize_text(pdf_id, max_chars=80)},
        ) as step:
            tool_result, tool_call = _invoke_agent_tool(
                "retrieve_current_paper",
                {
                    "pdfId": pdf_id,
                    "query": prompt,
                    "topK": 6,
                    "limit": 3,
                    "maxTextChars": 420,
                },
                fallback=_fallback_tool_result(pdf_id),
            )
            items = normalize_evidence_items(
                tool_result.get("items") or [],
                source_type="current_paper",
                pdf_id=pdf_id,
                limit=3,
                max_text_chars=420,
            )
            items = _stabilize_source_ids(items, fallback_prefix=pdf_id)
            evidence_items.extend(items)
            paper_contexts.append(
                {
                    "pdfId": pdf_id,
                    "evidenceCount": len(items),
                    "sourceIds": [item.get("sourceId") for item in items if item.get("sourceId")],
                    "preview": _evidence_preview(items),
                    "status": tool_call["status"],
                }
            )
            tool_calls.append(
                {
                    **tool_call,
                    "id": f"retrieve-current-paper-{index + 1}",
                    "target": pdf_id,
                    "result": f"Collected {len(items)} evidence items for {pdf_id}.",
                }
            )
            step["outputSize"] = len(items)
        progress = 0.45 + (0.22 * ((index + 1) / max(1, len(paper_ids))))
        _update_task(
            task_id,
            toolCalls=copy.deepcopy(tool_calls),
            evidenceItems=copy.deepcopy(evidence_items[:12]),
            events=[
                *_copy_task(task_id).get("events", []),
                _event("paper_evidence_collected", task_id, RETRIEVING_STAGE, f"Collected evidence from {pdf_id}."),
            ],
            progress=round(progress, 2),
        )
        _agent_step_delay()

    return paper_contexts, tool_calls, evidence_items[:12]


def _build_agent_outputs(
    prompt: str,
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[str]]:
    source_ids = [item.get("sourceId") for item in evidence_items if item.get("sourceId")]
    paper_ids = [item.get("pdfId") for item in paper_contexts if item.get("pdfId")]

    finding = {
        "id": "project-synthesis-1",
        "summary": _build_finding_summary(prompt, paper_contexts, evidence_items),
        "sourceIds": source_ids[:8],
        "status": "draft",
    }
    comparison_table = {
        "columns": ["paperId", "evidenceCount", "retrievalStatus", "judgement", "evidencePreview"],
        "rows": [
            [
                item.get("pdfId"),
                item.get("evidenceCount", 0),
                item.get("status", "unknown"),
                _build_paper_judgement(item),
                item.get("preview", ""),
            ]
            for item in paper_contexts
        ],
    }
    conflicts = _detect_conflicts(paper_contexts, evidence_items)
    open_questions = []
    for item in paper_contexts:
        if item.get("evidenceCount", 0) <= 1:
            open_questions.append(f"Need denser evidence coverage for {item.get('pdfId')}.")
    if not paper_ids:
        open_questions.append("No papers are attached to the project yet.")
    if not evidence_items:
        open_questions.append("Project retrieval returned no indexed evidence and is running on fallback summaries.")
    if not open_questions:
        open_questions.append("Next round can deepen claim-level judging with stronger section-aware evidence.")
    return finding, comparison_table, conflicts, open_questions[:5]


def _invoke_agent_tool(name: str, payload: Dict[str, Any], fallback: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    record_counter("retrievalCalls")
    registry = get_tool_registry()
    definition = registry.get(name)
    audit_meta = {
        "version": definition.version,
        "safetyScope": copy.deepcopy(definition.safetyScope),
    }
    try:
        response = registry.invoke(name, payload)
        normalized = response if isinstance(response, dict) else {}
        return normalized, {"name": name, "status": "succeeded", "meta": {}, **audit_meta}
    except Exception as error:
        return fallback, {
            "name": name,
            "status": "fallback",
            "meta": {"reason": sanitize_text(error, max_chars=180)},
            **audit_meta,
        }


def _fallback_tool_result(pdf_id: str) -> Dict[str, Any]:
    return {
        "items": [
            {
                "sourceId": f"{pdf_id}-fallback-1",
                "text": f"Fallback project evidence placeholder for {pdf_id}. Indexed retrieval can replace this in later rounds.",
                "pdfId": pdf_id,
                "chunkIndex": None,
                "pageIndex": None,
                "sectionId": None,
                "metadata": {"fallback": True, "stage": "round_2"},
            }
        ]
    }


def _build_plan_items(paper_ids: List[str], active_step: str = "scope") -> List[Dict[str, Any]]:
    status_by_step = {
        "scope": "pending",
        "retrieve": "pending",
        "synthesize": "pending",
    }
    if active_step == "scope":
        status_by_step["scope"] = "running"
    elif active_step == "retrieve":
        status_by_step["scope"] = "done"
        status_by_step["retrieve"] = "running"
    elif active_step == "synthesize":
        status_by_step["scope"] = "done"
        status_by_step["retrieve"] = "done"
        status_by_step["synthesize"] = "running"
    elif active_step == "done":
        status_by_step = {key: "done" for key in status_by_step}
    return [
        _plan_item("scope", "Confirm scope", "Resolve focused papers and project constraints.", status_by_step["scope"]),
        _plan_item("retrieve", "Collect evidence", f"Retrieve reusable evidence from {len(paper_ids)} project papers.", status_by_step["retrieve"]),
        _plan_item("synthesize", "Judge and compare", "Build cross-paper judgements, conflict candidates, and a draft report.", status_by_step["synthesize"]),
    ]


def _build_planning_context(project: Dict[str, Any], paper_ids: List[str], constraints: str) -> str:
    parts = [
        f"project={project.get('title')}",
        f"goal={project.get('goal')}",
        f"paper_count={len(paper_ids)}",
    ]
    if constraints:
        parts.append(f"constraints={constraints}")
    return "\n".join(parts)


def _copy_project(project_id: str) -> Dict[str, Any]:
    _ensure_storage_loaded()
    with _LOCK:
        project = _PROJECTS.get(project_id)
        if project is None:
            raise AgentProjectNotFoundError("Agent project not found.")
        return copy.deepcopy(project)


def _copy_task(task_id: str) -> Dict[str, Any]:
    _ensure_storage_loaded()
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise AgentTaskNotFoundError("Agent task not found.")
        return copy.deepcopy(task)


def _list_project_tasks(project_id: str) -> List[Dict[str, Any]]:
    normalized_project_id = _clean_text(project_id)
    with _LOCK:
        tasks = [
            copy.deepcopy(task)
            for task in _TASKS.values()
            if _clean_text(task.get("projectId")) == normalized_project_id
        ]
    tasks.sort(
        key=lambda item: str(item.get("updatedAt") or item.get("createdAt") or ""),
        reverse=True,
    )
    return tasks


def _update_task(task_id: str, **updates: Any) -> Dict[str, Any]:
    _ensure_storage_loaded()
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise AgentTaskNotFoundError("Agent task not found.")
        if task.get("status") == "cancelled" and updates.get("status") != "cancelled":
            return copy.deepcopy(task)
        next_task = {**task, **copy.deepcopy(updates), "updatedAt": _utc_now()}
        _TASKS[task_id] = next_task
        _persist_task_locked(next_task)
        return copy.deepcopy(next_task)


def _plan_item(item_id: str, label: str, detail: str, status: str) -> Dict[str, Any]:
    return {"id": item_id, "label": label, "detail": detail, "status": status}


def _event(event_type: str, task_id: str, stage: str, summary: str) -> Dict[str, Any]:
    return {
        "eventId": str(uuid.uuid4()),
        "type": event_type,
        "timestamp": _utc_now(),
        "taskId": task_id,
        "stage": stage,
        "summary": summary,
        "meta": {},
    }


def _paper_stub(pdf_id: str) -> Dict[str, Any]:
    return {"pdfId": pdf_id, "title": pdf_id, "indexed": True}


def _is_task_cancelled(task_id: str) -> bool:
    try:
        return _copy_task(task_id).get("status") == "cancelled"
    except AgentTaskNotFoundError:
        return True


def _agent_step_delay() -> None:
    time.sleep(AGENT_STEP_DELAY_SECONDS)


def _normalize_id_list(value: Any) -> List[str]:
    raw_items = value if isinstance(value, list) else []
    items: List[str] = []
    seen = set()
    for raw_item in raw_items:
        text = _clean_text(raw_item)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _normalize_history_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return 20
    if limit <= 0:
        return 20
    return min(limit, 100)


def _normalize_run_request(value: AgentRunCreateRequest | AgentTaskCreateRequest | Dict[str, Any]) -> AgentRunCreateRequest:
    if isinstance(value, AgentRunCreateRequest):
        return value
    if isinstance(value, AgentTaskCreateRequest):
        return AgentRunCreateRequest(
            prompt=value.prompt,
            focusedPaperIds=value.focusedPaperIds,
            constraints=value.constraints,
            context=value.context,
            allowExternalSearch=value.allowExternalSearch,
            allowCodeExecution=getattr(value, "allowCodeExecution", False),
        )
    payload = value if isinstance(value, dict) else {}
    return AgentRunCreateRequest.model_validate(payload)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _ensure_storage_loaded() -> None:
    global _STORAGE_LOADED
    with _LOCK:
        if _STORAGE_LOADED:
            return
        _initialize_storage_locked()
        loaded_projects, loaded_tasks = _load_persisted_state_locked()
        _PROJECTS.clear()
        _TASKS.clear()
        for project in loaded_projects:
            project_id = _clean_text(project.get("projectId"))
            if project_id:
                _PROJECTS[project_id] = project
        for task in loaded_tasks:
            restored = _restore_task_after_restart(task)
            task_id = _clean_text(restored.get("taskId"))
            if task_id:
                _TASKS[task_id] = restored
                if restored is not task:
                    _persist_task_locked(restored)
        _STORAGE_LOADED = True


def _restore_task_after_restart(task: Dict[str, Any]) -> Dict[str, Any]:
    status = _clean_text(task.get("status"))
    if status in TERMINAL_STATUSES or status in {"awaiting_plan_review", "awaiting_final_review", "awaiting_tool_approval", "awaiting_clarification"}:
        return task
    task_id = _clean_text(task.get("taskId"))

    # Queued tasks survive restarts — re-enqueue for background execution
    if status == "queued":
        events = list(task.get("events") or [])
        events.append(_event("task_recovered", task_id, "queued", "Task recovered after service restart and re-queued for execution."))
        recovered = {
            **task,
            "status": "queued",
            "events": events,
            "updatedAt": _utc_now(),
        }
        # Schedule recovery in background to avoid blocking state reload
        import threading
        threading.Thread(target=lambda: _recover_queued_task(task_id), daemon=True).start()
        return recovered

    events = list(task.get("events") or [])
    if not events or events[-1].get("type") != "task_expired":
        events.append(_event("task_expired", task_id, DONE_STAGE, INTERRUPTED_RESTART_ERROR))
    return {
        **task,
        "status": "failed",
        "stage": DONE_STAGE,
        "progress": 1.0,
        "events": events,
        "error": INTERRUPTED_RESTART_ERROR,
        "updatedAt": _utc_now(),
    }


def _recover_queued_task(task_id: str) -> None:
    """Re-enqueue a task that was queued before restart, with a short delay for state stabilization."""
    import time
    time.sleep(2.0)  # Allow state reload to complete
    try:
        task = _copy_task(task_id)
        if _clean_text(task.get("status")) != "queued":
            return
        _start_agent_worker(_run_minimal_agent_task, task_id)
    except (AgentProjectNotFoundError, AgentTaskNotFoundError):
        pass


def _build_agent_review_risks(conflicts: List[Dict[str, Any]], open_questions: List[str]) -> List[Dict[str, Any]]:
    risks = [
        {"riskId": f"conflict:{item.get('id') or index}", "type": "conflict", "label": "冲突候选", "detail": _clean_text(item.get("claim") or item.get("summary")), "sourceIds": list(item.get("sourceIds") or []), "reviewStatus": "pending"}
        for index, item in enumerate(conflicts, 1)
    ]
    risks.extend(
        {"riskId": f"open:{index}", "type": "open_question", "label": "开放问题", "detail": _clean_text(question), "sourceIds": [], "reviewStatus": "pending"}
        for index, question in enumerate(open_questions, 1)
    )
    return risks


def _validate_agent_risk_reviews(risks: List[Dict[str, Any]], reviews: List[Any]) -> List[Dict[str, Any]]:
    allowed = {_clean_text(item.get("riskId")) for item in risks}
    normalized = []
    for item in reviews:
        risk_id = _clean_text(getattr(item, "riskId", ""))
        status = _clean_text(getattr(item, "reviewStatus", ""))
        if risk_id not in allowed or status not in {"reviewed", "needs_follow_up"}:
            raise ValueError("Invalid risk review.")
        normalized.append({"riskId": risk_id, "reviewStatus": status})
    return normalized


def _persist_trace_summary(task_id: str, trace_snapshot: Dict[str, Any] | None) -> None:
    if not trace_snapshot:
        return
    _update_task(task_id, traceSummary=build_public_trace_summary(trace_snapshot))


def _initialize_storage_locked() -> None:
    _get_agent_state_repository()


def _load_persisted_state_locked() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    repository = _get_agent_state_repository()
    projects = repository.list_projects()
    tasks = []
    for project in projects:
        project_id = _clean_text(project.get("projectId"))
        for run in repository.list_runs(project_id):
            run_id = _clean_text(run.get("runId"))
            try:
                plan_review = repository.get_plan_review(run_id)
            except KeyError:
                plan_review = None
            try:
                final_review = repository.get_final_review(run_id)
            except KeyError:
                final_review = None
            try:
                artifacts = repository.get_artifacts(run_id)
            except KeyError:
                artifacts = None
            timeline = repository.list_timeline(run_id)
            tasks.append(
                _build_task_snapshot_from_resources(
                    project=project,
                    run=run,
                    plan_review=plan_review,
                    final_review=final_review,
                    artifacts=artifacts,
                    timeline=timeline,
                )
            )
    return projects, tasks


def _persist_project_locked(project: Dict[str, Any]) -> None:
    repository = _get_agent_state_repository()
    repository.save_project(_normalize_project_for_storage(project))


def _persist_task_locked(task: Dict[str, Any]) -> None:
    repository = _get_agent_state_repository()
    run_record = _build_run_record(task)
    repository.save_run(run_record)
    repository.save_artifacts(_build_artifacts_resource(task))
    timeline_entries = _build_timeline_resource(task)
    for entry in timeline_entries:
        repository.append_timeline_entry(
            {
                "runId": run_record["runId"],
                **entry,
            }
        )
    if task.get("status") == "awaiting_plan_review":
        repository.save_plan_review(_build_pending_review_record(task) or {"runId": run_record["runId"]})
    else:
        repository.save_plan_review({"runId": run_record["runId"], "status": "approved", "planItems": list(task.get("planItems") or []), "focusedPaperIds": list(task.get("focusedPaperIds") or []), "constraints": str(task.get("constraints") or ""), "reviewNotes": str(((task.get("humanReview") or {}).get("plan") or {}).get("reviewNotes") or ""), "reviewedAt": str(((task.get("humanReview") or {}).get("plan") or {}).get("reviewedAt") or ""), "version": 1})
    if task.get("status") == "awaiting_final_review":
        repository.save_final_review(_build_pending_review_record(task) or {"runId": run_record["runId"]})
    else:
        repository.save_final_review({"runId": run_record["runId"], "status": str(((task.get("humanReview") or {}).get("final") or {}).get("status") or "pending"), "summary": str(task.get("draftReport") or ""), "riskItems": list(task.get("reviewRisks") or []), "reviewNotes": str(((task.get("humanReview") or {}).get("final") or {}).get("reviewNotes") or ""), "reviewedAt": str(((task.get("humanReview") or {}).get("final") or {}).get("reviewedAt") or ""), "version": 1})


def _delete_persisted_project_locked(project_id: str) -> None:
    repository = _get_agent_state_repository()
    repository.delete_project(project_id)


def _delete_persisted_state_locked() -> None:
    repository = _get_agent_state_repository()
    repository.clear()


def _project_from_storage_row(row: sqlite3.Row) -> Dict[str, Any]:
    created_at = str(row["createdAt"] or _utc_now())
    updated_at = str(row["updatedAt"] or created_at)
    paper_ids = _safe_json_list(row["paperIds"])
    papers = _safe_json_list(row["papers"]) or [_paper_stub(pdf_id) for pdf_id in paper_ids]
    return {
        "projectId": str(row["projectId"] or ""),
        "title": str(row["title"] or "Agent Research Project"),
        "goal": str(row["goal"] or ""),
        "paperIds": paper_ids,
        "papers": papers,
        "latestTaskId": str(row["latestTaskId"] or ""),
        "defaultConstraints": str(row["defaultConstraints"] or ""),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def _task_from_storage_row(row: sqlite3.Row, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    created_at = str(row["createdAt"] or _utc_now())
    updated_at = str(row["updatedAt"] or created_at)
    return {
        "taskId": str(row["taskId"] or ""),
        "projectId": str(row["projectId"] or ""),
        "traceId": str(row["traceId"] or ""),
        "status": str(row["status"] or "failed"),
        "stage": str(row["stage"] or DONE_STAGE),
        "progress": float(row["progress"] or 0.0),
        "prompt": str(row["prompt"] or ""),
        "focusedPaperIds": _safe_json_list(row["focusedPaperIds"]),
        "constraints": str(row["constraints"] or ""),
        "context": _safe_json_dict(row["context"]),
        "planItems": _safe_json_list(row["planItems"]),
        "events": events,
        "toolCalls": _safe_json_list(row["toolCalls"]),
        "evidenceItems": _safe_json_list(row["evidenceItems"]),
        "findings": _safe_json_list(row["findings"]),
        "comparisonTable": _safe_json_dict(row["comparisonTable"]) or {"columns": [], "rows": []},
        "conflicts": _safe_json_list(row["conflicts"]),
        "openQuestions": _safe_json_list(row["openQuestions"]),
        "reviewRisks": _safe_json_list(row["reviewRisks"]) if "reviewRisks" in row.keys() else [],
        "humanReview": _safe_json_dict(row["humanReview"]) if "humanReview" in row.keys() else {},
        "traceSummary": _safe_json_dict(row["traceSummary"]) if "traceSummary" in row.keys() else {},
        "externalSearchConfig": _safe_json_dict(row["externalSearchConfig"]) if "externalSearchConfig" in row.keys() else {},
        "codeExecutionConfig": _safe_json_dict(row["codeExecutionConfig"]) if "codeExecutionConfig" in row.keys() else {},
        "draftReport": str(row["draftReport"] or ""),
        "error": str(row["error"] or ""),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def _event_from_storage_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "eventId": str(row["eventId"] or ""),
        "type": str(row["type"] or ""),
        "timestamp": str(row["timestamp"] or ""),
        "taskId": str(row["taskId"] or ""),
        "stage": str(row["stage"] or ""),
        "summary": str(row["summary"] or ""),
        "meta": _safe_json_dict(row["meta"]),
    }


def _normalize_project_for_storage(project: Dict[str, Any]) -> Dict[str, Any]:
    now = _utc_now()
    paper_ids = _normalize_id_list(project.get("paperIds"))
    return {
        "projectId": _clean_text(project.get("projectId")),
        "title": _clean_text(project.get("title")) or "Agent Research Project",
        "goal": _clean_text(project.get("goal")),
        "paperIds": paper_ids,
        "papers": list(project.get("papers") or [_paper_stub(pdf_id) for pdf_id in paper_ids]),
        "latestTaskId": _clean_text(project.get("latestTaskId")),
        "defaultConstraints": _clean_text(project.get("defaultConstraints")),
        "createdAt": str(project.get("createdAt") or now),
        "updatedAt": str(project.get("updatedAt") or project.get("createdAt") or now),
    }


def _normalize_task_for_storage(task: Dict[str, Any]) -> Dict[str, Any]:
    now = _utc_now()
    created_at = str(task.get("createdAt") or now)
    return {
        "taskId": _clean_text(task.get("taskId")),
        "projectId": _clean_text(task.get("projectId")),
        "traceId": _clean_text(task.get("traceId")),
        "status": _clean_text(task.get("status")) or "running",
        "stage": _clean_text(task.get("stage")) or PLANNING_STAGE,
        "progress": float(task.get("progress") or 0.0),
        "prompt": _clean_text(task.get("prompt")),
        "focusedPaperIds": _normalize_id_list(task.get("focusedPaperIds")),
        "constraints": _clean_text(task.get("constraints")),
        "context": dict(task.get("context") or {}),
        "planItems": list(task.get("planItems") or []),
        "events": [_normalize_event_for_storage(event, _clean_text(task.get("taskId"))) for event in list(task.get("events") or [])],
        "toolCalls": list(task.get("toolCalls") or []),
        "evidenceItems": list(task.get("evidenceItems") or []),
        "findings": list(task.get("findings") or []),
        "comparisonTable": dict(task.get("comparisonTable") or {"columns": [], "rows": []}),
        "conflicts": list(task.get("conflicts") or []),
        "openQuestions": list(task.get("openQuestions") or []),
        "reviewRisks": list(task.get("reviewRisks") or []),
        "humanReview": dict(task.get("humanReview") or {}),
        "traceSummary": dict(task.get("traceSummary") or {}),
        "externalSearchConfig": dict(task.get("externalSearchConfig") or {}),
        "codeExecutionConfig": dict(task.get("codeExecutionConfig") or {}),
        "draftReport": str(task.get("draftReport") or ""),
        "error": _clean_text(task.get("error")),
        "createdAt": created_at,
        "updatedAt": str(task.get("updatedAt") or created_at),
    }


def _normalize_event_for_storage(event: Dict[str, Any], fallback_task_id: str) -> Dict[str, Any]:
    return {
        "eventId": _clean_text(event.get("eventId")) or str(uuid.uuid4()),
        "type": _clean_text(event.get("type")),
        "timestamp": _clean_text(event.get("timestamp")) or _utc_now(),
        "taskId": _clean_text(event.get("taskId")) or fallback_task_id,
        "stage": _clean_text(event.get("stage")),
        "summary": _clean_text(event.get("summary")),
        "meta": dict(event.get("meta") or {}),
    }


def _safe_json_list(value: Any) -> List[Any]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _safe_json_dict(value: Any) -> Dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _agent_state_db_path() -> Path:
    configured = os.environ.get("AGENT_STATE_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "agent_state.sqlite3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

