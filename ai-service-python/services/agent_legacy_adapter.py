"""Legacy task snapshot adapter for backward compatibility."""

import copy
from typing import Any

from services.agent_artifact_service import build_artifacts_record
from services.agent_review_service import (
    build_final_review_packet,
    build_plan_review_packet,
)
from services.agent_timeline_service import build_timeline_entry


class AgentProjectNotFoundError(Exception):
    pass


def _copy_project(project_id: str) -> dict[str, Any]:
    from services.agent_project_service import _LOCK, _PROJECTS, _ensure_storage_loaded

    _ensure_storage_loaded()
    with _LOCK:
        project = _PROJECTS.get(project_id)
        if project is None:
            raise AgentProjectNotFoundError("Agent project not found.")
        return copy.deepcopy(project)


def _copy_task(task_id: str) -> dict[str, Any]:
    from services.agent_project_service import _LOCK, _TASKS, _ensure_storage_loaded

    _ensure_storage_loaded()
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            from services.agent_project_service import AgentTaskNotFoundError

            raise AgentTaskNotFoundError("Agent task not found.")
        return copy.deepcopy(task)


def _build_legacy_task_snapshot_from_run_id(run_id: str) -> dict[str, Any]:
    from services.agent_project_service import _clean_text

    task = _copy_task(_clean_text(run_id))
    project = _copy_project(str(task.get("projectId") or ""))
    return _build_legacy_task_snapshot(
        project=project,
        run=_build_run_record(task),
        pending_review=_build_pending_review_record(task),
        artifacts=_build_artifacts_resource(task),
        timeline=_build_timeline_resource(task),
    )


def _build_run_record(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": str(task.get("taskId") or ""),
        "projectId": str(task.get("projectId") or ""),
        "traceId": str(task.get("traceId") or ""),
        "status": str(task.get("status") or ""),
        "executionPhase": str(task.get("stage") or ""),
        "progress": float(task.get("progress") or 0.0),
        "prompt": str(task.get("prompt") or ""),
        "focusedPaperIds": list(task.get("focusedPaperIds") or []),
        "constraints": str(task.get("constraints") or ""),
        "context": dict(task.get("context") or {}),
        "humanReview": copy.deepcopy(task.get("humanReview") or {}),
        "reviewRisks": list(task.get("reviewRisks") or []),
        "traceSummary": copy.deepcopy(task.get("traceSummary") or {}),
        "externalSearchConfig": copy.deepcopy(task.get("externalSearchConfig") or {}),
        "codeExecutionConfig": copy.deepcopy(task.get("codeExecutionConfig") or {}),
        "error": str(task.get("error") or ""),
        "createdAt": str(task.get("createdAt") or ""),
        "updatedAt": str(task.get("updatedAt") or ""),
    }


def _build_pending_review_record(task: dict[str, Any]) -> dict[str, Any] | None:
    if task.get("status") == "awaiting_plan_review":
        return build_plan_review_packet(
            run={"runId": str(task.get("taskId") or "")},
            plan_items=task.get("planItems") or [],
            focused_paper_ids=task.get("focusedPaperIds") or [],
            constraints=str(task.get("constraints") or ""),
            allow_external_search=bool(
                (task.get("externalSearchConfig") or {}).get("allowExternalSearch")
            ),
        )
    if task.get("status") == "awaiting_final_review":
        return build_final_review_packet(
            run={"runId": str(task.get("taskId") or "")},
            artifacts=_build_artifacts_resource(task),
        )
    return None


def _build_artifacts_resource(task: dict[str, Any]) -> dict[str, Any]:
    return build_artifacts_record(
        str(task.get("taskId") or ""),
        evidence_items=task.get("evidenceItems") or [],
        tool_call_summary=task.get("toolCalls") or [],
        findings=task.get("findings") or [],
        comparison_table=task.get("comparisonTable") or {"columns": [], "rows": []},
        conflicts=task.get("conflicts") or [],
        open_questions=task.get("openQuestions") or [],
        draft_report=str(task.get("draftReport") or ""),
    )


