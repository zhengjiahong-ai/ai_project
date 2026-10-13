import copy
import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from functools import wraps
from services.operation_control import OperationCancelled, cancellation_scope
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from rag.store import normalize_id

from schemas.requests import (
    ResearchFinalReviewRequest,
    ResearchPlanReviewRequest,
    ResearchTaskBriefPreviewRequest,
    ResearchTaskCreateRequest,
)
from services import research_aggregator, research_executor, research_planner
from services.evidence_service import format_evidence_context
from services.research_conflict import (
    _build_research_review_risks,
    _validate_risk_reviews,
)

# Functions extracted to research_task_results.py (23-2).
# Names that are overridden by module-level aliases below are NOT imported here.
from services.research_task_results import (
    _build_research_brief_preview,
    _clean_text,
    _compose_research_question,
    _load_current_paper_documents,
    _normalize_brief_preview,
    _normalize_missing_aspects,
    _stringify_paper_skeleton,
)
from services.safety_service import (
    wrap_untrusted_context,
)
from services.trace_service import (
    build_public_trace_summary,
    finalize_trace,
    get_trace_snapshot,
    record_metric,
    sanitize_text,
    start_trace,
    trace_step,
    use_trace,
)

_logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
PLANNING_STAGE = "planning"
RETRIEVING_STAGE = "retrieving"
JUDGING_STAGE = "judging"
SYNTHESIZING_STAGE = "synthesizing"
DONE_STAGE = "done"

_TASKS: dict[str, dict[str, Any]] = {}
_TASK_CONTEXTS: dict[str, dict[str, Any]] = {}
_TASK_CANCELLATIONS: set[str] = set()
_TASK_LOCK = threading.RLock()
_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_RUNNING_TASKS: dict[str, int] = {}
_STORAGE_LOADED = False
INTERRUPTED_RESTART_ERROR = "服务已重启，研究执行已中断。已保存的计划与结果保留，可继续未完成部分。"
MAX_DYNAMIC_FOLLOW_UPS = 1
MAX_RESEARCH_CONFLICTS = 5

class ResearchTaskNotFoundError(Exception):
    pass

class ResearchReviewConflictError(Exception):
    pass


def _tracked_execution(function):
    @wraps(function)
    def execute(task_id, *args, **kwargs):
        with _TASK_LOCK:
            if _is_cancelled(task_id):
                return _copy_task_snapshot(task_id)
            _RUNNING_TASKS[task_id] = _RUNNING_TASKS.get(task_id, 0) + 1
        try:
            with cancellation_scope(lambda: _is_cancelled(task_id)):
                return function(task_id, *args, **kwargs)
        except OperationCancelled:
            return _copy_task_snapshot(task_id)
        except Exception as error:
            if not _is_cancelled(task_id):
                _fail_task(task_id, "研究执行未完成，请保留已保存的计划与结果。")
            _logger.error("Research worker failed: %s", type(error).__name__)
            return _copy_task_snapshot(task_id)
        finally:
            with _TASK_LOCK:
                remaining = _RUNNING_TASKS.get(task_id, 1) - 1
                if remaining:
                    _RUNNING_TASKS[task_id] = remaining
                else:
                    _RUNNING_TASKS.pop(task_id, None)
                    if _is_cancelled(task_id):
                        _update_task_snapshot(task_id, status="cancelled", stage=DONE_STAGE)
    return execute

