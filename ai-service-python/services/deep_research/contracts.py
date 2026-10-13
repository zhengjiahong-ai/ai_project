"""Deep Research run contracts (v2).

Plain JSON dicts with camelCase keys externally.  Internal helpers use
snake_case where useful.  This module has no LangGraph, FastAPI or LLM
imports so repository-level tests stay dependency free.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Iterable

CONTRACT_VERSION = 2
ENGINE_VERSION = "deep-research-v2"

# ── Lifecycle statuses ────────────────────────────────────────────────────────

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_WAITING_USER = "waiting_user"
STATUS_PAUSED = "paused"
STATUS_STOPPING = "stopping"
STATUS_CANCELLED = "cancelled"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

RUN_STATUSES = frozenset(
    {
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_WAITING_USER,
        STATUS_PAUSED,
        STATUS_STOPPING,
        STATUS_CANCELLED,
        STATUS_COMPLETED,
        STATUS_FAILED,
    }
)
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED})
ACTIVE_STATUSES = frozenset(
    {STATUS_QUEUED, STATUS_RUNNING, STATUS_WAITING_USER, STATUS_PAUSED, STATUS_STOPPING}
)

ALLOWED_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_QUEUED: frozenset({STATUS_RUNNING, STATUS_CANCELLED, STATUS_FAILED}),
    STATUS_RUNNING: frozenset(
        {
            STATUS_WAITING_USER,
            STATUS_PAUSED,
            STATUS_STOPPING,
            STATUS_CANCELLED,
            STATUS_COMPLETED,
            STATUS_FAILED,
        }
    ),
    STATUS_WAITING_USER: frozenset(
        {STATUS_RUNNING, STATUS_PAUSED, STATUS_STOPPING, STATUS_CANCELLED, STATUS_FAILED}
    ),
    STATUS_PAUSED: frozenset(
        {STATUS_RUNNING, STATUS_STOPPING, STATUS_CANCELLED, STATUS_FAILED}
    ),
    STATUS_STOPPING: frozenset({STATUS_CANCELLED, STATUS_FAILED}),
    STATUS_CANCELLED: frozenset(),
    STATUS_COMPLETED: frozenset(),
    STATUS_FAILED: frozenset(),
}

# ── Outcomes (independent of lifecycle) ───────────────────────────────────────

OUTCOME_COMPLETE = "complete"
OUTCOME_PARTIAL = "partial"
OUTCOME_INCONCLUSIVE = "inconclusive"
OUTCOME_NONE = "none"

OUTCOMES = frozenset({OUTCOME_COMPLETE, OUTCOME_PARTIAL, OUTCOME_INCONCLUSIVE, OUTCOME_NONE})

# ── Error codes (separate from statuses/outcomes) ─────────────────────────────

ERROR_BUDGET_EXHAUSTED = "budget_exhausted"
ERROR_DOMAIN_NOT_IMPLEMENTED = "domain_not_implemented"
ERROR_UNKNOWN_CALL = "unknown_call"
ERROR_TERMINAL_GUARD = "terminal_guard"
ERROR_PUBLICATION_CONFLICT = "publication_conflict"
ERROR_INTERRUPTED = "interrupted"
ERROR_LATE_COMPLETION = "late_completion"
ERROR_EPOCH_MISMATCH = "epoch_mismatch"
ERROR_DUPLICATE_DISPATCH = "duplicate_dispatch"
ERROR_CALL_OUTSIDE_RUNNING = "call_outside_running"
ERROR_REVISION_CONFLICT = "revision_conflict"
ERROR_IDEMPOTENCY_CONFLICT = "idempotency_conflict"
ERROR_RUN_NOT_FOUND = "run_not_found"
ERROR_ILLEGAL_TRANSITION = "illegal_transition"
ERROR_UNRESOLVED_UNKNOWN = "unresolved_unknown"
ERROR_SETTLEMENT_ALREADY = "settlement_already"

# ── Call statuses ─────────────────────────────────────────────────────────────

CALL_STATUS_PENDING = "pending"
CALL_STATUS_SUCCEEDED = "succeeded"
CALL_STATUS_FAILED = "failed"
CALL_STATUS_PAUSED = "paused"
CALL_STATUS_UNKNOWN = "unknown"
CALL_STATUSES = frozenset(
    {
        CALL_STATUS_PENDING,
        CALL_STATUS_SUCCEEDED,
        CALL_STATUS_FAILED,
        CALL_STATUS_PAUSED,
        CALL_STATUS_UNKNOWN,
    }
)

# ── Budget profiles ───────────────────────────────────────────────────────────

DEFAULT_BUDGET_PROFILE = "standard"
BUDGET_PROFILES: dict[str, dict[str, int]] = {
    "standard": {
        "maxModelCalls": 18,
        "maxTokens": 100000,
        "maxWallClockSeconds": 360,
        "reserveModelCalls": 5,
        "reserveTokens": 50000,
        "maxExternalSearches": 6,
        "maxFulltextFetches": 6,
    },
    "extended": {
        "maxModelCalls": 32,
        "maxTokens": 180000,
        "maxWallClockSeconds": 720,
        "reserveModelCalls": 7,
        "reserveTokens": 80000,
        "maxExternalSearches": 12,
        "maxFulltextFetches": 12,
    },
}

BUDGET_COUNTER_KINDS = ("modelCalls", "tokens", "normalTokens", "elapsedSeconds", "externalSearches", "fulltextFetches")


def resolve_budget_profile(name: str | None) -> tuple[str, dict[str, int]]:
    """Return (profile_name, limits).  Unknown profile raises ValueError."""
    key = (name or DEFAULT_BUDGET_PROFILE).strip().lower()
    if not key:
        key = DEFAULT_BUDGET_PROFILE
    if key not in BUDGET_PROFILES:
        raise ValueError(f"Unknown budget profile: {key!r}")
    return key, dict(BUDGET_PROFILES[key])


# ── Source / material validation ──────────────────────────────────────────────

_MATERIAL_ID_PATTERN = re.compile(r"^[\w\-. ]{1,256}$", re.UNICODE)


def validate_material_id(value: Any) -> str:
    """Accept unicode opaque material identifiers."""
    normalized = str(value or "").strip()
    if not normalized or not _MATERIAL_ID_PATTERN.match(normalized):
        raise ValueError(f"Invalid material id: {value!r}")
    return normalized


def validate_source_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a source descriptor.

    Required keys: ``sourceId``, ``materialId``, ``snapshotVersion``,
    ``snapshotHash`` and ``accessLevel``.  Unknown keys are preserved.
    """
    if not isinstance(record, dict):
        raise TypeError("source record must be a dict")
    source_id = str(record.get("sourceId") or "").strip()
    material_id = str(record.get("materialId") or "").strip()
    snapshot_version = str(record.get("snapshotVersion") or "").strip()
    snapshot_hash = str(record.get("snapshotHash") or "").strip()
    access_level = str(record.get("accessLevel") or "").strip()
    if not source_id:
        raise ValueError("source record missing sourceId")
    if not material_id:
        raise ValueError("source record missing materialId")
    validate_material_id(material_id)
    if not snapshot_version:
        raise ValueError("source record missing snapshotVersion")
    if not snapshot_hash:
        raise ValueError("source record missing snapshotHash")
    if not access_level:
        raise ValueError("source record missing accessLevel")
    normalized = dict(record)
    normalized["sourceId"] = source_id
    normalized["materialId"] = material_id
    normalized["snapshotVersion"] = snapshot_version
    normalized["snapshotHash"] = snapshot_hash
    normalized["accessLevel"] = access_level
    return normalized