def _build_timeline_resource(task: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for event in list(task.get("events") or []):
        if "id" in event and "eventId" not in event:
            current = copy.deepcopy(event)
            current["timestamp"] = str(current.get("timestamp") or "")
            entries.append(current)
            continue
        entry = build_timeline_entry(
            entry_id=str(event.get("eventId") or ""),
            entry_type=str(event.get("type") or ""),
            title=str(event.get("summary") or ""),
            detail=str(event.get("summary") or ""),
            phase=str(event.get("stage") or ""),
            meta={
                **dict(event.get("meta") or {}),
                "timestamp": str(event.get("timestamp") or ""),
                "taskId": str(event.get("taskId") or ""),
            },
        )
        entry["timestamp"] = str(event.get("timestamp") or "")
        entries.append(entry)
    return entries


def _build_legacy_events_from_timeline(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for entry in list(timeline or []):
        meta = dict(entry.get("meta") or {})
        events.append(
            {
                "eventId": str(entry.get("id") or ""),
                "type": str(entry.get("type") or ""),
                "timestamp": str(entry.get("timestamp") or meta.get("timestamp") or ""),
                "taskId": str(meta.get("taskId") or ""),
                "stage": str(entry.get("phase") or ""),
                "summary": str(entry.get("detail") or entry.get("title") or ""),
                "meta": meta,
            }
        )
    return events


def _build_task_snapshot_from_resources(
    project: dict[str, Any],
    run: dict[str, Any],
    plan_review: dict[str, Any] | None,
    final_review: dict[str, Any] | None,
    artifacts: dict[str, Any] | None,
    timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    pending_review = None
    if str(run.get("status") or "") == "awaiting_plan_review":
        pending_review = plan_review or {}
    elif str(run.get("status") or "") == "awaiting_final_review":
        pending_review = final_review or {}
    snapshot = _build_legacy_task_snapshot(
        project=project,
        run=run,
        pending_review=pending_review,
        artifacts=artifacts or {},
        timeline=_build_legacy_events_from_timeline(timeline),
    )
    snapshot["reviewRisks"] = list(run.get("reviewRisks") or [])
    snapshot["traceSummary"] = copy.deepcopy(run.get("traceSummary") or {})
    return snapshot


def _build_legacy_task_snapshot(
    project: dict[str, Any],
    run: dict[str, Any],
    pending_review: dict[str, Any] | None,
    artifacts: dict[str, Any] | None,
    timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "taskId": str(run.get("runId") or ""),
        "projectId": str(project.get("projectId") or ""),
        "status": str(run.get("status") or ""),
        "stage": str(run.get("executionPhase") or ""),
        "traceId": str(run.get("traceId") or ""),
        "progress": float(run.get("progress") or 0.0),
        "prompt": str(run.get("prompt") or ""),
        "focusedPaperIds": list(run.get("focusedPaperIds") or []),
        "constraints": str(run.get("constraints") or ""),
        "planItems": list((pending_review or {}).get("planItems") or []),
        "toolCalls": list((artifacts or {}).get("toolCallSummary") or []),
        "evidenceItems": list((artifacts or {}).get("evidenceItems") or []),
        "findings": list((artifacts or {}).get("findings") or []),
        "comparisonTable": copy.deepcopy((artifacts or {}).get("comparisonTable") or {"columns": [], "rows": []}),
        "conflicts": list((artifacts or {}).get("conflicts") or []),
        "openQuestions": list((artifacts or {}).get("openQuestions") or []),
        "events": list(timeline or []),
        "draftReport": str((artifacts or {}).get("draftReport") or ""),
        "humanReview": copy.deepcopy(run.get("humanReview") or {}),
        "reviewRisks": list(run.get("reviewRisks") or []),
        "traceSummary": copy.deepcopy(run.get("traceSummary") or {}),
        "externalSearchConfig": copy.deepcopy(run.get("externalSearchConfig") or {}),
        "codeExecutionConfig": copy.deepcopy(run.get("codeExecutionConfig") or {}),
        "error": str(run.get("error") or ""),
        "createdAt": str(run.get("createdAt") or ""),
        "updatedAt": str(run.get("updatedAt") or ""),
    }