def create_research_task(
    request: ResearchTaskCreateRequest,
    start_async: bool = True,
) -> dict[str, Any]:
    _ensure_storage_loaded()
    question = " ".join(str(request.question or "").strip().split())
    pdf_id = " ".join(str(request.pdfId or "").strip().split())
    user_constraints = _clean_text(getattr(request, "userConstraints", ""))
    brief_preview = _normalize_brief_preview(getattr(request, "briefPreview", None), question=question, pdf_id=pdf_id)
    if not question:
        raise ValueError("Question cannot be empty.")
    if not pdf_id:
        raise ValueError("pdfId cannot be empty.")
    allowed_papers = request.allowedPaperIds
    if allowed_papers is not None:
        allowed_papers = list(dict.fromkeys(normalize_id(value) for value in allowed_papers))
        if normalize_id(pdf_id) not in allowed_papers:
            raise ValueError("Research primary paper is outside the material snapshot.")

    operation_key = request.operationKey
    task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "pixiu:research:" + operation_key)) if operation_key else str(uuid.uuid4())
    fingerprint = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if operation_key:
        with _TASK_LOCK:
            if task_id in _TASKS:
                if _TASK_CONTEXTS[task_id].get("operationFingerprint") != fingerprint:
                    raise ResearchReviewConflictError("Research request identity was reused with different input.")
                return {"status": "success", "task": copy.deepcopy(_TASKS[task_id])}
    trace_id = start_trace(
        "deep_research",
        request_meta={
            "question": sanitize_text(question, max_chars=120),
            "pdfId": sanitize_text(pdf_id, max_chars=80),
        },
        activate=False,
        initial_status="pending",
    )
    created_at = _utc_now()
    task = {
        "taskId": task_id,
        "traceId": trace_id,
        "status": "pending",
        "stage": PLANNING_STAGE,
        "progress": 0.0,
        "question": question,
        "pdfId": pdf_id,
        "plan": [],
        "findings": [],
        "conflicts": [],
        "reviewRisks": [],
        "humanReview": {"plan": {"status": "pending", "reviewNotes": "", "reviewedAt": ""}, "final": {"status": "pending", "reviewNotes": "", "reviewedAt": "", "riskReviews": []}},
        "traceSummary": {},
        "externalSearchConfig": {
            "allowExternalSearch": bool(getattr(request, "allowExternalSearch", False)),
            "provider": "disabled",
            "budget": {"callLimit": 3, "evidenceLimit": 15, "callsUsed": 0, "evidenceUsed": 0},
            "status": "disabled",
            "degradation": "",
        },
        "report": "",
        "error": "",
        "createdAt": created_at,
        "updatedAt": created_at,
    }

    with _TASK_LOCK:
        # A second caller may have created this identity while we built the snapshot.
        if operation_key and task_id in _TASKS:
            if _TASK_CONTEXTS[task_id].get("operationFingerprint") != fingerprint:
                raise ResearchReviewConflictError("Research request identity was reused with different input.")
            return {"status": "success", "task": copy.deepcopy(_TASKS[task_id])}
        _TASKS[task_id] = copy.deepcopy(task)
        _TASK_CONTEXTS[task_id] = {
            "paperSkeleton": copy.deepcopy(request.paperSkeleton or {}),
            "userConstraints": user_constraints,
            "briefPreview": copy.deepcopy(brief_preview),
            "allowedPaperIds": copy.deepcopy(allowed_papers),
            "operationFingerprint": fingerprint,
        }
        _TASK_CANCELLATIONS.discard(task_id)
        _persist_task_snapshot_locked(_TASKS[task_id])

    if start_async:
        _TASK_EXECUTOR.submit(prepare_research_task_now, task_id)

    return {"status": "success", "task": _copy_task_snapshot(task_id)}

def preview_research_brief(request: ResearchTaskBriefPreviewRequest) -> dict[str, Any]:
    question = _clean_text(request.question)
    pdf_id = _clean_text(request.pdfId)
    if not question:
        raise ValueError("Question cannot be empty.")
    if not pdf_id:
        raise ValueError("pdfId cannot be empty.")

    with trace_step("research_brief_preview", input_size=len(question)):
        try:
            documents, normalized_pdf_id = _load_current_paper_documents(pdf_id)
        except Exception as error:
            _logger.error(f"research brief preview could not load current paper evidence: {error}")
            documents, normalized_pdf_id = [], pdf_id
        preview = _build_research_brief_preview(
            question=question,
            pdf_id=normalized_pdf_id or pdf_id,
            paper_skeleton=request.paperSkeleton or {},
            documents=documents,
            user_constraints=_clean_text(request.userConstraints),
        )
    return {"status": "success", "briefPreview": preview}

def get_research_task(task_id: str) -> dict[str, Any]:
    _ensure_storage_loaded()
    return {"status": "success", "task": _copy_task_snapshot(task_id)}

def get_latest_research_task(pdf_id: str) -> dict[str, Any]:
    _ensure_storage_loaded()
    normalized_pdf_id = _clean_text(pdf_id)
    if not normalized_pdf_id:
        raise ResearchTaskNotFoundError("Research task not found.")

    with _TASK_LOCK:
        candidates = [
            task for task in _TASKS.values()
            if str(task.get("pdfId") or "") == normalized_pdf_id
        ]
        if not candidates:
            raise ResearchTaskNotFoundError("Research task not found.")

        latest = max(
            candidates,
            key=lambda task: (
                str(task.get("updatedAt") or ""),
                str(task.get("createdAt") or ""),
                str(task.get("taskId") or ""),
            ),
        )
        return {"status": "success", "task": copy.deepcopy(latest)}

def get_persisted_trace_summary(trace_id: str) -> dict[str, Any] | None:
    _ensure_storage_loaded()
    normalized_trace_id = _clean_text(trace_id)
    if not normalized_trace_id:
        return None

    with _TASK_LOCK:
        for task in _TASKS.values():
            if str(task.get("traceId") or "") != normalized_trace_id:
                continue
            summary = task.get("traceSummary")
            return copy.deepcopy(summary) if isinstance(summary, dict) and summary else None
    return None

