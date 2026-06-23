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
    AgentTaskCreateRequest,
)
from services import agent_orchestrator
from services.evidence_service import normalize_evidence_items
from services.tool_registry import get_tool_registry
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


class AgentProjectNotFoundError(Exception):
    pass


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


def create_agent_task(project_id: str, request: AgentTaskCreateRequest) -> Dict[str, Any]:
    _ensure_storage_loaded()
    project = _copy_project(project_id)
    prompt = _clean_text(request.prompt)
    if not prompt:
        raise ValueError("Prompt cannot be empty.")
    focused_paper_ids = _normalize_id_list(request.focusedPaperIds) or list(project.get("paperIds") or [])
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
        "constraints": _clean_text(request.constraints),
        "context": dict(request.context or {}),
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
    return {"status": "success", "task": _copy_task(task_id)}


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
    task = _copy_task(task_id)
    if task.get("status") != "awaiting_plan_review":
        if task.get("status") in {"running", "awaiting_final_review", "succeeded"}:
            return {"status": "success", "task": task}
        raise AgentReviewConflictError("Agent task is not awaiting plan review.")
    project = _copy_project(str(task.get("projectId") or ""))
    paper_ids = _normalize_id_list(request.focusedPaperIds)
    if not paper_ids or any(item not in (project.get("paperIds") or []) for item in paper_ids):
        raise ValueError("focusedPaperIds must reference papers in the project.")
    plan_items = agent_orchestrator.normalize_review_plan_items([item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in request.planItems])
    if not plan_items:
        raise ValueError("At least one valid Agent plan item is required.")
    human_review = copy.deepcopy(task.get("humanReview") or {})
    human_review["plan"] = {"status": "approved", "reviewNotes": _clean_text(request.reviewNotes), "reviewedAt": _utc_now()}
    updated = _update_task(task_id, status="running", focusedPaperIds=paper_ids, constraints=_clean_text(request.constraints), planItems=plan_items, humanReview=human_review)
    _start_agent_worker(_run_minimal_agent_task, task_id)
    return {"status": "success", "task": updated}


def review_agent_final(task_id: str, request: AgentFinalReviewRequest) -> Dict[str, Any]:
    task = _copy_task(task_id)
    if task.get("status") == "succeeded":
        return {"status": "success", "task": task}
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
    return {"status": "success", "task": _copy_task(task_id)}


def get_latest_agent_task(project_id: str) -> Dict[str, Any]:
    project = _copy_project(project_id)
    task_id = _clean_text(project.get("latestTaskId"))
    if not task_id:
        raise AgentTaskNotFoundError("Agent task not found.")
    return {"status": "success", "task": _copy_task(task_id)}


def list_agent_project_tasks(project_id: str, limit: Any = 20) -> Dict[str, Any]:
    project = _copy_project(project_id)
    normalized_project_id = _clean_text(project.get("projectId"))
    normalized_limit = _normalize_history_limit(limit)
    with _LOCK:
        tasks = [
            copy.deepcopy(task)
            for task in _TASKS.values()
            if _clean_text(task.get("projectId")) == normalized_project_id
        ]
    tasks.sort(key=lambda item: str(item.get("updatedAt") or item.get("createdAt") or ""), reverse=True)
    return {
        "status": "success",
        "projectId": normalized_project_id,
        "tasks": tasks[:normalized_limit],
        "limit": normalized_limit,
    }