# ── Normalizers ───────────────────────────────────────────────────────────────


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def new_run_id() -> str:
    return f"dr_run_{uuid.uuid4().hex}"


def new_call_id(run_id: str, node: str, tool: str, args_digest: str) -> str:
    raw = f"{run_id}|{node}|{tool}|{args_digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def new_publication_id() -> str:
    return f"dr_pub_{uuid.uuid4().hex}"


def normalize_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a run payload while preserving unknown keys.

    Known keys receive defaults when absent; everything else is kept as-is.
    """
    if not isinstance(payload, dict):
        raise TypeError("run payload must be a dict")
    record = dict(payload)
    now = utc_now_iso()
    record.setdefault("contractVersion", CONTRACT_VERSION)
    record.setdefault("engineVersion", ENGINE_VERSION)
    record.setdefault("runId", new_run_id())
    record.setdefault("taskId", "")
    record.setdefault("workspaceId", "")
    record.setdefault("idempotencyKey", "")
    record.setdefault("engine", "")
    record.setdefault("status", STATUS_QUEUED)
    record.setdefault("outcome", OUTCOME_NONE)
    record.setdefault("errorCode", "")
    record.setdefault("stage", "")
    record.setdefault("runRevision", 0)
    record.setdefault("executionEpoch", 0)
    record.setdefault("createdAt", now)
    record.setdefault("updatedAt", now)
    record.setdefault("startedAt", "")
    record.setdefault("finishedAt", "")
    record.setdefault("question", "")
    record.setdefault("pdfId", "")
    record.setdefault("materials", [])
    record.setdefault("constraints", "")
    record.setdefault("requestDigest", "")
    record.setdefault("state", {})
    record.setdefault("result", None)
    record.setdefault("error", None)
    record.setdefault(
        "cancellation", {"requested": False, "requestedAt": "", "reason": ""}
    )
    record.setdefault(
        "pause",
        {"requested": False, "node": "", "reason": "", "payload": None, "requestedAt": ""},
    )
    record.setdefault("resume", {"token": "", "payload": None, "appliedAt": ""})
    budget_defaults = resolve_budget_profile(record.get("budgetProfile"))[1]
    existing_budget = record.get("budget") or {}
    merged_budget = dict(budget_defaults)
    merged_budget.update(existing_budget)
    for counter in BUDGET_COUNTER_KINDS:
        merged_budget.setdefault(counter, 0)
    merged_budget.setdefault("reservedModelCalls", 0)
    merged_budget.setdefault("exhausted", "")
    merged_budget.setdefault(
        "profile", record.get("budgetProfile") or DEFAULT_BUDGET_PROFILE
    )
    record["budget"] = merged_budget
    record.setdefault(
        "publication",
        {
            "published": False,
            "publicationId": "",
            "dedupKey": "",
            "publishedAt": "",
            "reused": False,
        },
    )
    record.setdefault("outbox", [])
    return record


def transition_status(record: dict[str, Any], next_status: str) -> dict[str, Any]:
    """Return a shallow copy with the new status after validating the transition."""
    current = str(record.get("status") or "").strip()
    allowed = ALLOWED_RUN_TRANSITIONS.get(current, frozenset())
    if next_status not in allowed:
        raise IllegalStatusTransitionError(current, next_status)
    updated = dict(record)
    updated["status"] = next_status
    return updated


# ── Errors ────────────────────────────────────────────────────────────────────


class DeepResearchError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


class RunNotFoundError(DeepResearchError):
    def __init__(self, run_id: str):
        super().__init__(ERROR_RUN_NOT_FOUND, f"Run {run_id!r} not found", {"runId": run_id})


class RevisionConflictError(DeepResearchError):
    def __init__(self, run_id: str, expected: int, actual: int):
        super().__init__(
            ERROR_REVISION_CONFLICT,
            f"Run {run_id!r} revision conflict (expected {expected}, actual {actual})",
            {"runId": run_id, "expectedRevision": expected, "actualRevision": actual},
        )


class EpochConflictError(DeepResearchError):
    def __init__(self, run_id: str, expected: int, actual: int):
        super().__init__(
            ERROR_EPOCH_MISMATCH,
            f"Run {run_id!r} epoch conflict (expected {expected}, actual {actual})",
            {"runId": run_id, "expectedEpoch": expected, "actualEpoch": actual},
        )


class IllegalStatusTransitionError(DeepResearchError):
    def __init__(self, current: str, requested: str):
        super().__init__(
            ERROR_ILLEGAL_TRANSITION,
            f"Illegal run transition: {current!r} -> {requested!r}",
            {"currentStatus": current, "requestedStatus": requested},
        )


class IdempotencyConflictError(DeepResearchError):
    def __init__(self, workspace_id: str, key: str):
        super().__init__(
            ERROR_IDEMPOTENCY_CONFLICT,
            "Idempotency key reused with different input",
            {"workspaceId": workspace_id, "idempotencyKey": key},
        )


class BudgetExhaustedError(DeepResearchError):
    def __init__(self, kind: str, limit: int, used: int):
        super().__init__(
            ERROR_BUDGET_EXHAUSTED,
            f"Budget exhausted for {kind}: used {used}/{limit}",
            {"kind": kind, "limit": limit, "used": used},
        )


class DomainToolNotImplementedError(DeepResearchError):
    def __init__(self, tool: str, message: str = ""):
        text = message or f"Domain tool '{tool}' is not wired yet"
        super().__init__(ERROR_DOMAIN_NOT_IMPLEMENTED, text, {"tool": tool})


class UnknownCallError(DeepResearchError):
    def __init__(self, call_id: str):
        super().__init__(
            ERROR_UNKNOWN_CALL,
            f"Call {call_id!r} recorded as unknown and requires manual resolution",
            {"callId": call_id},
        )


class TerminalGuardError(DeepResearchError):
    def __init__(self, run_id: str, status: str):
        super().__init__(
            ERROR_TERMINAL_GUARD,
            f"Run {run_id!r} is terminal ({status}) and cannot resume",
            {"runId": run_id, "status": status},
        )


class PublicationConflictError(DeepResearchError):
    def __init__(self, dedup_key: str):
        super().__init__(
            ERROR_PUBLICATION_CONFLICT,
            "Publication already exists for dedup key",
            {"dedupKey": dedup_key},
        )


class LateCompletionError(DeepResearchError):
    """Raised when a call completion arrives after the run left running."""

    def __init__(self, call_id: str, run_status: str):
        super().__init__(
            ERROR_LATE_COMPLETION,
            f"Call {call_id!r} completed late while run is {run_status}",
            {"callId": call_id, "runStatus": run_status},
        )


class DuplicateDispatchError(DeepResearchError):
    def __init__(self, run_id: str):
        super().__init__(
            ERROR_DUPLICATE_DISPATCH,
            f"Run {run_id!r} already has a pending dispatch",
            {"runId": run_id},
        )


class CallOutsideRunningError(DeepResearchError):
    def __init__(self, run_id: str, status: str):
        super().__init__(
            ERROR_CALL_OUTSIDE_RUNNING,
            f"Cannot reserve calls while run {run_id!r} is {status}",
            {"runId": run_id, "status": status},
        )


class UnresolvedUnknownError(DeepResearchError):
    """Raised when begin_execution finds unresolved unknown calls."""

    def __init__(self, run_id: str, call_ids: list[str]):
        super().__init__(
            ERROR_UNRESOLVED_UNKNOWN,
            f"Run {run_id!r} has {len(call_ids)} unresolved unknown call(s)",
            {"runId": run_id, "unknownCallIds": call_ids},
        )


class SettlementAlreadyError(DeepResearchError):
    """Raised when complete_call attempts to settle an already-settled call."""

    def __init__(self, call_id: str):
        super().__init__(
            ERROR_SETTLEMENT_ALREADY,
            f"Call {call_id!r} has already been settled",
            {"callId": call_id},
        )


def merge_budget_counters(current: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Return a new budget dict with counters incremented by delta.

    Only known counter kinds are summed; unknown keys in ``delta`` are ignored.
    Negative deltas are clamped to zero so counters never go below their origin.
    """
    merged = dict(current)
    for kind in BUDGET_COUNTER_KINDS:
        if kind in delta:
            try:
                increment = int(delta[kind])
            except (TypeError, ValueError):
                continue
            base = int(merged.get(kind) or 0)
            merged[kind] = max(0, base + increment)
    return merged