def cancel_research_task(task_id: str) -> dict[str, Any]:
    _ensure_storage_loaded()
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise ResearchTaskNotFoundError("Research task not found.")
        interrupted = task.get("status") == "failed" and task.get("error") == INTERRUPTED_RESTART_ERROR
        if str(task.get("status") or "") in TERMINAL_STATUSES and not interrupted:
            return {"status": "success", "task": copy.deepcopy(task)}

        _TASK_CANCELLATIONS.add(task_id)
        cancelled = {
            **task,
            "status": "cancelling" if _RUNNING_TASKS.get(task_id, 0) else "cancelled",
            "stage": task.get("stage") if _RUNNING_TASKS.get(task_id, 0) else DONE_STAGE,
            "updatedAt": _utc_now(),
        }
        _TASKS[task_id] = cancelled
        _persist_task_snapshot_locked(cancelled)

    with use_trace(str(cancelled.get("traceId") or "")):
        trace_snapshot = finalize_trace(
            "cancelled",
            response_meta={
                "taskId": task_id,
                "stage": DONE_STAGE,
            },
        )
        _persist_trace_summary(task_id, trace_snapshot)
    return {"status": "success", "task": _copy_task_snapshot(task_id)}

def clear_research_tasks(clear_storage: bool = True) -> None:
    with _TASK_LOCK:
        _TASKS.clear()
        _TASK_CONTEXTS.clear()
        _TASK_CANCELLATIONS.clear()
        global _STORAGE_LOADED
        _STORAGE_LOADED = False
        if clear_storage:
            _delete_persisted_tasks_locked()

def reload_research_tasks_from_storage() -> None:
    with _TASK_LOCK:
        _TASKS.clear()
        _TASK_CONTEXTS.clear()
        _TASK_CANCELLATIONS.clear()
        global _STORAGE_LOADED
        _STORAGE_LOADED = False
    _ensure_storage_loaded()

@_tracked_execution
def run_research_task_now(task_id: str) -> dict[str, Any]:
    _ensure_storage_loaded()
    task = _ensure_execution_trace(task_id)
    context = _copy_task_context(task_id)
    with use_trace(str(task.get("traceId") or "")):
        _run_research_task(
            task_id,
            question=str(task.get("question") or ""),
            pdf_id=str(task.get("pdfId") or ""),
            paper_skeleton=context.get("paperSkeleton") or {},
            user_constraints=str(context.get("userConstraints") or ""),
            brief_preview=context.get("briefPreview") or {},
            trace_id=str(task.get("traceId") or ""),
        )
    return _copy_task_snapshot(task_id)

@_tracked_execution
def prepare_research_task_now(task_id: str) -> dict[str, Any]:
    task = _copy_task_snapshot(task_id)
    context = _copy_task_context(task_id)
    _update_task_snapshot(task_id, status="running", stage=PLANNING_STAGE, progress=0.05)
    documents, normalized_pdf_id = _load_current_paper_documents(str(task.get("pdfId") or ""))
    if not documents:
        _fail_task(task_id, "Current paper has not been indexed yet.")
        return _copy_task_snapshot(task_id)
    research_question = _compose_research_question(str(task.get("question") or ""), str(context.get("userConstraints") or ""))
    brief_preview = context.get("briefPreview") or {}
    brief, sub_questions = _build_research_plan(
        research_question,
        context.get("paperSkeleton") or {},
        documents,
        brief_override=_clean_text(brief_preview.get("brief")),
    )
    plan_items = _build_initial_plan_items(sub_questions)
    with _TASK_LOCK:
        _TASK_CONTEXTS[task_id] = {**context, "brief": brief, "normalizedPdfId": normalized_pdf_id, "approvedPlan": []}
    return _update_task_snapshot(task_id, status="awaiting_plan_review", stage=PLANNING_STAGE, progress=0.2, plan=plan_items)

def _serialized_control(function):
    @wraps(function)
    def control(task_id, *args, **kwargs):
        _ensure_storage_loaded()
        with _TASK_LOCK:
            return function(task_id, *args, **kwargs)
    return control


def _ensure_execution_trace(task_id: str, *, restart: bool = False) -> dict[str, Any]:
    """A persisted task can outlive the process-local trace store."""
    with _TASK_LOCK:
        task = _copy_task_snapshot(task_id)
        if not restart:
            try:
                get_trace_snapshot(str(task.get("traceId") or ""))
                return task
            except KeyError:
                pass
        trace_id = start_trace(
            "deep_research",
            request_meta={
                "question": sanitize_text(task.get("question"), max_chars=120),
                "pdfId": sanitize_text(task.get("pdfId"), max_chars=80),
                "previousTraceId": str(task.get("traceId") or ""),
                "taskId": task_id,
            },
            activate=False,
            initial_status="pending",
        )
        # Keep persisted findings and prior summary until the new execution checkpoints.
        return _update_task_snapshot(task_id, traceId=trace_id)