def get_agent_task(task_id: str) -> Dict[str, Any]:
    return {"status": "success", "task": _copy_task(task_id)}


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

            paper_contexts, tool_calls, evidence_items = agent_orchestrator.collect_project_evidence(
                execution_prompt,
                paper_ids,
                should_cancel=lambda: _is_task_cancelled(task_id),
                on_progress=update_retrieval_progress,
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


def _build_minimal_report(
    prompt: str,
    project: Dict[str, Any],
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    open_questions: List[str],
) -> str:
    paper_lines = "\n".join(_build_scope_lines(paper_contexts)) or "- No project papers selected"
    evidence_lines = "\n".join(_build_evidence_snapshot_lines(evidence_items)) or "- No evidence snippets yet"
    conclusion_lines = "\n".join(_build_conclusion_lines(prompt, paper_contexts, evidence_items))
    question_lines = "\n".join(f"- {item}" for item in open_questions[:4]) or "- None"
    conflict_lines = "\n".join(_build_conflict_lines(conflicts)) or "- No strong conflict candidates detected in this pass"
    return (
        "# Agent Research Draft\n\n"
        f"## Task\n{prompt}\n\n"
        f"## Project\n{project.get('title')}\n\n"
        f"## Scope\n{paper_lines}\n\n"
        "## Evidence Snapshot\n"
        f"{evidence_lines}\n\n"
        "## Current Conclusion\n"
        f"{conclusion_lines}\n\n"
        "## Conflict Candidates\n"
        f"{conflict_lines}\n\n"
        "## Open Questions\n"
        f"{question_lines}\n"
    )


def _build_finding_summary(prompt: str, paper_contexts: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> str:
    paper_count = len(paper_contexts)
    evidence_count = len(evidence_items)
    support_profiles = _build_paper_support_profiles(paper_contexts, evidence_items)
    if support_profiles:
        support_text = "; ".join(
            f"{item['pdfId']} has {item['evidenceCount']} snippets focused on {item['theme']}"
            for item in support_profiles[:3]
        )
        return (
            f"For '{prompt}', the Agent synthesized {evidence_count} normalized evidence items across {paper_count} papers. "
            f"The strongest current support is: {support_text}."
        )
    return (
        f"For '{prompt}', the Agent workspace has completed the end-to-end project chain across {paper_count} papers, "
        f"but the evidence set is still sparse and should be strengthened in later rounds."
    )


def _evidence_preview(evidence_items: List[Dict[str, Any]]) -> str:
    snippets = []
    for item in evidence_items[:2]:
        text = _clean_text(item.get("text"))
        if text:
            snippets.append(text[:80])
    return " | ".join(snippets)


def _stabilize_source_ids(items: List[Dict[str, Any]], fallback_prefix: str) -> List[Dict[str, Any]]:
    stabilized = []
    for index, item in enumerate(items):
        current = copy.deepcopy(item)
        source_id = _clean_text(current.get("sourceId"))
        if not source_id:
            source_id = f"{fallback_prefix}-source-{index + 1}"
        current["sourceId"] = source_id[:80]
        stabilized.append(current)
    return stabilized


def _build_paper_judgement(paper_context: Dict[str, Any]) -> str:
    evidence_count = int(paper_context.get("evidenceCount") or 0)
    status = _clean_text(paper_context.get("status")) or "unknown"
    if evidence_count >= 3 and status == "succeeded":
        return "Evidence is dense enough for cross-paper judgement."
    if evidence_count >= 1:
        return "Evidence is usable, but section coverage is still uneven."
    return "Evidence is too sparse for a confident judgement."


def _build_scope_lines(paper_contexts: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for item in paper_contexts:
        pdf_id = _clean_text(item.get("pdfId")) or "unknown-paper"
        evidence_count = int(item.get("evidenceCount") or 0)
        preview = _clean_text(item.get("preview"))[:120]
        preview_suffix = f" Preview: {preview}" if preview else ""
        lines.append(f"- `{pdf_id}`: {evidence_count} evidence snippets.{preview_suffix}")
    return lines


def _build_evidence_snapshot_lines(evidence_items: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for item in evidence_items[:6]:
        pdf_id = _clean_text(item.get("pdfId")) or "unknown-paper"
        section_id = _clean_text(item.get("sectionId")) or "unknown-section"
        text = _clean_text(item.get("text"))[:160]
        lines.append(f"- `{pdf_id}` / `{section_id}`: {text}")
    return lines


def _build_paper_support_profiles(
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in evidence_items:
        pdf_id = _clean_text(item.get("pdfId"))
        if not pdf_id:
            continue
        grouped.setdefault(pdf_id, []).append(item)

    profiles = []
    for paper_context in paper_contexts:
        pdf_id = _clean_text(paper_context.get("pdfId"))
        evidence_for_paper = grouped.get(pdf_id, [])
        profiles.append(
            {
                "pdfId": pdf_id,
                "evidenceCount": int(paper_context.get("evidenceCount") or len(evidence_for_paper)),
                "theme": _infer_theme_from_evidence(evidence_for_paper),
                "status": _clean_text(paper_context.get("status")) or "unknown",
            }
        )
    return sorted(profiles, key=lambda item: item["evidenceCount"], reverse=True)


def _build_conclusion_lines(
    prompt: str,
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[str]:
    if not paper_contexts:
        return ["- No project papers are attached yet, so a project-level conclusion cannot be formed."]

    profiles = _build_paper_support_profiles(paper_contexts, evidence_items)
    strongest = [item for item in profiles if item["evidenceCount"] >= 2]
    sparse = [item for item in profiles if item["evidenceCount"] <= 1]
    fallback = [item for item in profiles if item["status"] == "fallback"]
    common_themes = _extract_common_themes(profiles)

    lines = []
    if strongest:
        top_summary = "; ".join(
            f"`{item['pdfId']}` mainly surfaces {item['theme']}"
            for item in strongest[:3]
        )
        lines.append(f"- For '{prompt}', the best-supported current conclusion comes from {top_summary}.")

    if common_themes:
        lines.append(
            "- Across the current evidence, the recurring discussion centers on "
            + ", ".join(common_themes[:4])
            + "."
        )

    if strongest and sparse:
        lines.append(
            "- The comparison is already directionally useful, but it is still imbalanced because some papers have much denser evidence than others."
        )
    elif strongest:
        lines.append(
            "- The retrieved evidence is strong enough to support a first-pass comparison, especially on papers with denser method and experiment snippets."
        )
    else:
        lines.append(
            "- The current evidence mostly supports a scoping conclusion rather than a strong claim about methodological differences."
        )

    if fallback:
        fallback_text = ", ".join(f"`{item['pdfId']}`" for item in fallback[:3])
        lines.append(
            f"- Some conclusions remain provisional because {fallback_text} is still using fallback evidence rather than indexed retrieval."
        )

    return lines


def _build_conflict_lines(conflicts: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for item in conflicts[:4]:
        severity = _clean_text(item.get("severity")) or "unknown"
        summary = _clean_text(item.get("summary"))
        claim = _clean_text(item.get("claim"))
        papers = [paper for paper in item.get("papers") or [] if _clean_text(paper)]
        paper_text = f" Papers: {', '.join(papers[:4])}." if papers else ""
        claim_text = f" Claim: {claim}." if claim else ""
        lines.append(f"- [{severity}] {summary}{claim_text}{paper_text}")
    return lines


def _infer_theme_from_evidence(evidence_items: List[Dict[str, Any]]) -> str:
    if not evidence_items:
        return "limited evidence"

    section_ids = [
        _clean_text(item.get("sectionId")).lower()
        for item in evidence_items
        if _clean_text(item.get("sectionId"))
    ]
    for preferred in ("method", "experiment", "results", "discussion", "conclusion"):
        if preferred in section_ids:
            return preferred

    joined = " ".join(_clean_text(item.get("text")) for item in evidence_items[:4])
    keywords = _extract_keywords(joined)
    if keywords:
        return ", ".join(keywords[:2])
    return "paper-level evidence"


def _extract_common_themes(profiles: List[Dict[str, Any]]) -> List[str]:
    counts: Dict[str, int] = {}
    for profile in profiles:
        for part in [item.strip() for item in str(profile.get("theme") or "").split(",")]:
            if not part or part == "limited evidence":
                continue
            counts[part] = counts.get(part, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [item[0] for item in ordered]


def _extract_keywords(text: str) -> List[str]:
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "into", "about", "their",
        "method", "methods", "result", "results", "paper", "study", "using", "used",
        "shows", "show", "based", "current", "evidence", "section", "discussion",
    }
    counts: Dict[str, int] = {}
    for token in re.findall(r"[a-zA-Z][a-zA-Z_-]{3,}", text.lower()):
        if token in stopwords:
            continue
        counts[token] = counts.get(token, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [item[0].replace("_", " ").replace("-", " ") for item in ordered[:5]]


def _detect_conflicts(paper_contexts: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(paper_contexts) < 2:
        return []

    conflicts: List[Dict[str, Any]] = []
    sparse = [item for item in paper_contexts if int(item.get("evidenceCount") or 0) <= 1]
    strong = [item for item in paper_contexts if int(item.get("evidenceCount") or 0) >= 3]
    fallback_contexts = [item for item in paper_contexts if item.get("status") == "fallback"]

    if sparse and strong:
        conflicts.append(
            {
                "id": "evidence-coverage-conflict",
                "severity": "medium",
                "claim": "Cross-paper conclusion may over-weight papers with denser retrieved evidence.",
                "papers": [*(item.get("pdfId") for item in strong[:2]), *(item.get("pdfId") for item in sparse[:2])],
                "summary": "Some papers have strong evidence coverage while others are sparse, so the comparison should separate evidence strength from actual methodological differences.",
                "sourceIds": [item.get("sourceId") for item in evidence_items[:6] if item.get("sourceId")],
                "resolutionHint": "Retrieve additional method, experiment, and limitation sections for sparse papers before making a high-confidence claim.",
            }
        )

    if fallback_contexts:
        conflicts.append(
            {
                "id": "retrieval-fallback-conflict",
                "severity": "high",
                "claim": "At least one paper is using fallback evidence rather than indexed retrieval.",
                "papers": [item.get("pdfId") for item in fallback_contexts],
                "summary": "Fallback evidence can keep the workflow moving, but it should not be treated as equally reliable as indexed paper evidence.",
                "sourceIds": [item.get("sourceId") for item in evidence_items if item.get("metadata", {}).get("fallback")][:6],
                "resolutionHint": "Re-index or re-upload the affected papers, then rerun the Agent task.",
            }
        )

    if not conflicts:
        conflicts.append(
            {
                "id": "no-major-conflict",
                "severity": "low",
                "claim": "No major conflict candidate was detected in the lightweight pass.",
                "papers": [item.get("pdfId") for item in paper_contexts[:4]],
                "summary": "The current evidence does not expose a clear contradiction; later rounds can add claim extraction and contradiction scoring.",
                "sourceIds": [item.get("sourceId") for item in evidence_items[:6] if item.get("sourceId")],
                "resolutionHint": "Use this as a process marker, not a final absence-of-conflict judgement.",
            }
        )

    return conflicts[:4]


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
    if status in TERMINAL_STATUSES or status in {"awaiting_plan_review", "awaiting_final_review"}:
        return task
    task_id = _clean_text(task.get("taskId"))
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
    db_path = _agent_state_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_projects (
                projectId TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                goal TEXT NOT NULL,
                paperIds TEXT NOT NULL,
                papers TEXT NOT NULL,
                latestTaskId TEXT NOT NULL,
                defaultConstraints TEXT NOT NULL,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_tasks (
                taskId TEXT PRIMARY KEY,
                projectId TEXT NOT NULL,
                traceId TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress REAL NOT NULL,
                prompt TEXT NOT NULL,
                focusedPaperIds TEXT NOT NULL,
                constraints TEXT NOT NULL,
                context TEXT NOT NULL,
                planItems TEXT NOT NULL,
                toolCalls TEXT NOT NULL,
                evidenceItems TEXT NOT NULL,
                findings TEXT NOT NULL,
                comparisonTable TEXT NOT NULL,
                conflicts TEXT NOT NULL,
                openQuestions TEXT NOT NULL,
                reviewRisks TEXT NOT NULL DEFAULT '[]',
                humanReview TEXT NOT NULL DEFAULT '{}',
                traceSummary TEXT NOT NULL DEFAULT '{}',
                draftReport TEXT NOT NULL,
                error TEXT NOT NULL,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_task_events (
                eventId TEXT PRIMARY KEY,
                taskId TEXT NOT NULL,
                type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                stage TEXT NOT NULL,
                summary TEXT NOT NULL,
                meta TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_tasks)").fetchall()}
        if "reviewRisks" not in columns:
            connection.execute("ALTER TABLE agent_tasks ADD COLUMN reviewRisks TEXT NOT NULL DEFAULT '[]'")
        if "humanReview" not in columns:
            connection.execute("ALTER TABLE agent_tasks ADD COLUMN humanReview TEXT NOT NULL DEFAULT '{}'")
        if "traceSummary" not in columns:
            connection.execute("ALTER TABLE agent_tasks ADD COLUMN traceSummary TEXT NOT NULL DEFAULT '{}'")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_projects_updated ON agent_projects (updatedAt)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_project_updated ON agent_tasks (projectId, updatedAt)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_task_events_task_time ON agent_task_events (taskId, timestamp)")
        connection.commit()


def _load_persisted_state_locked() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    db_path = _agent_state_db_path()
    if not db_path.exists():
        return [], []
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        project_rows = connection.execute("SELECT * FROM agent_projects ORDER BY createdAt ASC").fetchall()
        task_rows = connection.execute("SELECT * FROM agent_tasks ORDER BY createdAt ASC").fetchall()
        event_rows = connection.execute("SELECT * FROM agent_task_events ORDER BY timestamp ASC").fetchall()

    events_by_task: Dict[str, List[Dict[str, Any]]] = {}
    for row in event_rows:
        event = _event_from_storage_row(row)
        events_by_task.setdefault(event["taskId"], []).append(event)

    projects = [_project_from_storage_row(row) for row in project_rows]
    tasks = [_task_from_storage_row(row, events_by_task.get(str(row["taskId"] or ""), [])) for row in task_rows]
    return projects, tasks


def _persist_project_locked(project: Dict[str, Any]) -> None:
    _initialize_storage_locked()
    snapshot = _normalize_project_for_storage(project)
    with closing(sqlite3.connect(_agent_state_db_path())) as connection:
        connection.execute(
            """
            INSERT INTO agent_projects (
                projectId, title, goal, paperIds, papers, latestTaskId,
                defaultConstraints, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(projectId) DO UPDATE SET
                title=excluded.title,
                goal=excluded.goal,
                paperIds=excluded.paperIds,
                papers=excluded.papers,
                latestTaskId=excluded.latestTaskId,
                defaultConstraints=excluded.defaultConstraints,
                createdAt=excluded.createdAt,
                updatedAt=excluded.updatedAt
            """,
            (
                snapshot["projectId"],
                snapshot["title"],
                snapshot["goal"],
                json.dumps(snapshot["paperIds"], ensure_ascii=False),
                json.dumps(snapshot["papers"], ensure_ascii=False),
                snapshot["latestTaskId"],
                snapshot["defaultConstraints"],
                snapshot["createdAt"],
                snapshot["updatedAt"],
            ),
        )
        connection.commit()


def _persist_task_locked(task: Dict[str, Any]) -> None:
    _initialize_storage_locked()
    snapshot = _normalize_task_for_storage(task)
    with closing(sqlite3.connect(_agent_state_db_path())) as connection:
        connection.execute(
            """
            INSERT INTO agent_tasks (
                taskId, projectId, traceId, status, stage, progress, prompt,
                focusedPaperIds, constraints, context, planItems, toolCalls,
                evidenceItems, findings, comparisonTable, conflicts, openQuestions,
                reviewRisks, humanReview, traceSummary, draftReport, error, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(taskId) DO UPDATE SET
                projectId=excluded.projectId,
                traceId=excluded.traceId,
                status=excluded.status,
                stage=excluded.stage,
                progress=excluded.progress,
                prompt=excluded.prompt,
                focusedPaperIds=excluded.focusedPaperIds,
                constraints=excluded.constraints,
                context=excluded.context,
                planItems=excluded.planItems,
                toolCalls=excluded.toolCalls,
                evidenceItems=excluded.evidenceItems,
                findings=excluded.findings,
                comparisonTable=excluded.comparisonTable,
                conflicts=excluded.conflicts,
                openQuestions=excluded.openQuestions,
                reviewRisks=excluded.reviewRisks,
                humanReview=excluded.humanReview,
                traceSummary=excluded.traceSummary,
                draftReport=excluded.draftReport,
                error=excluded.error,
                createdAt=excluded.createdAt,
                updatedAt=excluded.updatedAt
            """,
            (
                snapshot["taskId"],
                snapshot["projectId"],
                snapshot["traceId"],
                snapshot["status"],
                snapshot["stage"],
                snapshot["progress"],
                snapshot["prompt"],
                json.dumps(snapshot["focusedPaperIds"], ensure_ascii=False),
                snapshot["constraints"],
                json.dumps(snapshot["context"], ensure_ascii=False),
                json.dumps(snapshot["planItems"], ensure_ascii=False),
                json.dumps(snapshot["toolCalls"], ensure_ascii=False),
                json.dumps(snapshot["evidenceItems"], ensure_ascii=False),
                json.dumps(snapshot["findings"], ensure_ascii=False),
                json.dumps(snapshot["comparisonTable"], ensure_ascii=False),
                json.dumps(snapshot["conflicts"], ensure_ascii=False),
                json.dumps(snapshot["openQuestions"], ensure_ascii=False),
                json.dumps(snapshot["reviewRisks"], ensure_ascii=False),
                json.dumps(snapshot["humanReview"], ensure_ascii=False),
                json.dumps(snapshot["traceSummary"], ensure_ascii=False),
                snapshot["draftReport"],
                snapshot["error"],
                snapshot["createdAt"],
                snapshot["updatedAt"],
            ),
        )
        connection.execute("DELETE FROM agent_task_events WHERE taskId = ?", (snapshot["taskId"],))
        for event in snapshot["events"]:
            connection.execute(
                """
                INSERT INTO agent_task_events (
                    eventId, taskId, type, timestamp, stage, summary, meta
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["eventId"],
                    event["taskId"],
                    event["type"],
                    event["timestamp"],
                    event["stage"],
                    event["summary"],
                    json.dumps(event["meta"], ensure_ascii=False),
                ),
            )
        connection.commit()


def _delete_persisted_project_locked(project_id: str) -> None:
    _initialize_storage_locked()
    with closing(sqlite3.connect(_agent_state_db_path())) as connection:
        task_rows = connection.execute("SELECT taskId FROM agent_tasks WHERE projectId = ?", (project_id,)).fetchall()
        task_ids = [str(row[0] or "") for row in task_rows]
        for task_id in task_ids:
            connection.execute("DELETE FROM agent_task_events WHERE taskId = ?", (task_id,))
        connection.execute("DELETE FROM agent_tasks WHERE projectId = ?", (project_id,))
        connection.execute("DELETE FROM agent_projects WHERE projectId = ?", (project_id,))
        connection.commit()


def _delete_persisted_state_locked() -> None:
    _initialize_storage_locked()
    with closing(sqlite3.connect(_agent_state_db_path())) as connection:
        connection.execute("DELETE FROM agent_task_events")
        connection.execute("DELETE FROM agent_tasks")
        connection.execute("DELETE FROM agent_projects")
        connection.commit()


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

