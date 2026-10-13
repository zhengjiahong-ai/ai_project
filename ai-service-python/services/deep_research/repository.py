"""SQLite-backed durable store for Deep Research runs (v2).

All authoritative counters (budget reservations, call tokens, time origin) live
inside SQLite transactions.  In-memory state is never authoritative.  Unknown
call statuses retain their reserved budget and block automatic reissue.  Terminal
runs cannot resume.  Report + outbox commits are atomic under revision+epoch guard.
Reserve model calls are isolated from normal usage and only consumable via explicit
settlement.  Recovery pauses interrupted nonterminal runs instead of failing them.
"""
from __future__ import annotations

import json
import copy
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, UTC, timedelta
from typing import Any, Callable, Iterable

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
    DuplicateDispatchError,
    ENGINE_VERSION,
    EpochConflictError,
    ERROR_INTERRUPTED,
    IdempotencyConflictError,
    IllegalStatusTransitionError,
    LateCompletionError,
    OUTCOME_NONE,
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
    UnresolvedUnknownError,
    check_budget_limits,
    digest,
    merge_budget_counters,
    new_publication_id,
    normalize_run,
    resolve_budget_profile,
    transition_status,
    utc_now_iso,
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS deep_research_runs_v2 (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL DEFAULT '',
  workspace_id TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT NOT NULL DEFAULT '',
  engine TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  run_revision INTEGER NOT NULL DEFAULT 0,
  execution_epoch INTEGER NOT NULL DEFAULT 0,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS deep_research_runs_idem_v2
  ON deep_research_runs_v2 (workspace_id, idempotency_key)
  WHERE idempotency_key <> '';
CREATE INDEX IF NOT EXISTS deep_research_runs_status_v2
  ON deep_research_runs_v2 (status);
CREATE INDEX IF NOT EXISTS deep_research_runs_task_v2
  ON deep_research_runs_v2 (task_id);

CREATE TABLE IF NOT EXISTS deep_research_calls_v2 (
  call_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  node TEXT NOT NULL,
  tool TEXT NOT NULL,
  args_digest TEXT NOT NULL,
  status TEXT NOT NULL,
  result TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  attempt INTEGER NOT NULL DEFAULT 1,
  reservation_token TEXT NOT NULL DEFAULT '',
  reserved_at TEXT NOT NULL DEFAULT '',
  completed_at TEXT NOT NULL DEFAULT '',
  uses_reserve INTEGER NOT NULL DEFAULT 0,
  execution_epoch INTEGER NOT NULL DEFAULT 0,
  reserved_tokens INTEGER NOT NULL DEFAULT 0,
  settled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS deep_research_calls_dedup_v2
  ON deep_research_calls_v2 (run_id, node, tool, args_digest);
CREATE INDEX IF NOT EXISTS deep_research_calls_run_v2
  ON deep_research_calls_v2 (run_id);

CREATE TABLE IF NOT EXISTS deep_research_outbox_v2 (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  published INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS deep_research_outbox_run_v2
  ON deep_research_outbox_v2 (run_id, seq);

CREATE TABLE IF NOT EXISTS deep_research_actions_v2 (
  run_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  result TEXT,
  PRIMARY KEY(run_id, request_id)
);

CREATE TABLE IF NOT EXISTS deep_research_publications_v2 (
  publication_id TEXT PRIMARY KEY,
  dedup_key TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def _safe_rollback(conn: sqlite3.Connection) -> None:
    """Rollback only when a transaction is active.

    Prevents ``OperationalError`` from double-rollback when domain exceptions
    explicitly rollback before raising and the outer except clause would
    otherwise issue a second rollback.
    """
    if conn.in_transaction:
        conn.execute("ROLLBACK")


def _clamp_budget_to_profile(budget: dict[str, Any], profile_name: str) -> dict[str, Any]:
    """Ensure client-supplied budget overrides never widen the server profile."""
    _, limits = resolve_budget_profile(profile_name)
    clamped = dict(budget)
    limit_map = {
        "maxModelCalls": "maxModelCalls",
        "maxTokens": "maxTokens",
        "maxWallClockSeconds": "maxWallClockSeconds",
        "reserveModelCalls": "reserveModelCalls",
        "reserveTokens": "reserveTokens",
        "maxExternalSearches": "maxExternalSearches",
        "maxFulltextFetches": "maxFulltextFetches",
    }
    for key, limit_key in limit_map.items():
        if limit_key in limits:
            server_max = int(limits[limit_key])
            try:
                client_val = int(clamped.get(key, server_max))
            except (TypeError, ValueError):
                client_val = server_max
            if client_val < 0 or (client_val == 0 and key not in {"reserveModelCalls", "reserveTokens"}):
                raise ValueError("Budget limits must be positive")
            clamped[key] = min(client_val, server_max)
    clamped['reserveTokens'] = min(clamped['reserveTokens'], clamped['maxTokens'] // 2)
    return clamped


class DeepResearchRepository:
    """Durable repository with optimistic revision+epoch concurrency."""

    def __init__(self, db_path: str):
        if not db_path or db_path == ":memory:":
            raise ValueError("DeepResearchRepository requires a file-backed SQLite path")
        self.db_path = db_path
        self._write_lock = threading.Lock()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()

    # ── runs ──────────────────────────────────────────────────────────────────

    def create_run(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Idempotent run creation.

        Returns ``(record, created)`` where ``created`` is False when an existing
        record matched by idempotency key or run id was returned.  Raises
        :class:`IdempotencyConflictError` when the same idempotency key is reused
        with a different request digest.
        """
        record = normalize_run(payload)
        # Clamp budget to server profile limits
        profile_name = str(record.get("budget", {}).get("profile") or "standard")
        record["budget"] = _clamp_budget_to_profile(record["budget"], profile_name)
        run_id = record["runId"]
        workspace_id = str(record.get("workspaceId") or "")
        idem_key = str(record.get("idempotencyKey") or "")
        request_digest = str(record.get("requestDigest") or "")
        now = utc_now_iso()
        record.setdefault("createdAt", now)
        record.setdefault("updatedAt", now)
        serialized = json.dumps(record, ensure_ascii=False)
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                if idem_key:
                    row = conn.execute(
                        "SELECT payload FROM deep_research_runs_v2 WHERE workspace_id=? AND idempotency_key=?",
                        (workspace_id, idem_key),
                    ).fetchone()
                    if row is not None:
                        existing = json.loads(row[0])
                        if request_digest and str(existing.get("requestDigest") or "") != request_digest:
                            _safe_rollback(conn)
                            raise IdempotencyConflictError(workspace_id, idem_key)
                        conn.execute("COMMIT")
                        return existing, False
                row = conn.execute(
                    "SELECT payload FROM deep_research_runs_v2 WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is not None:
                    conn.execute("COMMIT")
                    return json.loads(row[0]), False
                conn.execute(
                    """
                    INSERT INTO deep_research_runs_v2
                      (run_id, task_id, workspace_id, idempotency_key, engine, status, outcome, error_code,
                       run_revision, execution_epoch, payload, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        str(record.get("taskId") or ""),
                        workspace_id,
                        idem_key,
                        str(record.get("engine") or ""),
                        str(record.get("status") or STATUS_QUEUED),
                        str(record.get("outcome") or OUTCOME_NONE),
                        str(record.get("errorCode") or ""),
                        int(record.get("runRevision") or 0),
                        int(record.get("executionEpoch") or 0),
                        serialized,
                        str(record.get("createdAt") or now),
                        str(record.get("updatedAt") or now),
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                _safe_rollback(conn)
                raise
        return record, True

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        normalized = str(run_id or "").strip()
        if not normalized:
            return None
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            row = conn.execute(
                "SELECT payload FROM deep_research_runs_v2 WHERE run_id=?", (normalized,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def require_run(self, run_id: str) -> dict[str, Any]:
        record = self.get_run(run_id)
        if record is None:
            raise RunNotFoundError(str(run_id))
        return record

    def list_runs(
        self,
        *,
        workspace_id: str | None = None,
        statuses: Iterable[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if workspace_id is not None:
            clauses.append("workspace_id=?")
            params.append(str(workspace_id))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT payload FROM deep_research_runs_v2 {where} ORDER BY rowid DESC LIMIT ?"
        params.append(int(limit))
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def update_run(
        self,
        run_id: str,
        mutate: Callable[[dict[str, Any]], dict[str, Any] | None],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Optimistic update guarded by runRevision.

        ``mutate`` receives a copy of the current record and must return the
        updated record (or ``None`` to keep it unchanged).  It MUST NOT call back
        into this repository because the write lock is held for the duration.
        """
        normalized = str(run_id or "").strip()
        if not normalized:
            raise RunNotFoundError(run_id)
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT payload FROM deep_research_runs_v2 WHERE run_id=?", (normalized,)
                ).fetchone()
                if row is None:
                    _safe_rollback(conn)
                    raise RunNotFoundError(normalized)
                current = json.loads(row[0])
                if expected_revision is not None and int(current.get("runRevision") or 0) != int(expected_revision):
                    _safe_rollback(conn)
                    raise RevisionConflictError(
                        normalized, int(expected_revision), int(current.get("runRevision") or 0)
                    )
                updated = mutate(copy.deepcopy(current))
                if updated is None:
                    updated = current
                for identity in ("runId", "taskId", "engineVersion", "contractVersion", "materialSnapshot"):
                    if updated.get(identity) != current.get(identity):
                        raise ValueError(f"Immutable run field changed: {identity}")
                if updated.get("executionEpoch") != current.get("executionEpoch"):
                    raise ValueError("Execution epoch changes require begin_execution")
                if updated.get("status") != current.get("status"):
                    transition_status(current, str(updated.get("status")))
                updated["runRevision"] = int(current.get("runRevision") or 0) + 1
                updated["updatedAt"] = utc_now_iso()
                serialized = json.dumps(updated, ensure_ascii=False)
                conn.execute(
                    """
                    UPDATE deep_research_runs_v2
                    SET status=?, outcome=?, error_code=?, run_revision=?, payload=?, updated_at=?
                    WHERE run_id=?
                    """,
                    (
                        str(updated.get("status") or ""),
                        str(updated.get("outcome") or OUTCOME_NONE),
                        str(updated.get("errorCode") or ""),
                        int(updated["runRevision"]),
                        serialized,
                        str(updated["updatedAt"]),
                        normalized,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                _safe_rollback(conn)
                raise
        return updated

    def transition(
        self,
        run_id: str,
        next_status: str,
        *,
        expected_revision: int | None = None,
        mutate: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        """Validate and apply a status transition atomically."""

        def _apply(record: dict[str, Any]) -> dict[str, Any]:
            validated = transition_status(record, next_status)
            if mutate is not None:
                mutated = mutate(validated)
                if mutated is not None:
                    validated = mutated
            return validated

        return self.update_run(run_id, _apply, expected_revision=expected_revision)

    def begin_execution(self, run_id: str, *, expected_epoch: int | None = None,
                        expected_revision: int | None = None) -> dict[str, Any]:
        """Atomically mark a run as running and increment its executionEpoch.

        Rejects duplicate pending dispatch (already running), terminal runs,
        and runs with unresolved unknown calls.  Resets ``startedAt`` only on
        the first execution so wall-clock deadlines do not restart on re-entry.
        """
        normalized = str(run_id or "").strip()
        if not normalized:
            raise RunNotFoundError(run_id)
        now = utc_now_iso()
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT payload FROM deep_research_runs_v2 WHERE run_id=?", (normalized,)
                ).fetchone()
                if row is None:
                    _safe_rollback(conn)
                    raise RunNotFoundError(normalized)
                record = json.loads(row[0])
                if expected_revision is not None and record.get("runRevision") != expected_revision:
                    raise RevisionConflictError(normalized, expected_revision, record.get("runRevision", 0))
                current_epoch = int(record.get("executionEpoch") or 0)
                if expected_epoch is not None and current_epoch != int(expected_epoch):
                    _safe_rollback(conn)
                    raise EpochConflictError(normalized, int(expected_epoch), current_epoch)
                if record.get("status") in TERMINAL_STATUSES:
                    _safe_rollback(conn)
                    from services.deep_research.contracts import TerminalGuardError

                    raise TerminalGuardError(normalized, str(record.get("status")))
                if record.get("status") == STATUS_RUNNING:
                    _safe_rollback(conn)
                    raise DuplicateDispatchError(normalized)
                allowed = {STATUS_QUEUED, STATUS_PAUSED, STATUS_WAITING_USER}
                if record.get("status") not in allowed:
                    _safe_rollback(conn)
                    raise IllegalStatusTransitionError(str(record.get("status")), STATUS_RUNNING)
                # Reject runs with unresolved unknown calls
                unknown_rows = conn.execute(
                    "SELECT call_id FROM deep_research_calls_v2 WHERE run_id=? AND status=?",
                    (normalized, CALL_STATUS_UNKNOWN),
                ).fetchall()
                if unknown_rows:
                    _safe_rollback(conn)
                    raise UnresolvedUnknownError(
                        normalized, [r[0] for r in unknown_rows]
                    )
                waiting_since = record.get("state", {}).get("waitingSince") if record["status"] == STATUS_WAITING_USER else None
                if waiting_since and record.get("startedAt"):
                    # Human response time is not active research time. Apply once under the run lock.
                    end = datetime.fromisoformat(now.replace("Z", "+00:00"))
                    begin = datetime.fromisoformat(waiting_since.replace("Z", "+00:00"))
                    duration = max(end - begin, timedelta(0))
                    start = datetime.fromisoformat(record["startedAt"].replace("Z", "+00:00"))
                    record["firstStartedAt"] = record.get("firstStartedAt") or record["startedAt"]
                    record["startedAt"] = (start + duration).isoformat()
                    record["state"]["waitingSince"] = None
                    record["budget"]["waitingSeconds"] = record["budget"].get("waitingSeconds", 0) + duration.total_seconds()
                record["status"] = STATUS_RUNNING
                record["executionEpoch"] = current_epoch + 1
                # Only set startedAt on first execution (epoch 0 → 1)
                if current_epoch == 0:
                    record["startedAt"] = now
                record["updatedAt"] = now
                record["runRevision"] = int(record.get("runRevision") or 0) + 1
                serialized = json.dumps(record, ensure_ascii=False)
                conn.execute(
                    """
                    UPDATE deep_research_runs_v2
                    SET status=?, run_revision=?, execution_epoch=?, payload=?, updated_at=?
                    WHERE run_id=?
                    """,
                    (
                        STATUS_RUNNING,
                        int(record["runRevision"]),
                        int(record["executionEpoch"]),
                        serialized,
                        now,
                        normalized,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                _safe_rollback(conn)
                raise
        return record

    # ── calls ─────────────────────────────────────────────────────────────────

    def reserve_call(
        self,
        *,
        run_id: str,
        node: str,
        tool: str,
        args_digest: str,
        reservation_token: str | None = None,
        budget_delta: dict[str, Any] | None = None,
        use_reserve: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Reserve a durable tool call and account for its budget cost.

        Returns ``(call_record, reused)`` where ``reused`` is True when an
        existing succeeded call was found.  Only succeeded calls are reused;
        failed/paused/unknown calls are NOT automatically re-reserved.  Unknown
        calls retain their reserved budget and block automatic reissue.  Calls
        are rejected unless the run is currently running.  Normal calls cannot
        consume reserve; only explicit ``use_reserve=True`` may draw from the
        reserve pool.

        Per-call ``reservedTokens`` is persisted from the budget delta so
        settlement can be bounded against the original reservation.
        """
        normalized_run = str(run_id or "").strip()
        normalized_node = str(node or "").strip()
        normalized_tool = str(tool or "").strip()
        normalized_digest = str(args_digest or "").strip()
        if not normalized_run or not normalized_node or not normalized_tool or not normalized_digest:
            raise ValueError("reserve_call requires run_id, node, tool and args_digest")
        token = str(
            reservation_token
            or digest(
                {
                    "run": normalized_run,
                    "node": normalized_node,
                    "tool": normalized_tool,
                    "digest": normalized_digest,
                }
            )
        )
        delta = dict(budget_delta or {})
        for value in delta.values():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("Reservation costs must be nonnegative integers")
        now = utc_now_iso()
        call_id = _build_call_id(normalized_run, normalized_node, normalized_tool, normalized_digest)
        # Compute reserved_tokens from delta for persistence
        reserved_tokens = 0
        if "tokens" in delta:
            try:
                reserved_tokens = max(0, int(delta["tokens"]))
            except (TypeError, ValueError):
                reserved_tokens = 0
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                run_row = conn.execute(
                    "SELECT payload FROM deep_research_runs_v2 WHERE run_id=?", (normalized_run,)
                ).fetchone()
                if run_row is None:
                    _safe_rollback(conn)
                    raise RunNotFoundError(normalized_run)
                run_record = json.loads(run_row[0])
                if run_record.get("status") != STATUS_RUNNING:
                    _safe_rollback(conn)
                    raise CallOutsideRunningError(normalized_run, str(run_record.get("status")))
                started = run_record.get("startedAt")
                if started:
                    elapsed = (datetime.now(UTC) - datetime.fromisoformat(started)).total_seconds()
                    if elapsed > int(run_record["budget"]["maxWallClockSeconds"]):
                        from services.deep_research.contracts import BudgetExhaustedError
                        raise BudgetExhaustedError("elapsedSeconds", int(run_record["budget"]["maxWallClockSeconds"]), int(elapsed))
                current_epoch = int(run_record.get("executionEpoch") or 0)
                row = conn.execute(
                    "SELECT * FROM deep_research_calls_v2 WHERE call_id=?", (call_id,)
                ).fetchone()
                if row is None:
                    unresolved = conn.execute("SELECT call_id FROM deep_research_calls_v2 WHERE run_id=? AND status='unknown'",
                                              (normalized_run,)).fetchall()
                    if unresolved:
                        from services.deep_research.contracts import UnresolvedUnknownError
                        raise UnresolvedUnknownError(normalized_run, [row[0] for row in unresolved])
                    if delta:
                        from services.deep_research.finalization_pool import select_reservation_pool
                        # Select against current counters under the same write
                        # transaction. Full budget checks below still admit or
                        # reject; the ledger records the actual pool used.
                        use_reserve = select_reservation_pool(run_record.get('budget') or {},
                                                              delta, use_reserve, normalized_node)
                        run_record["budget"] = _apply_reservation(
                            run_record.get("budget") or {}, delta, use_reserve=use_reserve
                        )
                        from services.deep_research.contracts import check_exploration_headroom
                        exhausted = check_budget_limits(run_record["budget"])
                        if not exhausted and not use_reserve and int(delta.get('modelCalls') or 0) > 0:
                            headroom = check_exploration_headroom(run_record["budget"], normalized_node)
                            if headroom:
                                from services.deep_research.contracts import BudgetExhaustedError
                                raise BudgetExhaustedError(*headroom)
                        if exhausted:
                            _safe_rollback(conn)
                            from services.deep_research.contracts import BudgetExhaustedError

                            raise BudgetExhaustedError(
                                exhausted,
                                (int(run_record['budget']['maxTokens']) - int(run_record['budget'].get('reserveTokens') or 0))
                                if exhausted == 'normalTokens' else int(run_record["budget"].get(f"max{exhausted[0].upper()}{exhausted[1:]}", 0)),
                                int(run_record["budget"].get(exhausted) or 0),
                            )
                        run_record["runRevision"] = int(run_record.get("runRevision") or 0) + 1
                        run_record["updatedAt"] = now
                        conn.execute(
                            """
                            UPDATE deep_research_runs_v2
                            SET run_revision=?, payload=?, updated_at=?
                            WHERE run_id=?
                            """,
                            (int(run_record["runRevision"]), json.dumps(run_record, ensure_ascii=False), now, normalized_run),
                        )
                    conn.execute(
                        """
                        INSERT INTO deep_research_calls_v2
                          (call_id, run_id, node, tool, args_digest, status, attempt, reservation_token,
                           reserved_at, created_at, updated_at, uses_reserve, execution_epoch, reserved_tokens, settled)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            call_id,
                            normalized_run,
                            normalized_node,
                            normalized_tool,
                            normalized_digest,
                            CALL_STATUS_PENDING,
                            1,
                            token,
                            now,
                            now,
                            now,
                            1 if use_reserve else 0,
                            current_epoch,
                            reserved_tokens,
                            0,
                        ),
                    )
                    conn.execute("COMMIT")
                    record = _row_to_call(conn, call_id)
                    return record, False
                record = _row_to_call_from_row(row)
                if record["status"] == CALL_STATUS_SUCCEEDED:
                    conn.execute("COMMIT")
                    return record, True
                if record["status"] == CALL_STATUS_UNKNOWN:
                    _safe_rollback(conn)
                    from services.deep_research.contracts import UnknownCallError

                    raise UnknownCallError(call_id)
                # Failed and paused calls are NOT automatically re-reserved.
                # They require explicit user resolution or a new call identity.
                if record["status"] in {CALL_STATUS_FAILED, CALL_STATUS_PAUSED}:
                    _safe_rollback(conn)
                    raise IllegalStatusTransitionError(
                        record["status"],
                        CALL_STATUS_PENDING,
                    )
                # Should not reach here, but guard defensively
                _safe_rollback(conn)
                raise ValueError(f"Unexpected call status for re-reservation: {record['status']!r}")
            except Exception:
                _safe_rollback(conn)
                raise

    def complete_call(
        self,
        call_id: str,
        *,
        status: str,
        result: Any | None = None,
        error: Any | None = None,
        reservation_token: str | None = None,
        budget_delta: dict[str, Any] | None = None,
        allow_late: bool = False,
    ) -> dict[str, Any]:
        """Finalize a reserved call.

        Compares the call's persisted ``executionEpoch`` against the run's
        current epoch; mismatches raise :class:`EpochConflictError` to protect
        against stale completions from prior epochs.

        Late completions against non-running runs raise
        :class:`LateCompletionError` unless ``allow_late`` is True.  When
        ``allow_late`` is True the completion is recorded for audit only:
        authoritative run state (budget counters, outcome, status) is NOT
        modified.

        Budget deltas settle actual usage atomically with the completion
        (only when not late-audit).  Settlement is bounded against the
        per-call ``reservedTokens`` and can only occur once per call.
        """
        normalized = str(call_id or "").strip()
        if not normalized:
            raise ValueError("complete_call requires call_id")
        if status not in {CALL_STATUS_SUCCEEDED, CALL_STATUS_FAILED, CALL_STATUS_PAUSED, CALL_STATUS_UNKNOWN}:
            raise ValueError(f"Invalid call status: {status!r}")
        now = utc_now_iso()
        serialized_result = json.dumps(result, ensure_ascii=False) if result is not None else ""
        serialized_error = json.dumps(error, ensure_ascii=False) if error is not None else ""
        delta = dict(budget_delta or {})
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM deep_research_calls_v2 WHERE call_id=?", (normalized,)
                ).fetchone()
                if row is None:
                    _safe_rollback(conn)
                    raise RunNotFoundError(f"call:{normalized}")
                record = _row_to_call_from_row(row)
                if reservation_token and record.get("reservationToken") != reservation_token:
                    _safe_rollback(conn)
                    raise EpochConflictError(
                        normalized, int(reservation_token or 0), int(record.get("reservationToken") or 0)
                    )
                # Settlement guard: reject if already settled and delta provided
                if record.get("settled") or record.get("status") in {CALL_STATUS_SUCCEEDED, CALL_STATUS_FAILED}:
                    _safe_rollback(conn)
                    raise SettlementAlreadyError(normalized)
                run_row = conn.execute(
                    "SELECT payload FROM deep_research_runs_v2 WHERE run_id=?", (record["runId"],)
                ).fetchone()
                if run_row is not None:
                    run_record = json.loads(run_row[0])
                    run_status = str(run_record.get("status") or "")
                    current_epoch = int(run_record.get("executionEpoch") or 0)
                    call_epoch = int(record.get("executionEpoch") or 0)
                    # Epoch protection: reject stale completions from prior epochs
                    if call_epoch != current_epoch and not allow_late:
                        _safe_rollback(conn)
                        raise EpochConflictError(normalized, current_epoch, call_epoch)
                    if run_status != STATUS_RUNNING and not allow_late:
                        _safe_rollback(conn)
                        raise LateCompletionError(normalized, run_status)
                    # allow_late: audit-only, do NOT touch run budget or state
                    if not allow_late and delta:
                        # Bound settlement against reserved tokens
                        bounded_delta = _bound_settlement(delta, record)
                        run_record["budget"] = merge_budget_counters(run_record.get("budget") or {}, bounded_delta)
                        run_record["runRevision"] = int(run_record.get("runRevision") or 0) + 1
                        run_record["updatedAt"] = now
                        conn.execute(
                            """
                            UPDATE deep_research_runs_v2
                            SET run_revision=?, payload=?, updated_at=?
                            WHERE run_id=?
                            """,
                            (int(run_record["runRevision"]), json.dumps(run_record, ensure_ascii=False), now, record["runId"]),
                        )
                # Mark settled when applying budget delta (not late-audit)
                new_settled = 1 if (status in {CALL_STATUS_SUCCEEDED, CALL_STATUS_FAILED} and not allow_late) else int(record.get("settled") or 0)
                conn.execute(
                    """
                    UPDATE deep_research_calls_v2
                    SET status=?, result=?, error=?, completed_at=?, updated_at=?, settled=?
                    WHERE call_id=?
                    """,
                    (status, serialized_result, serialized_error, now, now, new_settled, normalized),
                )
                conn.execute("COMMIT")
            except Exception:
                _safe_rollback(conn)
                raise
        record["status"] = status
        record["result"] = result
        record["error"] = error
        record["completedAt"] = now
        record["updatedAt"] = now
        record["settled"] = bool(new_settled)
        return record

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        normalized = str(call_id or "").strip()
        if not normalized:
            return None
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            row = conn.execute(
                "SELECT * FROM deep_research_calls_v2 WHERE call_id=?", (normalized,)
            ).fetchone()
        return _row_to_call_from_row(row) if row else None

    def list_calls(self, run_id: str) -> list[dict[str, Any]]:
        normalized = str(run_id or "").strip()
        if not normalized:
            return []
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            rows = conn.execute(
                "SELECT * FROM deep_research_calls_v2 WHERE run_id=? ORDER BY rowid ASC",
                (normalized,),
            ).fetchall()
        return [_row_to_call_from_row(row) for row in rows]

    # ── recovery ──────────────────────────────────────────────────────────────

    def recover(self, *, reason: str = "interrupted") -> list[str]:
        """Recover interrupted runs safely.

        - **queued** runs that were never dispatched stay queued (safe checkpoint).
        - **running** runs are paused so they can resume after restart.
        - **stopping** runs are cancelled (graceful shutdown intent preserved).
        - Pending calls become ``unknown`` and retain their reserved budget
          so they block automatic reissue until resolved.

        Returns the list of affected run ids.
        """
        affected: list[str] = []
        now = utc_now_iso()
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Running → paused
                running_rows = conn.execute(
                    "SELECT run_id, payload FROM deep_research_runs_v2 WHERE status=?",
                    (STATUS_RUNNING,),
                ).fetchall()
                for run_id, raw in running_rows:
                    record = json.loads(raw)
                    record["status"] = STATUS_PAUSED
                    record["pause"] = {
                        "requested": True,
                        "node": "",
                        "reason": reason,
                        "payload": None,
                        "requestedAt": now,
                    }
                    record["updatedAt"] = now
                    record["runRevision"] = int(record.get("runRevision") or 0) + 1
                    serialized = json.dumps(record, ensure_ascii=False)
                    conn.execute(
                        """
                        UPDATE deep_research_runs_v2
                        SET status=?, run_revision=?, payload=?, updated_at=?
                        WHERE run_id=?
                        """,
                        (STATUS_PAUSED, int(record["runRevision"]), serialized, now, run_id),
                    )
                    affected.append(run_id)

                # Stopping → cancelled
                stopping_rows = conn.execute(
                    "SELECT run_id, payload FROM deep_research_runs_v2 WHERE status=?",
                    (STATUS_STOPPING,),
                ).fetchall()
                for run_id, raw in stopping_rows:
                    record = json.loads(raw)
                    record["status"] = STATUS_CANCELLED
                    record["cancellation"] = {
                        "requested": True,
                        "requestedAt": now,
                        "reason": reason,
                    }
                    record["finishedAt"] = now
                    record["updatedAt"] = now
                    record["runRevision"] = int(record.get("runRevision") or 0) + 1
                    serialized = json.dumps(record, ensure_ascii=False)
                    conn.execute(
                        """
                        UPDATE deep_research_runs_v2
                        SET status=?, run_revision=?, payload=?, updated_at=?
                        WHERE run_id=?
                        """,
                        (STATUS_CANCELLED, int(record["runRevision"]), serialized, now, run_id),
                    )
                    affected.append(run_id)

                # Queued runs stay queued — they were never dispatched so
                # there is no in-flight work to recover.  We still list them
                # as affected so callers know they were inspected.
                queued_rows = conn.execute(
                    "SELECT run_id FROM deep_research_runs_v2 WHERE status=?",
                    (STATUS_QUEUED,),
                ).fetchall()
                for (run_id,) in queued_rows:
                    affected.append(run_id)

                # Pending calls → unknown (retain reserved budget)
                conn.execute(
                    """
                    UPDATE deep_research_calls_v2
                    SET status=?, updated_at=?
                    WHERE status=?
                    """,
                    (CALL_STATUS_UNKNOWN, now, CALL_STATUS_PENDING),
                )
                conn.execute("COMMIT")
            except Exception:
                _safe_rollback(conn)
                raise
        return affected

    # ── publications & outbox ─────────────────────────────────────────────────

    def publish_report(
        self,
        *,
        run_id: str,
        dedup_key: str,
        payload: dict[str, Any],
        outcome: str | None = None,
        report_text: str = "",
        expected_revision: int | None = None,
        expected_epoch: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Persist a publication atomically with an outbox entry and run update.

        The outbox entry starts with ``published=0`` and must be explicitly
        acknowledged via :meth:`acknowledge_outbox`.  Duplicate dedup keys
        with the **same** run_id and payload return the existing record.
        Duplicate dedup keys with a **different** run_id or payload raise
        :class:`PublicationConflictError`.

        The run record is updated atomically in the same transaction:
        ``result``, ``outcome``, ``status=completed``, and ``finishedAt``
        are set under revision+epoch guard.
        """
        normalized_run = str(run_id or "").strip()
        normalized_key = str(dedup_key or "").strip()
        if not normalized_run or not normalized_key:
            raise ValueError("publish_report requires run_id and dedup_key")
        now = utc_now_iso()
        pub_id = new_publication_id()
        serialized_payload = json.dumps(payload, ensure_ascii=False)
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT publication_id, run_id, payload, created_at FROM deep_research_publications_v2 WHERE dedup_key=?",
                    (normalized_key,),
                ).fetchone()
                if existing is not None:
                    existing_run_id = existing[1]
                    existing_payload = existing[2]
                    # Same run + same payload → idempotent return
                    if existing_run_id == normalized_run and existing_payload == serialized_payload:
                        conn.execute("COMMIT")
                        return {
                            "publicationId": existing[0],
                            "dedupKey": normalized_key,
                            "runId": normalized_run,
                            "payload": json.loads(existing[2]),
                            "createdAt": existing[3],
                        }, False
                    # Different run or payload → conflict
                    _safe_rollback(conn)
                    raise PublicationConflictError(normalized_key)

                # Update run record atomically with publication
                run_row = conn.execute(
                    "SELECT payload FROM deep_research_runs_v2 WHERE run_id=?", (normalized_run,)
                ).fetchone()
                if run_row is None:
                    _safe_rollback(conn)
                    raise RunNotFoundError(normalized_run)
                run_record = json.loads(run_row[0])
                if run_record.get("status") != STATUS_RUNNING:
                    raise CallOutsideRunningError(normalized_run, str(run_record.get("status")))
                if expected_epoch is not None and int(run_record.get("executionEpoch") or 0) != expected_epoch:
                    raise EpochConflictError(normalized_run, expected_epoch, int(run_record.get("executionEpoch") or 0))
                if expected_revision is not None and int(run_record.get("runRevision") or 0) != int(expected_revision):
                    _safe_rollback(conn)
                    raise RevisionConflictError(
                        normalized_run, int(expected_revision), int(run_record.get("runRevision") or 0)
                    )
                run_record["result"] = payload
                run_record["state"] = {**run_record.get("state", {}),
                                       "reportVersionId": payload.get("reportVersionId", ""),
                                       "publicationId": pub_id}
                if outcome:
                    run_record["outcome"] = outcome
                if report_text:
                    run_record["report"] = report_text
                run_record["status"] = STATUS_COMPLETED
                run_record["finishedAt"] = now
                if run_record.get("startedAt"):
                    start = datetime.fromisoformat(run_record["startedAt"].replace("Z", "+00:00"))
                    elapsed = max(0, (datetime.now(UTC) - start).total_seconds())
                    run_record["budget"] = {**run_record.get("budget", {}), "elapsedSeconds": round(elapsed, 3)}
                run_record["publication"] = {
                    "published": False,
                    "publicationId": pub_id,
                    "dedupKey": normalized_key,
                    "publishedAt": now,
                    "reused": False,
                }
                run_record["runRevision"] = int(run_record.get("runRevision") or 0) + 1
                run_record["updatedAt"] = now
                serialized_run = json.dumps(run_record, ensure_ascii=False)
                conn.execute(
                    """
                    UPDATE deep_research_runs_v2
                    SET status=?, outcome=?, run_revision=?, payload=?, updated_at=?
                    WHERE run_id=?
                    """,
                    (
                        STATUS_COMPLETED,
                        str(run_record.get("outcome") or OUTCOME_NONE),
                        int(run_record["runRevision"]),
                        serialized_run,
                        now,
                        normalized_run,
                    ),
                )

                conn.execute(
                    """
                    INSERT INTO deep_research_publications_v2 (publication_id, dedup_key, run_id, payload, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (pub_id, normalized_key, normalized_run, serialized_payload, now),
                )
                # Outbox starts unpublished (published=0)
                conn.execute(
                    """
                    INSERT INTO deep_research_outbox_v2 (run_id, kind, payload, published, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (normalized_run, "publication", serialized_payload, 0, now),
                )
                conn.execute("COMMIT")
            except Exception:
                _safe_rollback(conn)
                raise
        return {
            "publicationId": pub_id,
            "dedupKey": normalized_key,
            "runId": normalized_run,
            "payload": payload,
            "createdAt": now,
        }, True

    def acknowledge_outbox(self, run_id: str, seq: int) -> dict[str, Any]:
        """Mark an outbox entry as published (acknowledged by downstream).

        Returns the updated outbox entry.  Raises :class:`RunNotFoundError`
        if the entry does not exist.
        """
        normalized_run = str(run_id or "").strip()
        if not normalized_run:
            raise ValueError("acknowledge_outbox requires run_id")
        now = utc_now_iso()
        with self._write_lock, closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT seq, run_id, kind, payload, published, created_at FROM deep_research_outbox_v2 WHERE run_id=? AND seq=?",
                    (normalized_run, int(seq)),
                ).fetchone()
                if row is None:
                    _safe_rollback(conn)
                    raise RunNotFoundError(f"outbox:{normalized_run}:{seq}")
                conn.execute(
                    "UPDATE deep_research_outbox_v2 SET published=1 WHERE run_id=? AND seq=?",
                    (normalized_run, int(seq)),
                )
                conn.execute("COMMIT")
            except Exception:
                _safe_rollback(conn)
                raise
        return {
            "seq": int(row[0]),
            "runId": row[1],
            "kind": row[2],
            "payload": json.loads(row[3]),
            "published": True,
            "createdAt": row[5],
        }

    def append_outbox(self, *, run_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_run = str(run_id or "").strip()
        normalized_kind = str(kind or "").strip()
        if not normalized_run or not normalized_kind:
            raise ValueError("append_outbox requires run_id and kind")
        now = utc_now_iso()
        serialized = json.dumps(payload, ensure_ascii=False)
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            cursor = conn.execute(
                """
                INSERT INTO deep_research_outbox_v2 (run_id, kind, payload, published, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_run, normalized_kind, serialized, 0, now),
            )
            conn.commit()
            seq = cursor.lastrowid
        return {
            "seq": int(seq or 0),
            "runId": normalized_run,
            "kind": normalized_kind,
            "payload": payload,
            "published": False,
            "createdAt": now,
        }

    def list_outbox(self, run_id: str, *, include_published: bool = False) -> list[dict[str, Any]]:
        normalized = str(run_id or "").strip()
        if not normalized:
            return []
        sql = "SELECT seq, run_id, kind, payload, published, created_at FROM deep_research_outbox_v2 WHERE run_id=?"
        params: list[Any] = [normalized]
        if not include_published:
            sql += " AND published=0"
        sql += " ORDER BY seq ASC"
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "seq": int(row[0]),
                "runId": row[1],
                "kind": row[2],
                "payload": json.loads(row[3]),
                "published": bool(row[4]),
                "createdAt": row[5],
            }
            for row in rows
        ]

    def pending_publications(self, limit: int = 20) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            rows = conn.execute("""SELECT o.seq, o.run_id, o.payload, r.payload
                FROM deep_research_outbox_v2 o JOIN deep_research_runs_v2 r ON r.run_id=o.run_id
                WHERE o.published=0 AND o.kind='publication' ORDER BY o.seq LIMIT ?""",
                (min(max(0, limit), 100),)).fetchall()
        return [{"seq": row[0], "runId": row[1], "payload": json.loads(row[2]),
                 "taskId": json.loads(row[3])["taskId"]} for row in rows]

    # ── maintenance ───────────────────────────────────────────────────────────

    def claim_action(self, run_id: str, request_id: str, fingerprint: str) -> tuple[dict, bool]:
        """Persist action intent before mutating a run or dispatching work.

        Pending intent on recovery is uncertain, never a license to reissue.
        Replay returns the stored receipt; a different payload cannot reuse it.
        """
        if not request_id or len(request_id) > 256 or not fingerprint:
            raise ValueError("Action requires bounded request identity")
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self_row = conn.execute("SELECT 1 FROM deep_research_runs_v2 WHERE run_id=?", (run_id,)).fetchone()
            if self_row is None:
                raise RunNotFoundError(run_id)
            row = conn.execute("SELECT fingerprint,status,result FROM deep_research_actions_v2 WHERE run_id=? AND request_id=?", (run_id, request_id)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise IdempotencyConflictError(run_id, request_id)
                return {"status": row[1], "result": json.loads(row[2]) if row[2] else None}, False
            conn.execute("INSERT INTO deep_research_actions_v2 VALUES (?,?,?,'pending',NULL)", (run_id, request_id, fingerprint))
            conn.commit()
            return {"status": "pending", "result": None}, True

    def finish_action(self, run_id: str, request_id: str, result: dict, *, status: str = "completed") -> dict:
        if status not in {"completed", "failed"}:
            raise ValueError("Invalid action receipt status")
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status,result FROM deep_research_actions_v2 WHERE run_id=? AND request_id=?", (run_id, request_id)).fetchone()
            if row is None:
                raise RunNotFoundError(f"action:{request_id}")
            if row[0] != "pending":
                return json.loads(row[1])
            conn.execute("UPDATE deep_research_actions_v2 SET status=?,result=? WHERE run_id=? AND request_id=?", (status, json.dumps(result, ensure_ascii=False), run_id, request_id))
            conn.commit()
            return result

    def clear(self) -> None:
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            conn.execute("DELETE FROM deep_research_actions_v2")
            conn.execute("DELETE FROM deep_research_runs_v2")
            conn.execute("DELETE FROM deep_research_calls_v2")
            conn.execute("DELETE FROM deep_research_outbox_v2")
            conn.execute("DELETE FROM deep_research_publications_v2")
            conn.commit()


# ── helpers ───────────────────────────────────────────────────────────────────


def _build_call_id(run_id: str, node: str, tool: str, args_digest: str) -> str:
    raw = f"{run_id}|{node}|{tool}|{args_digest}"
    return digest(raw)[:32]


def _apply_reservation(budget: dict[str, Any], delta: dict[str, Any], *, use_reserve: bool) -> dict[str, Any]:
    """Apply worst-case reservation accounting.

    Normal calls increment counters directly.  Reserve calls increment
    ``reservedModelCalls`` instead of ``modelCalls`` so the reserve pool stays
    isolated and additive to the main budget.  Tokens and elapsed seconds always
    count against the main budget regardless of reserve usage.
    """
    merged = dict(budget)
    for kind in BUDGET_COUNTER_KINDS:
        if kind == 'normalTokens':
            continue  # Derived only from the authoritative call's pool.
        if kind not in delta:
            continue
        try:
            increment = int(delta[kind])
        except (TypeError, ValueError):
            continue
        if increment <= 0:
            continue
        if kind == "modelCalls" and use_reserve:
            merged["reservedModelCalls"] = int(merged.get("reservedModelCalls") or 0) + increment
            continue
        base = int(merged.get(kind) or 0)
        merged[kind] = base + increment
        if kind == 'tokens' and not use_reserve:
            merged['normalTokens'] = int(merged.get('normalTokens') or 0) + increment
    return merged


def _bound_settlement(delta: dict[str, Any], call_record: dict[str, Any]) -> dict[str, Any]:
    """Bound settlement delta against the original reservation.

    Token refunds cannot exceed the per-call ``reservedTokens``.  This prevents
    over-refunding when actual usage was less than reserved.
    """
    bounded = dict(delta)
    bounded.pop('normalTokens', None)
    reserved_tokens = int(call_record.get("reservedTokens") or 0)
    if "tokens" in bounded and reserved_tokens > 0:
        try:
            token_delta = int(bounded["tokens"])
        except (TypeError, ValueError):
            token_delta = 0
        # Refunds (negative delta) bounded by reservation
        if token_delta < 0:
            bounded["tokens"] = max(token_delta, -reserved_tokens)
    if 'tokens' in bounded and not call_record.get('usesReserve'):
        bounded['normalTokens'] = bounded['tokens']
    return bounded


def _row_to_call(conn: sqlite3.Connection, call_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM deep_research_calls_v2 WHERE call_id=?", (call_id,)
    ).fetchone()
    if row is None:
        raise RunNotFoundError(f"call:{call_id}")
    return _row_to_call_from_row(row)


def _row_to_call_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    result_raw = row[6] if len(row) > 6 else ""
    error_raw = row[7] if len(row) > 7 else ""
    result_value = json.loads(result_raw) if result_raw else None
    error_value = json.loads(error_raw) if error_raw else None
    return {
        "callId": row[0],
        "runId": row[1],
        "node": row[2],
        "tool": row[3],
        "argsDigest": row[4],
        "status": row[5],
        "result": result_value,
        "error": error_value,
        "attempt": int(row[8]) if len(row) > 8 else 1,
        "reservationToken": row[9] if len(row) > 9 else "",
        "reservedAt": row[10] if len(row) > 10 else "",
        "completedAt": row[11] if len(row) > 11 else "",
        "usesReserve": bool(row[12]) if len(row) > 12 else False,
        "executionEpoch": int(row[13]) if len(row) > 13 else 0,
        "reservedTokens": int(row[14]) if len(row) > 14 else 0,
        "settled": bool(row[15]) if len(row) > 15 else False,
        "createdAt": row[16] if len(row) > 16 else "",
        "updatedAt": row[17] if len(row) > 17 else "",
    }