@_serialized_control
def review_research_plan(task_id: str, request: ResearchPlanReviewRequest) -> dict[str, Any]:
    task = _copy_task_snapshot(task_id)
    if task.get("status") != "awaiting_plan_review":
        if task.get("status") in {"running", "awaiting_final_review", "succeeded"}:
            return {"status": "success", "task": task}
        raise ResearchReviewConflictError("Research task is not awaiting plan review.")
    questions = research_planner.normalize_sub_questions(request.subQuestions, [])
    if not questions:
        raise ValueError("At least one valid sub-question is required.")
    plan_items = _build_initial_plan_items(questions)
    reviewed_at = _utc_now()
    context = _copy_task_context(task_id)
    with _TASK_LOCK:
        _TASK_CONTEXTS[task_id] = {**context, "approvedPlan": copy.deepcopy(plan_items)}
    human_review = copy.deepcopy(task.get("humanReview") or {})
    human_review["plan"] = {"status": "approved", "reviewNotes": _clean_text(request.reviewNotes), "reviewedAt": reviewed_at}
    updated = _update_task_snapshot(task_id, status="running", plan=plan_items, humanReview=human_review)
    _TASK_EXECUTOR.submit(run_research_task_now, task_id)
    return {"status": "success", "task": updated}


def resume_research_task(task_id: str) -> dict[str, Any]:
    """Explicit continuation only; repeated acknowledgements never schedule twice."""
    _ensure_storage_loaded()
    with _TASK_LOCK:
        task = _copy_task_snapshot(task_id)
        if task["status"] not in {"failed", "cancelled"}:
            return {"status": "success", "task": task}
        if _RUNNING_TASKS.get(task_id):
            raise ResearchReviewConflictError("Research worker has not stopped yet.")
        context = _copy_task_context(task_id)
        if not context.get("approvedPlan"):
            if not task.get("plan"):
                raise ResearchReviewConflictError("No saved plan is available. Start a new research request.")
            next_status = "awaiting_plan_review"
        else:
            next_status = "running"
        task = _ensure_execution_trace(task_id, restart=True)
        _TASK_CANCELLATIONS.discard(task_id)
        # Directly transition under the same lock: ordinary updates cannot revive cancellation.
        task = {**task, "status": next_status, "stage": PLANNING_STAGE, "error": "", "updatedAt": _utc_now()}
        _TASKS[task_id] = task
        _persist_task_snapshot_locked(task)
        if next_status == "running":
            _TASK_EXECUTOR.submit(run_research_task_now, task_id)
        return {"status": "success", "task": copy.deepcopy(task)}

@_serialized_control
def review_research_final(task_id: str, request: ResearchFinalReviewRequest) -> dict[str, Any]:
    task = _copy_task_snapshot(task_id)
    if task.get("status") == "succeeded":
        return {"status": "success", "task": task}
    if task.get("status") != "awaiting_final_review":
        raise ResearchReviewConflictError("Research task is not awaiting final review.")
    risk_reviews = _validate_risk_reviews(task.get("reviewRisks") or [], request.riskReviews or [])
    human_review = copy.deepcopy(task.get("humanReview") or {})
    human_review["final"] = {"status": "approved", "reviewNotes": _clean_text(request.reviewNotes), "reviewedAt": _utc_now(), "riskReviews": risk_reviews}
    status_by_id = {item["riskId"]: item["reviewStatus"] for item in risk_reviews}
    reviewed_risks = [{**item, "reviewStatus": status_by_id.get(str(item.get("riskId") or ""), item.get("reviewStatus") or "pending")} for item in task.get("reviewRisks") or []]
    updated = _update_task_snapshot(task_id, status="succeeded", stage=DONE_STAGE, progress=1.0, humanReview=human_review, reviewRisks=reviewed_risks)
    with use_trace(str(task.get("traceId") or "")):
        trace_snapshot = finalize_trace("success", response_meta={"taskId": task_id, "stage": DONE_STAGE})
        _persist_trace_summary(task_id, trace_snapshot)
    return {"status": "success", "task": updated}

