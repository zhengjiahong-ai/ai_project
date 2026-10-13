"""Core tests for Deep Research contracts and repository (v2).

Covers exact lifecycle/outcome/error values, concurrency, budget reserve
isolation, unknown retention, epoch late-result protection, report/outbox
atomicity, recovery semantics, settlement guards, and publication conflicts.
No LangGraph imports.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from services.deep_research.contracts import (
    ACTIVE_STATUSES,
    BUDGET_COUNTER_KINDS,
    BUDGET_PROFILES,
    CALL_STATUS_FAILED,
    CALL_STATUS_PAUSED,
    CALL_STATUS_PENDING,
    CALL_STATUS_SUCCEEDED,
    CALL_STATUS_UNKNOWN,
    CONTRACT_VERSION,
    CallOutsideRunningError,
    DEFAULT_BUDGET_PROFILE,
    DomainToolNotImplementedError,
    DuplicateDispatchError,
    ENGINE_VERSION,
    EpochConflictError,
    ERROR_BUDGET_EXHAUSTED,
    ERROR_CALL_OUTSIDE_RUNNING,
    ERROR_DOMAIN_NOT_IMPLEMENTED,
    ERROR_DUPLICATE_DISPATCH,
    ERROR_EPOCH_MISMATCH,
    ERROR_IDEMPOTENCY_CONFLICT,
    ERROR_ILLEGAL_TRANSITION,
    ERROR_INTERRUPTED,
    ERROR_LATE_COMPLETION,
    ERROR_PUBLICATION_CONFLICT,
    ERROR_REVISION_CONFLICT,
    ERROR_RUN_NOT_FOUND,
    ERROR_SETTLEMENT_ALREADY,
    ERROR_TERMINAL_GUARD,
    ERROR_UNKNOWN_CALL,
    ERROR_UNRESOLVED_UNKNOWN,
    IdempotencyConflictError,
    IllegalStatusTransitionError,
    LateCompletionError,
    OUTCOME_COMPLETE,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_NONE,
    OUTCOME_PARTIAL,
    OUTCOMES,
    PublicationConflictError,
    RunNotFoundError,
    RevisionConflictError,
    SettlementAlreadyError,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_STOPPING,
    STATUS_WAITING_USER,
    TERMINAL_STATUSES,
    TerminalGuardError,
    UnknownCallError,
    UnresolvedUnknownError,
    check_budget_limits,
    digest,
    merge_budget_counters,
    normalize_run,
    resolve_budget_profile,
    transition_status,
    validate_material_id,
    validate_source_record,
)
from services.deep_research.repository import DeepResearchRepository


@pytest.fixture
def repo(tmp_path: Path) -> DeepResearchRepository:
    db = tmp_path / "deep_research.sqlite3"
    repository = DeepResearchRepository(str(db))
    repository.initialize()
    return repository


# ── exact contract values ─────────────────────────────────────────────────────


def test_contract_and_engine_versions_are_fixed():
    assert CONTRACT_VERSION == 2
    assert ENGINE_VERSION == "deep-research-v2"


def test_waiting_for_human_input_does_not_spend_or_reset_active_time(repo):
    from datetime import datetime, UTC, timedelta
    now = datetime.now(UTC)
    started = (now - timedelta(minutes=20)).isoformat()
    waiting = (now - timedelta(minutes=19)).isoformat()
    repo.create_run({'runId': 'waiting-time'})
    repo.begin_execution('waiting-time')
    repo.update_run('waiting-time', lambda r: {**r, 'status': STATUS_WAITING_USER, 'startedAt': started,
        'state': {**r.get('state', {}), 'waitingSince': waiting}})
    resumed = repo.begin_execution('waiting-time')
    active_seconds = (datetime.now(UTC) - datetime.fromisoformat(resumed['startedAt'])).total_seconds()
    assert 59 <= active_seconds <= 62
    assert resumed['firstStartedAt'] == started and resumed['budget']['waitingSeconds'] > 1139
    assert resumed['state']['waitingSince'] is None
    repo.transition('waiting-time', STATUS_PAUSED)
    assert repo.begin_execution('waiting-time')['startedAt'] == resumed['startedAt']


def test_lifecycle_statuses_match_design():
    expected = {
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_WAITING_USER,
        STATUS_PAUSED,
        STATUS_STOPPING,
        STATUS_CANCELLED,
        STATUS_COMPLETED,
        STATUS_FAILED,
    }
    assert set(ACTIVE_STATUSES | TERMINAL_STATUSES) == expected
    assert TERMINAL_STATUSES == {STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED}
    assert STATUS_QUEUED in ACTIVE_STATUSES
    assert STATUS_STOPPING in ACTIVE_STATUSES


def test_outcomes_are_independent_of_lifecycle():
    assert OUTCOMES == {OUTCOME_COMPLETE, OUTCOME_PARTIAL, OUTCOME_INCONCLUSIVE, OUTCOME_NONE}
    # outcomes must not collide with any status string
    from services.deep_research.contracts import RUN_STATUSES

    assert OUTCOMES.isdisjoint(RUN_STATUSES)


def test_error_codes_are_distinct_from_statuses_and_outcomes():
    from services.deep_research.contracts import RUN_STATUSES

    error_codes = {
        ERROR_BUDGET_EXHAUSTED,
        ERROR_DOMAIN_NOT_IMPLEMENTED,
        ERROR_UNKNOWN_CALL,
        ERROR_TERMINAL_GUARD,
        ERROR_INTERRUPTED,
        ERROR_LATE_COMPLETION,
        ERROR_EPOCH_MISMATCH,
        ERROR_DUPLICATE_DISPATCH,
        ERROR_CALL_OUTSIDE_RUNNING,
        ERROR_REVISION_CONFLICT,
        ERROR_IDEMPOTENCY_CONFLICT,
        ERROR_RUN_NOT_FOUND,
        ERROR_ILLEGAL_TRANSITION,
        ERROR_PUBLICATION_CONFLICT,
        ERROR_UNRESOLVED_UNKNOWN,
        ERROR_SETTLEMENT_ALREADY,
    }
    assert error_codes.isdisjoint(RUN_STATUSES)
    assert error_codes.isdisjoint(OUTCOMES)


def test_budget_profiles_match_spec():
    standard = BUDGET_PROFILES["standard"]
    assert standard["maxModelCalls"] == 18
    assert standard["maxTokens"] == 100000
    assert standard["maxWallClockSeconds"] == 360
    assert standard["reserveModelCalls"] == 5
    extended = BUDGET_PROFILES["extended"]
    assert extended["maxModelCalls"] == 32
    assert extended["maxTokens"] == 180000
    assert extended["maxWallClockSeconds"] == 720
    assert extended["reserveModelCalls"] == 7


def test_normalize_run_defaults_to_v2_schema():
    record = normalize_run({"question": "q"})
    assert record["contractVersion"] == CONTRACT_VERSION
    assert record["engineVersion"] == ENGINE_VERSION
    assert record["status"] == STATUS_QUEUED
    assert record["outcome"] == OUTCOME_NONE
    assert record["errorCode"] == ""
    assert record["runRevision"] == 0
    assert record["executionEpoch"] == 0
    assert record["budget"]["profile"] == DEFAULT_BUDGET_PROFILE
    assert record["budget"]["reservedModelCalls"] == 0


def test_validate_material_id_accepts_unicode_opaque_ids():
    assert validate_material_id("材料-α") == "材料-α"
    assert validate_material_id("pdf 日本語") == "pdf 日本語"
    with pytest.raises(ValueError):
        validate_material_id("")


def test_validate_source_record_requires_immutable_snapshot_fields():
    source = validate_source_record(
        {
            "sourceId": "s1",
            "materialId": "m1",
            "snapshotVersion": "v3",
            "snapshotHash": "abc123",
            "accessLevel": "read",
            "extra": 7,
        }
    )
    assert source["snapshotVersion"] == "v3"
    assert source["snapshotHash"] == "abc123"
    assert source["accessLevel"] == "read"
    assert source["extra"] == 7
    with pytest.raises(ValueError):
        validate_source_record({"sourceId": "s1", "materialId": "m1"})


def test_merge_budget_counters_sums_known_and_clamps_negative():
    current = {"modelCalls": 3, "tokens": 100, "custom": "keep"}
    merged = merge_budget_counters(current, {"modelCalls": 2, "tokens": -500, "unknownKey": 9})
    assert merged["modelCalls"] == 5
    assert merged["tokens"] == 0
    assert merged["custom"] == "keep"
    assert "unknownKey" not in merged


def test_check_budget_limits_returns_first_exhausted_counter():
    budget = {"maxModelCalls": 2, "modelCalls": 3, "maxTokens": 10, "tokens": 1}
    assert check_budget_limits(budget) == "modelCalls"
    assert check_budget_limits({"maxModelCalls": 5, "modelCalls": 2}) is None
    assert check_budget_limits({"maxModelCalls": 0, "modelCalls": 99}) is None


# ── repository lifecycle ─────────────────────────────────────────────────────


def test_create_run_is_idempotent_by_key(repo: DeepResearchRepository):
    payload = {
        "runId": "dr_run_alpha",
        "workspaceId": "ws1",
        "idempotencyKey": "idem-1",
        "requestDigest": digest({"q": "one"}),
        "question": "one",
    }
    first, created = repo.create_run(payload)
    assert created is True
    second, created_again = repo.create_run(payload)
    assert created_again is False
    assert second["runId"] == first["runId"]
    assert second["runRevision"] == first["runRevision"]


def test_create_run_detects_idempotency_conflict(repo: DeepResearchRepository):
    base = {
        "workspaceId": "ws1",
        "idempotencyKey": "idem-conflict",
        "requestDigest": digest({"q": "original"}),
        "question": "original",
    }
    repo.create_run(base)
    conflicting = dict(base)
    conflicting["requestDigest"] = digest({"q": "changed"})
    with pytest.raises(IdempotencyConflictError):
        repo.create_run(conflicting)


def test_get_run_returns_none_for_missing(repo: DeepResearchRepository):
    assert repo.get_run("missing") is None
    with pytest.raises(RunNotFoundError):
        repo.require_run("missing")


def test_list_runs_filters_by_workspace_and_status(repo: DeepResearchRepository):
    repo.create_run({"runId": "r1", "workspaceId": "wsA", "status": STATUS_QUEUED})
    repo.create_run({"runId": "r2", "workspaceId": "wsB", "status": STATUS_QUEUED})
    repo.create_run({"runId": "r3", "workspaceId": "wsA", "status": STATUS_FAILED})
    ws_a = repo.list_runs(workspace_id="wsA")
    assert {item["runId"] for item in ws_a} == {"r1", "r3"}
    queued = repo.list_runs(statuses=[STATUS_QUEUED])
    assert {item["runId"] for item in queued} == {"r1", "r2"}


def test_update_run_enforces_revision(repo: DeepResearchRepository):
    record, _ = repo.create_run({"runId": "rev-test"})
    updated = repo.update_run(
        "rev-test",
        lambda r: {**r, "stage": "plan"},
        expected_revision=record["runRevision"],
    )
    assert updated["runRevision"] == record["runRevision"] + 1
    with pytest.raises(Exception):
        repo.update_run(
            "rev-test",
            lambda r: {**r, "stage": "acquire"},
            expected_revision=record["runRevision"],
        )


def test_transition_validates_state_machine(repo: DeepResearchRepository):
    repo.create_run({"runId": "trans-test"})
    repo.transition("trans-test", STATUS_RUNNING)
    repo.transition("trans-test", STATUS_COMPLETED)
    with pytest.raises(IllegalStatusTransitionError):
        repo.transition("trans-test", STATUS_QUEUED)


def test_begin_execution_increments_epoch_and_rejects_duplicate_dispatch(repo: DeepResearchRepository):
    repo.create_run({"runId": "epoch-test"})
    started = repo.begin_execution("epoch-test")
    assert started["executionEpoch"] == 1
    assert started["status"] == STATUS_RUNNING
    with pytest.raises(DuplicateDispatchError):
        repo.begin_execution("epoch-test")


def test_begin_execution_blocks_terminal_runs(repo: DeepResearchRepository):
    repo.create_run({"runId": "term-guard"})
    repo.begin_execution("term-guard")
    repo.transition("term-guard", STATUS_COMPLETED)
    with pytest.raises(TerminalGuardError):
        repo.begin_execution("term-guard")


def test_begin_execution_detects_epoch_conflict(repo: DeepResearchRepository):
    repo.create_run({"runId": "epoch-conflict"})
    repo.begin_execution("epoch-conflict")
    with pytest.raises(EpochConflictError):
        repo.begin_execution("epoch-conflict", expected_epoch=0)


def test_begin_execution_resets_started_at_only_on_first_execution(repo: DeepResearchRepository):
    """Wall-clock deadline must not restart on re-entry after pause."""
    repo.create_run({"runId": "started-at-guard"})
    first = repo.begin_execution("started-at-guard")
    original_started = first["startedAt"]
    assert original_started != ""
    # Pause and re-enter
    repo.transition("started-at-guard", STATUS_PAUSED)
    second = repo.begin_execution("started-at-guard")
    assert second["executionEpoch"] == 2
    # startedAt must remain the original value
    assert second["startedAt"] == original_started


def test_begin_execution_rejects_unresolved_unknown_calls(repo: DeepResearchRepository):
    """Runs with unresolved unknown calls cannot resume execution."""
    repo.create_run({"runId": "unknown-block-resume"})
    repo.begin_execution("unknown-block-resume")
    call, _ = repo.reserve_call(
        run_id="unknown-block-resume",
        node="read",
        tool="read",
        args_digest=digest({"ub": 1}),
    )
    repo.complete_call(call["callId"], status=CALL_STATUS_UNKNOWN, error={"reason": "timeout"})
    repo.transition("unknown-block-resume", STATUS_PAUSED)
    with pytest.raises(UnresolvedUnknownError):
        repo.begin_execution("unknown-block-resume")


# ── durable calls & budget reserve ────────────────────────────────────────────


def test_reserve_call_creates_pending_and_reuses_succeeded(repo: DeepResearchRepository):
    repo.create_run({"runId": "call-reuse"})
    repo.begin_execution("call-reuse")
    call, reused = repo.reserve_call(
        run_id="call-reuse", node="plan", tool="plan", args_digest=digest({"x": 1})
    )
    assert reused is False
    assert call["status"] == CALL_STATUS_PENDING
    repo.complete_call(call["callId"], status=CALL_STATUS_SUCCEEDED, result={"ok": True})
    reused_call, reused_flag = repo.reserve_call(
        run_id="call-reuse", node="plan", tool="plan", args_digest=digest({"x": 1})
    )
    assert reused_flag is True
    assert reused_call["result"] == {"ok": True}


def test_reserve_call_accounts_budget_atomically(repo: DeepResearchRepository):
    repo.create_run({"runId": "budget-reserve", "budget": {"maxModelCalls": 2, "reserveModelCalls": 0}})
    repo.begin_execution("budget-reserve")
    first, _ = repo.reserve_call(
        run_id="budget-reserve",
        node="plan",
        tool="plan",
        args_digest=digest({"b": 1}),
        budget_delta={"modelCalls": 1},
    )
    assert first["status"] == CALL_STATUS_PENDING
    run_after_first = repo.require_run("budget-reserve")
    assert run_after_first["budget"]["modelCalls"] == 1
    second, _ = repo.reserve_call(
        run_id="budget-reserve",
        node="acquire",
        tool="acquire",
        args_digest=digest({"b": 2}),
        budget_delta={"modelCalls": 1},
    )
    run_after_second = repo.require_run("budget-reserve")
    assert run_after_second["budget"]["modelCalls"] == 2
    from services.deep_research.contracts import BudgetExhaustedError

    with pytest.raises(BudgetExhaustedError):
        repo.reserve_call(
            run_id="budget-reserve",
            node="read",
            tool="read",
            args_digest=digest({"b": 3}),
            budget_delta={"modelCalls": 1},
        )
    run_after_failure = repo.require_run("budget-reserve")
    assert run_after_failure["budget"]["modelCalls"] == 2


def test_reserve_call_isolates_reserve_pool(repo: DeepResearchRepository):
    repo.create_run({"runId": "reserve-pool", "budget": {"maxModelCalls": 5, "reserveModelCalls": 3}})
    repo.begin_execution("reserve-pool")
    normal, _ = repo.reserve_call(
        run_id="reserve-pool",
        node="plan",
        tool="plan",
        args_digest=digest({"rp": 1}),
        budget_delta={"modelCalls": 1},
    )
    assert normal["usesReserve"] is False
    reserved, _ = repo.reserve_call(
        run_id="reserve-pool",
        node="verify",
        tool="verify",
        args_digest=digest({"rp": 2}),
        budget_delta={"modelCalls": 2},
        use_reserve=True,
    )
    assert reserved["usesReserve"] is True
    run_record = repo.require_run("reserve-pool")
    assert run_record["budget"]["modelCalls"] == 1
    assert run_record["budget"]["reservedModelCalls"] == 2
    # Normal calls cannot consume reserve even when main budget exhausted
    from services.deep_research.contracts import BudgetExhaustedError

    repo.reserve_call(
        run_id="reserve-pool",
        node="acquire",
        tool="acquire",
        args_digest=digest({"rp": 3}),
        budget_delta={"modelCalls": 1},
    )
    with pytest.raises(BudgetExhaustedError):
        repo.reserve_call(
            run_id="reserve-pool",
            node="read",
            tool="read",
            args_digest=digest({"rp": 4}),
            budget_delta={"modelCalls": 1},
        )
    # Reserve pool still intact
    final = repo.require_run("reserve-pool")
    assert final["budget"]["reservedModelCalls"] == 2


def test_reserve_pool_does_not_reduce_total_max_model_calls(repo: DeepResearchRepository):
    """Reserve pool is additive to maxModelCalls, not subtractive."""
    record, _ = repo.create_run({
        "runId": "reserve-additive",
        "budget": {"maxModelCalls": 18, "reserveModelCalls": 3},
    })
    # maxModelCalls stays at 18; reserveModelCalls is separate
    assert record["budget"]["maxModelCalls"] == 18
    assert record["budget"]["reserveModelCalls"] == 3
    repo.begin_execution("reserve-additive")
    # Use all 18 normal calls
    for i in range(15):
        repo.reserve_call(
            run_id="reserve-additive",
            node=f"node-{i}",
            tool="tool",
            args_digest=digest({"ra": i}),
            budget_delta={"modelCalls": 1},
        )
    run_after = repo.require_run("reserve-additive")
    assert run_after["budget"]["modelCalls"] == 15
    # Reserve pool still available
    assert run_after["budget"]["reservedModelCalls"] == 0
    reserved, _ = repo.reserve_call(
        run_id="reserve-additive",
        node="reserve-node",
        tool="verify",
        args_digest=digest({"ra": "reserve"}),
        budget_delta={"modelCalls": 2},
        use_reserve=True,
    )
    assert reserved["usesReserve"] is True
    final = repo.require_run("reserve-additive")
    assert final["budget"]["reservedModelCalls"] == 2


def test_reserve_call_rejects_non_running_runs(repo: DeepResearchRepository):
    repo.create_run({"runId": "outside-running"})
    with pytest.raises(CallOutsideRunningError):
        repo.reserve_call(
            run_id="outside-running",
            node="plan",
            tool="plan",
            args_digest=digest({"or": 1}),
        )


def test_unknown_call_retains_budget_and_blocks_reissue(repo: DeepResearchRepository):
    repo.create_run({"runId": "unknown-block", "budget": {"maxModelCalls": 5, "reserveModelCalls": 3}})
    repo.begin_execution("unknown-block")
    call, _ = repo.reserve_call(
        run_id="unknown-block",
        node="read",
        tool="read",
        args_digest=digest({"z": 3}),
        budget_delta={"modelCalls": 2},
    )
    repo.complete_call(call["callId"], status=CALL_STATUS_UNKNOWN, error={"reason": "manual"})
    run_record = repo.require_run("unknown-block")
    assert run_record["budget"]["modelCalls"] == 2
    with pytest.raises(UnknownCallError):
        repo.reserve_call(
            run_id="unknown-block",
            node="read",
            tool="read",
            args_digest=digest({"z": 3}),
        )


def test_complete_call_settles_actual_usage(repo: DeepResearchRepository):
    repo.create_run({"runId": "settle-usage"})
    repo.begin_execution("settle-usage")
    call, _ = repo.reserve_call(
        run_id="settle-usage",
        node="assess",
        tool="assess",
        args_digest=digest({"su": 1}),
        budget_delta={"modelCalls": 5, "tokens": 1000},
    )
    repo.complete_call(
        call["callId"],
        status=CALL_STATUS_SUCCEEDED,
        result={"ok": True},
        budget_delta={"modelCalls": -2, "tokens": -400},
    )
    run_record = repo.require_run("settle-usage")
    assert run_record["budget"]["modelCalls"] == 3
    assert run_record["budget"]["tokens"] == 600


def test_per_call_reserved_tokens_persisted(repo: DeepResearchRepository):
    """reservedTokens is stored on the call record at reservation time."""
    repo.create_run({"runId": "reserved-tokens-persist"})
    repo.begin_execution("reserved-tokens-persist")
    call, _ = repo.reserve_call(
        run_id="reserved-tokens-persist",
        node="extract",
        tool="extract",
        args_digest=digest({"rt": 1}),
        budget_delta={"tokens": 5000},
    )
    assert call["reservedTokens"] == 5000
    assert call["settled"] is False


def test_settlement_only_once(repo: DeepResearchRepository):
    """Budget settlement can only occur once per call."""
    repo.create_run({"runId": "settle-once"})
    repo.begin_execution("settle-once")
    call, _ = repo.reserve_call(
        run_id="settle-once",
        node="assess",
        tool="assess",
        args_digest=digest({"so": 1}),
        budget_delta={"modelCalls": 3, "tokens": 2000},
    )
    repo.complete_call(
        call["callId"],
        status=CALL_STATUS_SUCCEEDED,
        result={"ok": True},
        budget_delta={"modelCalls": -1, "tokens": -500},
    )
    completed_call = repo.get_call(call["callId"])
    assert completed_call["settled"] is True
    # Second settlement attempt must fail
    with pytest.raises(SettlementAlreadyError):
        repo.complete_call(
            call["callId"],
            status=CALL_STATUS_SUCCEEDED,
            result={"ok": True},
            budget_delta={"modelCalls": -1},
        )


def test_settlement_bounded_against_reservation(repo: DeepResearchRepository):
    """Token refund cannot exceed the per-call reservedTokens."""
    repo.create_run({"runId": "settle-bound"})
    repo.begin_execution("settle-bound")
    call, _ = repo.reserve_call(
        run_id="settle-bound",
        node="read",
        tool="read",
        args_digest=digest({"sb": 1}),
        budget_delta={"tokens": 1000},
    )
    assert call["reservedTokens"] == 1000
    # Try to refund more than reserved — bounded to -1000
    repo.complete_call(
        call["callId"],
        status=CALL_STATUS_SUCCEEDED,
        result={"ok": True},
        budget_delta={"tokens": -5000},
    )
    run_record = repo.require_run("settle-bound")
    # Reserved 1000, refunded at most 1000 → net tokens = 0
    assert run_record["budget"]["tokens"] == 0


def test_complete_call_blocks_late_completion_when_paused(repo: DeepResearchRepository):
    repo.create_run({"runId": "late-pause"})
    repo.begin_execution("late-pause")
    call, _ = repo.reserve_call(
        run_id="late-pause", node="synthesize", tool="synthesize", args_digest=digest({"lp": 1})
    )
    repo.transition("late-pause", STATUS_PAUSED)
    with pytest.raises(LateCompletionError):
        repo.complete_call(call["callId"], status=CALL_STATUS_SUCCEEDED, result={"v": 1})
    allowed = repo.complete_call(
        call["callId"], status=CALL_STATUS_SUCCEEDED, result={"v": 1}, allow_late=True
    )
    assert allowed["status"] == CALL_STATUS_SUCCEEDED
    assert repo.require_run("late-pause")["status"] == STATUS_PAUSED


def test_complete_call_blocks_late_completion_when_cancelled(repo: DeepResearchRepository):
    repo.create_run({"runId": "late-cancel"})
    repo.begin_execution("late-cancel")
    call, _ = repo.reserve_call(
        run_id="late-cancel", node="extract", tool="extract", args_digest=digest({"lc": 1})
    )
    repo.transition("late-cancel", STATUS_STOPPING)
    repo.transition("late-cancel", STATUS_CANCELLED)
    with pytest.raises(LateCompletionError):
        repo.complete_call(call["callId"], status=CALL_STATUS_FAILED, error={"code": "timeout"})
    allowed = repo.complete_call(
        call["callId"], status=CALL_STATUS_FAILED, error={"code": "timeout"}, allow_late=True
    )
    assert allowed["status"] == CALL_STATUS_FAILED
    assert repo.require_run("late-cancel")["status"] == STATUS_CANCELLED


def test_epoch_protects_stale_completions(repo: DeepResearchRepository):
    repo.create_run({"runId": "epoch-protect"})
    repo.begin_execution("epoch-protect")  # epoch 1
    call, _ = repo.reserve_call(
        run_id="epoch-protect",
        node="plan",
        tool="plan",
        args_digest=digest({"ep": 1}),
    )
    assert call["executionEpoch"] == 1
    # Pause and re-enter creates epoch 2
    repo.transition("epoch-protect", STATUS_PAUSED)
    repo.begin_execution("epoch-protect")  # epoch 2
    # Completion from epoch-1 call must be rejected against current epoch 2
    with pytest.raises(EpochConflictError):
        repo.complete_call(
            call["callId"],
            status=CALL_STATUS_SUCCEEDED,
            result={"stale": True},
        )


def test_allow_late_is_audit_only_and_does_not_modify_budget(repo: DeepResearchRepository):
    repo.create_run({"runId": "late-audit", "budget": {"maxModelCalls": 10}})
    repo.begin_execution("late-audit")
    call, _ = repo.reserve_call(
        run_id="late-audit",
        node="assess",
        tool="assess",
        args_digest=digest({"la": 1}),
        budget_delta={"modelCalls": 3},
    )
    repo.transition("late-audit", STATUS_PAUSED)
    budget_before = repo.require_run("late-audit")["budget"]["modelCalls"]
    repo.complete_call(
        call["callId"],
        status=CALL_STATUS_SUCCEEDED,
        result={"v": 1},
        budget_delta={"modelCalls": -1},
        allow_late=True,
    )
    budget_after = repo.require_run("late-audit")["budget"]["modelCalls"]
    assert budget_after == budget_before  # budget unchanged by late completion
    assert repo.require_run("late-audit")["status"] == STATUS_PAUSED


def test_failed_calls_are_not_automatically_rereserved(repo: DeepResearchRepository):
    repo.create_run({"runId": "no-rereserve"})
    repo.begin_execution("no-rereserve")
    call, _ = repo.reserve_call(
        run_id="no-rereserve",
        node="extract",
        tool="extract",
        args_digest=digest({"nr": 1}),
    )
    repo.complete_call(call["callId"], status=CALL_STATUS_FAILED, error={"code": "timeout"})
    with pytest.raises(IllegalStatusTransitionError):
        repo.reserve_call(
            run_id="no-rereserve",
            node="extract",
            tool="extract",
            args_digest=digest({"nr": 1}),
        )


def test_client_budget_override_cannot_widen_server_profile(repo: DeepResearchRepository):
    record, _ = repo.create_run({
        "runId": "clamp-budget",
        "budget": {"maxModelCalls": 999, "maxTokens": 999999, "maxWallClockSeconds": 9999},
    })
    # Server standard profile caps at 18/100000/360
    assert record["budget"]["maxModelCalls"] == 18
    assert record["budget"]["maxTokens"] == 100000
    assert record["budget"]["maxWallClockSeconds"] == 360


# ── recovery & crash windows ─────────────────────────────────────────────────


def test_recover_pauses_running_runs_instead_of_failing(repo: DeepResearchRepository):
    """Recovery pauses interrupted nonterminal runs instead of failing them."""
    repo.create_run({"runId": "recover-pause"})
    repo.begin_execution("recover-pause")
    call, _ = repo.reserve_call(
        run_id="recover-pause", node="extract", tool="extract", args_digest=digest({"rp": 1})
    )
    affected = repo.recover(reason="service_restart")
    assert "recover-pause" in affected
    recovered_run = repo.require_run("recover-pause")
    assert recovered_run["status"] == STATUS_PAUSED
    assert recovered_run["pause"]["requested"] is True
    assert recovered_run["pause"]["reason"] == "service_restart"
    # Pending call becomes unknown
    recovered_call = repo.get_call(call["callId"])
    assert recovered_call["status"] == CALL_STATUS_UNKNOWN


def test_recover_preserves_queued_runs(repo: DeepResearchRepository):
    """Queued runs that were never dispatched stay queued."""
    repo.create_run({"runId": "queued-stays"})
    affected = repo.recover(reason="noop")
    assert "queued-stays" in affected
    assert repo.require_run("queued-stays")["status"] == STATUS_QUEUED


def test_recover_cancels_stopping_runs(repo: DeepResearchRepository):
    """Stopping runs become cancelled during recovery."""
    repo.create_run({"runId": "stopping-cancel"})
    repo.begin_execution("stopping-cancel")
    repo.transition("stopping-cancel", STATUS_STOPPING)
    affected = repo.recover(reason="shutdown")
    assert "stopping-cancel" in affected
    recovered = repo.require_run("stopping-cancel")
    assert recovered["status"] == STATUS_CANCELLED
    assert recovered["cancellation"]["reason"] == "shutdown"


def test_recover_preserves_paused_and_waiting_user_runs(repo: DeepResearchRepository):
    repo.create_run({"runId": "pause-preserve"})
    repo.begin_execution("pause-preserve")
    repo.transition("pause-preserve", STATUS_PAUSED)
    repo.create_run({"runId": "wait-preserve"})
    repo.begin_execution("wait-preserve")
    repo.transition("wait-preserve", STATUS_WAITING_USER)
    affected = repo.recover(reason="noop")
    assert "pause-preserve" not in affected
    assert "wait-preserve" not in affected
    assert repo.require_run("pause-preserve")["status"] == STATUS_PAUSED
    assert repo.require_run("wait-preserve")["status"] == STATUS_WAITING_USER


# ── publications & outbox atomicity ───────────────────────────────────────────


def test_publish_report_starts_outbox_unpublished(repo: DeepResearchRepository):
    """Outbox entries from publish_report start with published=0."""
    repo.create_run({"runId": "pub-unpublished"})
    repo.begin_execution("pub-unpublished")
    pub, created = repo.publish_report(
        run_id="pub-unpublished", dedup_key="dk-up", payload={"report": "v1"}
    )
    assert created is True
    outbox = repo.list_outbox("pub-unpublished", include_published=True)
    assert len(outbox) == 1
    assert outbox[0]["published"] is False


def test_acknowledge_outbox_marks_published(repo: DeepResearchRepository):
    """Explicit acknowledge marks outbox entry as published."""
    repo.create_run({"runId": "ack-outbox"})
    repo.begin_execution("ack-outbox")
    pub, _ = repo.publish_report(
        run_id="ack-outbox", dedup_key="dk-ack", payload={"report": "v1"}
    )
    outbox_before = repo.list_outbox("ack-outbox")
    assert len(outbox_before) == 1
    seq = outbox_before[0]["seq"]
    acked = repo.acknowledge_outbox("ack-outbox", seq)
    assert acked["published"] is True
    # No longer appears in unpublished list
    remaining = repo.list_outbox("ack-outbox")
    assert len(remaining) == 0
    # Still visible with include_published
    all_entries = repo.list_outbox("ack-outbox", include_published=True)
    assert len(all_entries) == 1
    assert all_entries[0]["published"] is True


def test_publish_report_conflicts_on_different_payload(repo: DeepResearchRepository):
    """Duplicate dedup key with different payload raises PublicationConflictError."""
    repo.create_run({"runId": "pub-conflict-1"})
    repo.begin_execution("pub-conflict-1")
    repo.publish_report(
        run_id="pub-conflict-1", dedup_key="dk-conflict", payload={"report": "v1"}
    )
    with pytest.raises(PublicationConflictError):
        repo.publish_report(
            run_id="pub-conflict-1", dedup_key="dk-conflict", payload={"report": "v2"}
        )


def test_publish_report_conflicts_on_different_run(repo: DeepResearchRepository):
    """Duplicate dedup key with different run_id raises PublicationConflictError."""
    repo.create_run({"runId": "pub-run-a"})
    repo.begin_execution("pub-run-a")
    repo.create_run({"runId": "pub-run-b"})
    repo.begin_execution("pub-run-b")
    repo.publish_report(
        run_id="pub-run-a", dedup_key="dk-run-conflict", payload={"report": "same"}
    )
    with pytest.raises(PublicationConflictError):
        repo.publish_report(
            run_id="pub-run-b", dedup_key="dk-run-conflict", payload={"report": "same"}
        )


def test_publish_report_idempotent_same_run_and_payload(repo: DeepResearchRepository):
    """Same run + same payload returns existing without conflict."""
    repo.create_run({"runId": "pub-idem"})
    repo.begin_execution("pub-idem")
    first, created = repo.publish_report(
        run_id="pub-idem", dedup_key="dk-idem", payload={"report": "v1"}
    )
    assert created is True
    second, created_again = repo.publish_report(
        run_id="pub-idem", dedup_key="dk-idem", payload={"report": "v1"}
    )
    assert created_again is False
    assert second["publicationId"] == first["publicationId"]


def test_publish_report_atomically_updates_run(repo: DeepResearchRepository):
    """Publication atomically updates run record with result/outcome/status."""
    repo.create_run({"runId": "pub-atomic"})
    repo.begin_execution("pub-atomic")
    pub, created = repo.publish_report(
        run_id="pub-atomic",
        dedup_key="dk-atomic",
        payload={"summary": "final"},
        outcome=OUTCOME_COMPLETE,
        report_text="Full report text",
    )
    assert created is True
    run_record = repo.require_run("pub-atomic")
    assert run_record["status"] == STATUS_COMPLETED
    assert run_record["outcome"] == OUTCOME_COMPLETE
    assert run_record["result"] == {"summary": "final"}
    assert run_record["report"] == "Full report text"
    assert run_record["finishedAt"] != ""
    assert run_record["publication"]["published"] is False
    assert run_record["publication"]["dedupKey"] == "dk-atomic"


def test_publish_report_under_revision_guard(repo: DeepResearchRepository):
    """Publication respects expected_revision guard."""
    repo.create_run({"runId": "pub-rev-guard"})
    repo.begin_execution("pub-rev-guard")
    record = repo.require_run("pub-rev-guard")
    # Wrong revision must fail
    with pytest.raises(RevisionConflictError):
        repo.publish_report(
            run_id="pub-rev-guard",
            dedup_key="dk-rev",
            payload={"r": 1},
            expected_revision=record["runRevision"] + 99,
        )
    # Correct revision succeeds
    pub, created = repo.publish_report(
        run_id="pub-rev-guard",
        dedup_key="dk-rev",
        payload={"r": 1},
        expected_revision=record["runRevision"],
    )
    assert created is True


def test_append_outbox_tracks_unpublished_entries(repo: DeepResearchRepository):
    repo.create_run({"runId": "outbox-run"})
    entry = repo.append_outbox(run_id="outbox-run", kind="artifact", payload={"path": "/tmp/x"})
    assert entry["published"] is False
    entries = repo.list_outbox("outbox-run")
    assert entries[0]["seq"] == entry["seq"]


# ── concurrency ───────────────────────────────────────────────────────────────


def test_concurrent_creates_are_serialized(repo: DeepResearchRepository):
    results: list[tuple[bool, str]] = []
    lock = threading.Lock()

    def worker(idx: int) -> None:
        payload = {
            "runId": f"concurrent-{idx}",
            "workspaceId": "ws-concurrent",
            "idempotencyKey": "shared-key",
            "requestDigest": digest({"shared": True}),
            "question": "shared",
        }
        record, created = repo.create_run(payload)
        with lock:
            results.append((created, record["runId"]))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker, idx) for idx in range(8)]
        for future in as_completed(futures):
            future.result()

    created_flags = [flag for flag, _ in results]
    assert sum(created_flags) == 1
    run_ids = {run_id for _, run_id in results}
    assert len(run_ids) == 1


def test_concurrent_budget_reservations_stay_within_limit(repo: DeepResearchRepository):
    repo.create_run({"runId": "concurrent-budget", "budget": {"maxModelCalls": 4, "reserveModelCalls": 0}})
    repo.begin_execution("concurrent-budget")
    successes: list[str] = []
    failures: list[str] = []
    lock = threading.Lock()

    def worker(idx: int) -> None:
        try:
            call, _ = repo.reserve_call(
                run_id="concurrent-budget",
                node=f"node-{idx}",
                tool="tool",
                args_digest=digest({"idx": idx}),
                budget_delta={"modelCalls": 1},
            )
            with lock:
                successes.append(call["callId"])
        except Exception:
            with lock:
                failures.append(str(idx))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker, idx) for idx in range(8)]
        for future in as_completed(futures):
            future.result()

    assert len(successes) == 4
    assert len(failures) == 4
    final_run = repo.require_run("concurrent-budget")
    assert final_run["budget"]["modelCalls"] == 4


def test_clear_removes_all_rows(repo: DeepResearchRepository):
    repo.create_run({"runId": "clear-test"})
    repo.clear()
    assert repo.list_runs() == []
    assert repo.list_calls("clear-test") == []


def test_cancelled_or_stale_epoch_cannot_publish(repo: DeepResearchRepository):
    repo.create_run({"runId": "publish-epoch"})
    first = repo.begin_execution("publish-epoch")
    repo.transition("publish-epoch", STATUS_PAUSED)
    repo.begin_execution("publish-epoch")
    with pytest.raises(EpochConflictError):
        repo.publish_report(run_id="publish-epoch", dedup_key="stale-pub", payload={"body": "old"},
                            expected_epoch=first["executionEpoch"])
    assert not repo.list_outbox("publish-epoch")
    repo.transition("publish-epoch", STATUS_CANCELLED)
    with pytest.raises(CallOutsideRunningError):
        repo.publish_report(run_id="publish-epoch", dedup_key="cancel-pub", payload={"body": "old"})
    assert repo.require_run("publish-epoch")["status"] == STATUS_CANCELLED


def test_generic_update_cannot_reassign_identity_or_reopen_terminal(repo: DeepResearchRepository):
    repo.create_run({"runId": "immutable", "taskId": "owner"})
    for field, value in [("taskId", "foreign"), ("engineVersion", "legacy-v1"), ("executionEpoch", 99)]:
        with pytest.raises(ValueError):
            repo.update_run("immutable", lambda r: {**r, field: value})
    repo.transition("immutable", STATUS_CANCELLED)
    with pytest.raises(IllegalStatusTransitionError):
        repo.update_run("immutable", lambda r: {**r, "status": STATUS_RUNNING})
    assert repo.require_run("immutable")["taskId"] == "owner"


def test_reservation_rejects_negative_cost_and_expired_deadline(repo: DeepResearchRepository):
    from services.deep_research.contracts import BudgetExhaustedError
    repo.create_run({"runId": "deadline"})
    repo.begin_execution("deadline")
    args = dict(run_id="deadline", node="plan", tool="model", args_digest="unique")
    with pytest.raises(ValueError):
        repo.reserve_call(**args, budget_delta={"tokens": -100})
    repo.update_run("deadline", lambda r: {**r, "startedAt": "2020-01-01T00:00:00+00:00"})
    with pytest.raises(BudgetExhaustedError):
        repo.reserve_call(**args)
    assert not repo.list_calls("deadline")


def test_action_receipt_is_durable_and_payload_bound(repo: DeepResearchRepository):
    repo.create_run({"runId": "action-run"})
    receipt, first = repo.claim_action("action-run", "request", "pause-payload")
    assert first and receipt["status"] == "pending"
    restarted = DeepResearchRepository(repo.db_path)
    assert restarted.claim_action("action-run", "request", "pause-payload") == (receipt, False)
    with pytest.raises(IdempotencyConflictError):
        restarted.claim_action("action-run", "request", "cancel-payload")
    result = {"runId": "action-run", "status": "paused"}
    restarted.finish_action("action-run", "request", result)
    assert restarted.claim_action("action-run", "request", "pause-payload")[0]["result"] == result


@pytest.mark.parametrize("limit", ["maxModelCalls", "maxTokens", "maxWallClockSeconds"])
@pytest.mark.parametrize("value", [0, -1])
def test_nonpositive_budget_does_not_disable_limits(repo: DeepResearchRepository, limit, value):
    with pytest.raises(ValueError):
        repo.create_run({"runId": "bad-budget", "budget": {limit: value}})


def test_finalization_fallback_records_actual_pool_and_settles_once(repo):
    repo.create_run({'runId': 'finish-spare', 'budget': {'maxModelCalls': 4, 'reserveModelCalls': 1}})
    repo.begin_execution('finish-spare')
    repo.reserve_call(run_id='finish-spare', node='synthesize', tool='llm_invoke',
        args_digest=digest('synth'), budget_delta={'modelCalls': 1, 'tokens': 100}, use_reserve=True)
    args = dict(run_id='finish-spare', node='verify_answer_coverage', tool='llm_invoke',
                args_digest=digest('coverage'), budget_delta={'modelCalls': 1, 'tokens': 200}, use_reserve=True)
    call, reused = repo.reserve_call(**args)
    assert not reused and call['usesReserve'] is False
    repo.complete_call(call['callId'], status=CALL_STATUS_SUCCEEDED, result={'ok': True},
                       budget_delta={'tokens': -150})
    before = repo.require_run('finish-spare')['budget']
    assert before['modelCalls'] == 1 and before['reservedModelCalls'] == 1
    assert before['normalTokens'] == 50 and before['tokens'] == 150
    repeated, reused = repo.reserve_call(**args)
    assert reused and repeated['callId'] == call['callId'] and repeated['usesReserve'] is False
    assert repo.require_run('finish-spare')['budget'] == before


def test_concurrent_finalization_cannot_overspend_spare_normal_capacity(repo):
    from services.deep_research.contracts import BudgetExhaustedError
    repo.create_run({'runId': 'finish-race', 'budget': {'maxModelCalls': 4, 'reserveModelCalls': 1}})
    repo.begin_execution('finish-race')
    repo.reserve_call(run_id='finish-race', node='synthesize', tool='llm_invoke',
        args_digest=digest('synth'), budget_delta={'modelCalls': 1}, use_reserve=True)
    def worker(i):
        try:
            call, _ = repo.reserve_call(run_id='finish-race', node='verify', tool='llm_invoke',
                args_digest=digest(i), budget_delta={'modelCalls': 1}, use_reserve=True)
            assert call['usesReserve'] is False
            return True
        except BudgetExhaustedError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(worker, range(8)))
    assert sum(results) == 3
    budget = repo.require_run('finish-race')['budget']
    assert budget['modelCalls'] == 3 and budget['reservedModelCalls'] == 1
    assert budget['maxModelCalls'] == 4 and budget['reserveModelCalls'] == 1


def test_finalization_fallback_does_not_bypass_unknown_or_paused_guards(repo):
    from services.deep_research.contracts import UnresolvedUnknownError
    repo.create_run({'runId': 'finish-guard', 'budget': {'maxModelCalls': 4, 'reserveModelCalls': 1}})
    repo.begin_execution('finish-guard')
    call, _ = repo.reserve_call(run_id='finish-guard', node='synthesize', tool='llm_invoke',
        args_digest=digest('synth'), budget_delta={'modelCalls': 1}, use_reserve=True)
    repo.complete_call(call['callId'], status=CALL_STATUS_UNKNOWN, error={'reason': 'unknown'})
    args = dict(run_id='finish-guard', node='verify', tool='llm_invoke', args_digest=digest('next'),
                budget_delta={'modelCalls': 1}, use_reserve=True)
    with pytest.raises(UnresolvedUnknownError):
        repo.reserve_call(**args)
    repo.update_run('finish-guard', lambda r: {**r, 'status': 'paused'})
    with pytest.raises(CallOutsideRunningError):
        repo.reserve_call(**args)
    assert repo.require_run('finish-guard')['budget']['modelCalls'] == 0