def check_budget_limits(budget: dict[str, Any]) -> str | None:
    """Return the exhausted counter name or ``None`` when within limits."""
    token_reserve = int(budget.get('reserveTokens') or 0)
    token_maximum = int(budget.get('maxTokens') or 0)
    if token_reserve and token_maximum and int(budget.get('normalTokens') or 0) > max(0, token_maximum - token_reserve):
        return 'normalTokens'
    reserve = int(budget.get("reserveModelCalls") or 0)
    normal = int(budget.get("modelCalls") or 0)
    final = int(budget.get("reservedModelCalls") or 0)
    maximum = int(budget.get("maxModelCalls") or 0)
    if final > reserve or (maximum > 0 and (normal > max(0, maximum - reserve) or normal + final > maximum)):
        return "modelCalls"
    limits = {
        "modelCalls": "maxModelCalls",
        "tokens": "maxTokens",
        "elapsedSeconds": "maxWallClockSeconds",
        "externalSearches": "maxExternalSearches",
        "fulltextFetches": "maxFulltextFetches",
    }
    for counter, limit_key in limits.items():
        limit_value = budget.get(limit_key)
        if limit_value is None:
            continue
        try:
            limit_int = int(limit_value)
        except (TypeError, ValueError):
            continue
        if limit_int <= 0:
            continue
        used = int(budget.get(counter) or 0)
        if used > limit_int:
            return counter
    return None


def check_exploration_headroom(budget: dict[str, Any], node: str) -> tuple[str, int, int] | None:
    """Keep one normal call and its token allowance for bounded claim repair.

    Applied to the proposed reservation, inside the repository transaction.
    This is an earlier exploration stop, never an increase to the total budget.
    """
    if node not in {'extract', 'assess_relevance'}:
        return None
    calls = max(0, int(budget.get('maxModelCalls') or 0) - int(budget.get('reserveModelCalls') or 0))
    if calls > 1 and int(budget.get('modelCalls') or 0) > calls - 1:
        return ('explorationModelCalls', calls - 1, int(budget.get('modelCalls') or 0))
    tokens = max(0, int(budget.get('maxTokens') or 0) - int(budget.get('reserveTokens') or 0))
    # Match the full repair request envelope, not just its output allowance.
    # Small custom budgets still retain exploration capacity.
    from services.deep_research.repair_budget import repair_exploration_headroom
    headroom = repair_exploration_headroom(tokens)
    if tokens and int(budget.get('normalTokens') or 0) > tokens - headroom:
        return ('explorationTokens', tokens - headroom, int(budget.get('normalTokens') or 0))
    return None