def _run_research_task(
    task_id: str,
    question: str,
    pdf_id: str,
    paper_skeleton: dict[str, Any],
    user_constraints: str = "",
    brief_preview: dict[str, Any] | None = None,
    trace_id: str = "",
) -> None:
    if _is_cancelled(task_id):
        return

    context = _copy_task_context(task_id)
    _update_task_snapshot(task_id, status="running", stage=PLANNING_STAGE, progress=0.0)

    try:
        record_metric("taskId", task_id)
        with trace_step("research_load_current_paper", meta={"pdfId": sanitize_text(pdf_id, max_chars=80)}):
            documents, normalized_pdf_id = _load_current_paper_documents(pdf_id)
        if not documents:
            _fail_task(task_id, "Current paper has not been indexed yet.")
            trace_snapshot = finalize_trace(
                "error",
                error="Current paper has not been indexed yet.",
                response_meta={"taskId": task_id, "stage": DONE_STAGE},
            )
            _persist_trace_summary(task_id, trace_snapshot)
            return
        if _is_cancelled(task_id):
            return

        research_question = _compose_research_question(question, user_constraints)
        brief_override = _clean_text((brief_preview or {}).get("brief"))
        approved_plan = _copy_task_context(task_id).get("approvedPlan") or []
        if approved_plan:
            brief = _clean_text(_copy_task_context(task_id).get("brief")) or brief_override or research_question
            sub_questions = [_clean_text(item.get("question")) for item in approved_plan]
        else:
            brief, sub_questions = _build_research_plan(research_question, paper_skeleton, documents, brief_override=brief_override)
        record_metric("subQuestionCount", len(sub_questions))
        saved = _copy_task_snapshot(task_id)
        plan_items = copy.deepcopy(saved.get("plan") or []) if approved_plan else []
        if not plan_items:
            plan_items = _build_initial_plan_items(sub_questions)
        _update_task_snapshot(task_id, stage=PLANNING_STAGE, progress=0.2, plan=copy.deepcopy(plan_items))
        if _is_cancelled(task_id):
            return

        findings: list[dict[str, Any]] = copy.deepcopy(saved.get("findings") or []) if approved_plan else []
        follow_up_count = sum(item.get("kind") == "follow_up" for item in plan_items)
        index = 0
        while index < len(plan_items):
            if _is_cancelled(task_id):
                return

            if plan_items[index].get("status") == "done":
                index += 1
                continue

            plan_items[index]["status"] = "running"
            sub_question = _clean_text(plan_items[index].get("question"))
            total = max(len(plan_items), 1)
            base_progress = round(0.2 + (index / total) * 0.6, 2)
            _update_task_snapshot(
                task_id,
                stage=RETRIEVING_STAGE,
                progress=base_progress,
                plan=copy.deepcopy(plan_items),
            )

            with trace_step(
                f"research_sub_question_{index + 1}",
                input_size=len(str(sub_question or "")),
                meta={
                    "subQuestion": sanitize_text(sub_question, max_chars=120),
                    "kind": _clean_text(plan_items[index].get("kind")) or "initial",
                },
            ) as step:
                finding = _research_sub_question(
                    sub_question=sub_question,
                    question=research_question,
                    pdf_id=normalized_pdf_id,
                    paper_skeleton=paper_skeleton,
                    documents=documents,
                    **({"allowed_paper_ids": context["allowedPaperIds"]} if context.get("allowedPaperIds") is not None else {}),
                )
                step["outputSize"] = len(finding.get("sourceIds") or [])
            if _is_cancelled(task_id):
                return

            if plan_items[index].get("kind") == "follow_up":
                finding = {
                    **finding,
                    "isFollowUp": True,
                    "followUpOf": _clean_text(plan_items[index].get("sourceQuestion")),
                    "sourceMissingAspects": _normalize_missing_aspects(plan_items[index].get("sourceMissingAspects")),
                }

            findings.append(finding)
            plan_items[index]["status"] = "done"
            # Checkpoint before a follow-up model call can fail or the process can restart.
            _update_task_snapshot(task_id, plan=copy.deepcopy(plan_items), findings=copy.deepcopy(findings))
            if follow_up_count < MAX_DYNAMIC_FOLLOW_UPS and _should_create_follow_up(finding):
                with trace_step(
                    "research_replanning",
                    input_size=len(str(finding.get("summary") or "")),
                    meta={
                        "sourceQuestion": sanitize_text(finding.get("subQuestion"), max_chars=120),
                        "missingAspects": _normalize_missing_aspects(finding.get("missingAspects")),
                    },
                ) as step:
                    from services.research_planner import replan_if_needed

                    new_items = replan_if_needed(
                        finding=finding,
                        question=research_question,
                        next_index=len(plan_items) + 1,
                    )
                    for new_item in new_items:
                        plan_items.append(new_item)
                        follow_up_count += 1
                    record_metric("followUpCount", follow_up_count)
                    step["outputSize"] = len(new_items)

            total = max(len(plan_items), 1)
            done_progress = round(0.2 + ((index + 1) / total) * 0.6, 2)
            _update_task_snapshot(
                task_id,
                stage=JUDGING_STAGE,
                progress=done_progress,
                plan=copy.deepcopy(plan_items),
                findings=copy.deepcopy(findings),
            )
            index += 1

        if _is_cancelled(task_id):
            return

        _update_task_snapshot(
            task_id,
            stage=SYNTHESIZING_STAGE,
            progress=0.9,
            plan=copy.deepcopy(plan_items),
            findings=copy.deepcopy(findings),
        )
        conflicts = research_aggregator.enrich_research_conflicts(_detect_research_conflicts(findings))
        _update_task_snapshot(
            task_id,
            stage=SYNTHESIZING_STAGE,
            progress=0.92,
            plan=copy.deepcopy(plan_items),
            findings=copy.deepcopy(findings),
            conflicts=copy.deepcopy(conflicts),
        )
        with trace_step("research_report_synthesis", input_size=len(findings)) as step:
            trace_summary = get_trace_snapshot(trace_id)
            report = _build_research_report(research_question, brief, plan_items, findings, conflicts, trace_summary=trace_summary)
            step["outputSize"] = len(str(report or ""))
        if _is_cancelled(task_id):
            return

        _update_task_snapshot(
            task_id,
            status="awaiting_final_review",
            stage=SYNTHESIZING_STAGE,
            progress=0.95,
            plan=copy.deepcopy(plan_items),
            findings=copy.deepcopy(findings),
            conflicts=copy.deepcopy(conflicts),
            report=report,
            reviewRisks=_build_research_review_risks(findings, conflicts),
            error="",
        )
        final_skeleton_block = wrap_untrusted_context("Research paper skeleton", _stringify_paper_skeleton(paper_skeleton), max_tokens=1000)
        final_evidence_block = wrap_untrusted_context(
            "Research current paper evidence",
            # 旧值 max_items=4 / max_text_chars=260 / max_tokens=1400 让最终报告只能看到约 1040 字符原文，
            # 这是深度研究报告“漏写论文内容”的主因。
            format_evidence_context(documents, title="当前论文证据", max_items=8, max_text_chars=2000),
            max_tokens=8000,
        )
        _record_safety_budget_counters(final_skeleton_block, final_evidence_block)
        record_metric("awaitingFinalReview", True)
        trace_snapshot = finalize_trace(
            "awaiting_review",
            response_meta={"taskId": task_id, "findingCount": len(findings), "followUpCount": follow_up_count, "conflictCount": len(conflicts), "stage": SYNTHESIZING_STAGE},
        )
        _persist_trace_summary(task_id, trace_snapshot)
    except Exception as error:
        _fail_task(task_id, str(error))
        trace_snapshot = finalize_trace("error", error=error, response_meta={"taskId": task_id, "stage": DONE_STAGE})
        _persist_trace_summary(task_id, trace_snapshot)

def _copy_task_snapshot(task_id: str) -> dict[str, Any]:
    _ensure_storage_loaded()
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise ResearchTaskNotFoundError("Research task not found.")
        return copy.deepcopy(task)

def _copy_task_context(task_id: str) -> dict[str, Any]:
    _ensure_storage_loaded()
    with _TASK_LOCK:
        return copy.deepcopy(_TASK_CONTEXTS.get(task_id) or {})

def _update_task_snapshot(task_id: str, **updates: Any) -> dict[str, Any]:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise ResearchTaskNotFoundError("Research task not found.")
        if (
            str(task.get("status") or "") in {"cancelled", "cancelling"}
            and updates.get("status") not in {"cancelled", "cancelling"}
            and set(updates.keys()) != {"traceSummary"}
        ):
            return copy.deepcopy(task)

        updated = {
            **task,
            **copy.deepcopy(updates),
            "updatedAt": _utc_now(),
        }
        _TASKS[task_id] = updated
        _persist_task_snapshot_locked(updated)
        return copy.deepcopy(updated)
def _persist_trace_summary(task_id: str, trace_snapshot: dict[str, Any] | None) -> None:
    if not trace_snapshot:
        return
    _update_task_snapshot(task_id, traceSummary=build_public_trace_summary(trace_snapshot))

def _fail_task(task_id: str, error_message: str) -> None:
    _update_task_snapshot(
        task_id,
        status="failed",
        stage=DONE_STAGE,
        error=_clean_text(error_message)[:240] or "Research task failed.",
    )

def _is_cancelled(task_id: str) -> bool:
    _ensure_storage_loaded()
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        return task_id in _TASK_CANCELLATIONS or str((task or {}).get("status") or "") == "cancelled"

def _ensure_storage_loaded() -> None:
    global _STORAGE_LOADED
    with _TASK_LOCK:
        if _STORAGE_LOADED:
            return
        _initialize_storage_locked()
        for task in _load_persisted_tasks_locked():
            internal_context = task.pop("_context", {})
            restored = _restore_task_after_restart(task)
            _TASKS[str(restored.get("taskId") or "")] = restored
            _TASK_CONTEXTS[str(restored.get("taskId") or "")] = internal_context
            if restored is not task:
                _persist_task_snapshot_locked(restored)
        _STORAGE_LOADED = True

def _restore_task_after_restart(task: dict[str, Any]) -> dict[str, Any]:
    status = str(task.get("status") or "")
    if status == "cancelling":
        return {**task, "status": "cancelled", "stage": DONE_STAGE, "updatedAt": _utc_now()}
    if status in TERMINAL_STATUSES or status in {"awaiting_plan_review", "awaiting_final_review"}:
        return task
    restored = {
        **task,
        "status": "failed",
        "stage": DONE_STAGE,
        "error": INTERRUPTED_RESTART_ERROR,
        "updatedAt": _utc_now(),
    }
    return restored

def _initialize_storage_locked() -> None:
    db_path = _research_task_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_tasks (
                taskId TEXT PRIMARY KEY,
                traceId TEXT,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress REAL NOT NULL,
                question TEXT NOT NULL,
                pdfId TEXT NOT NULL,
                plan TEXT NOT NULL,
                findings TEXT NOT NULL,
                conflicts TEXT NOT NULL DEFAULT '[]',
                reviewRisks TEXT NOT NULL DEFAULT '[]',
                humanReview TEXT NOT NULL DEFAULT '{}',
                context TEXT NOT NULL DEFAULT '{}',
                traceSummary TEXT NOT NULL DEFAULT '{}',
                report TEXT NOT NULL,
                error TEXT NOT NULL,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(research_tasks)").fetchall()}
        if "conflicts" not in columns:
            connection.execute("ALTER TABLE research_tasks ADD COLUMN conflicts TEXT NOT NULL DEFAULT '[]'")
        if "traceSummary" not in columns:
            connection.execute("ALTER TABLE research_tasks ADD COLUMN traceSummary TEXT NOT NULL DEFAULT '{}'")
        if "reviewRisks" not in columns:
            connection.execute("ALTER TABLE research_tasks ADD COLUMN reviewRisks TEXT NOT NULL DEFAULT '[]'")
        if "humanReview" not in columns:
            connection.execute("ALTER TABLE research_tasks ADD COLUMN humanReview TEXT NOT NULL DEFAULT '{}'")
        if "context" not in columns:
            connection.execute("ALTER TABLE research_tasks ADD COLUMN context TEXT NOT NULL DEFAULT '{}'")
        if "externalSearchConfig" not in columns:
            connection.execute("ALTER TABLE research_tasks ADD COLUMN externalSearchConfig TEXT NOT NULL DEFAULT '{}'")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_tasks_pdf_updated ON research_tasks (pdfId, updatedAt)")
        connection.commit()

def _load_persisted_tasks_locked() -> list[dict[str, Any]]:
    db_path = _research_task_db_path()
    if not db_path.exists():
        return []
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM research_tasks ORDER BY createdAt ASC").fetchall()
    return [_task_from_storage_row(row) for row in rows]

def _persist_task_snapshot_locked(task: dict[str, Any]) -> None:
    _initialize_storage_locked()
    snapshot = _normalize_task_for_storage(task)
    with closing(sqlite3.connect(_research_task_db_path())) as connection:
        connection.execute(
            """
            INSERT INTO research_tasks (
                taskId, traceId, status, stage, progress, question, pdfId,
                plan, findings, conflicts, reviewRisks, humanReview, context, traceSummary, externalSearchConfig, report, error, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(taskId) DO UPDATE SET
                traceId=excluded.traceId,
                status=excluded.status,
                stage=excluded.stage,
                progress=excluded.progress,
                question=excluded.question,
                pdfId=excluded.pdfId,
                plan=excluded.plan,
                findings=excluded.findings,
                conflicts=excluded.conflicts,
                reviewRisks=excluded.reviewRisks,
                humanReview=excluded.humanReview,
                context=excluded.context,
                traceSummary=excluded.traceSummary,
                externalSearchConfig=excluded.externalSearchConfig,
                report=excluded.report,
                error=excluded.error,
                createdAt=excluded.createdAt,
                updatedAt=excluded.updatedAt
            """,
            (
                snapshot["taskId"],
                snapshot["traceId"],
                snapshot["status"],
                snapshot["stage"],
                snapshot["progress"],
                snapshot["question"],
                snapshot["pdfId"],
                json.dumps(snapshot["plan"], ensure_ascii=False),
                json.dumps(snapshot["findings"], ensure_ascii=False),
                json.dumps(snapshot["conflicts"], ensure_ascii=False),
                json.dumps(snapshot["reviewRisks"], ensure_ascii=False),
                json.dumps(snapshot["humanReview"], ensure_ascii=False),
                json.dumps(_TASK_CONTEXTS.get(snapshot["taskId"]) or {}, ensure_ascii=False),
                json.dumps(snapshot["traceSummary"], ensure_ascii=False),
                json.dumps(snapshot.get("externalSearchConfig") or {}, ensure_ascii=False),
                snapshot["report"],
                snapshot["error"],
                snapshot["createdAt"],
                snapshot["updatedAt"],
            ),
        )
        connection.commit()

def _delete_persisted_tasks_locked() -> None:
    _initialize_storage_locked()
    with closing(sqlite3.connect(_research_task_db_path())) as connection:
        connection.execute("DELETE FROM research_tasks")
        connection.commit()

def _task_from_storage_row(row: sqlite3.Row) -> dict[str, Any]:
    created_at = str(row["createdAt"] or _utc_now())
    updated_at = str(row["updatedAt"] or created_at)
    return {
        "taskId": str(row["taskId"] or ""),
        "traceId": str(row["traceId"] or ""),
        "status": str(row["status"] or "failed"),
        "stage": str(row["stage"] or DONE_STAGE),
        "progress": float(row["progress"] or 0.0),
        "question": str(row["question"] or ""),
        "pdfId": str(row["pdfId"] or ""),
        "plan": _safe_json_list(row["plan"]),
        "findings": _safe_json_list(row["findings"]),
        "conflicts": _safe_json_list(row["conflicts"]) if "conflicts" in row.keys() else [],
        "reviewRisks": _safe_json_list(row["reviewRisks"]) if "reviewRisks" in row.keys() else [],
        "humanReview": _safe_json_dict(row["humanReview"]) if "humanReview" in row.keys() else {},
        "_context": _safe_json_dict(row["context"]) if "context" in row.keys() else {},
        "traceSummary": _safe_json_dict(row["traceSummary"]) if "traceSummary" in row.keys() else {},
        "externalSearchConfig": _safe_json_dict(row["externalSearchConfig"]) if "externalSearchConfig" in row.keys() else {},
        "report": str(row["report"] or ""),
        "error": str(row["error"] or ""),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }

def _normalize_task_for_storage(task: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    created_at = str(task.get("createdAt") or now)
    updated_at = str(task.get("updatedAt") or created_at)
    return {
        "taskId": str(task.get("taskId") or ""),
        "traceId": str(task.get("traceId") or ""),
        "status": str(task.get("status") or "pending"),
        "stage": str(task.get("stage") or PLANNING_STAGE),
        "progress": float(task.get("progress") or 0.0),
        "question": str(task.get("question") or ""),
        "pdfId": str(task.get("pdfId") or ""),
        "plan": list(task.get("plan") or []),
        "findings": list(task.get("findings") or []),
        "conflicts": list(task.get("conflicts") or []),
        "reviewRisks": list(task.get("reviewRisks") or []),
        "humanReview": dict(task.get("humanReview") or {}),
        "traceSummary": dict(task.get("traceSummary") or {}),
        "externalSearchConfig": dict(task.get("externalSearchConfig") or {}),
        "report": str(task.get("report") or ""),
        "error": str(task.get("error") or ""),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }

def _safe_json_list(value: Any) -> list[Any]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []

def _safe_json_dict(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}

def _research_task_db_path() -> Path:
    configured = os.environ.get("RESEARCH_TASK_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "research_tasks.sqlite3"

def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

_build_research_plan = research_planner.build_research_plan
_build_initial_plan_items = research_planner.build_initial_plan_items
_should_create_follow_up = research_planner.should_create_follow_up
_build_follow_up_plan_item = research_planner.build_follow_up_plan_item
_record_safety_budget_counters = research_planner.record_safety_budget_counters

_research_sub_question = research_executor.research_sub_question
_retrieve_current_paper_evidence = research_executor.retrieve_current_paper_evidence
_retrieve_library_evidence = research_executor.retrieve_library_evidence
_judge_research_evidence = research_executor.judge_research_evidence
_should_try_external = research_executor.should_try_external
_retrieve_external_academic_evidence = research_executor.retrieve_external_academic_evidence

_build_research_report = research_aggregator.build_research_report
_detect_research_conflicts = research_aggregator.detect_research_conflicts
_build_judge_trace_summary = research_aggregator.build_judge_trace_summary
