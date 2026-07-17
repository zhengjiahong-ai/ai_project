"""Long-running research session with checkpoint/resume and background execution.

Each session has an independent token budget, auto-saves after each
sub-question, and supports pause / resume / terminate.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_SESSION_DB = os.environ.get(
    "RESEARCH_SESSION_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "research_sessions.sqlite3"),
)
DEFAULT_TOKEN_BUDGET = int(os.environ.get("PIXIU_SESSION_TOKEN_BUDGET", "2000000"))  # 2M
LOCK = threading.Lock()

VALID_STATUSES = frozenset({
    "draft", "running", "paused", "completed", "failed", "cancelled",
})


# ── SQLite ───────────────────────────────────────────────────────────────────

def _db(path: str = DEFAULT_SESSION_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    with conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS research_sessions (
                session_id  TEXT PRIMARY KEY,
                question    TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'draft',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                token_budget_total INTEGER NOT NULL DEFAULT 2000000,
                token_budget_used  INTEGER NOT NULL DEFAULT 0,
                estimated_remaining_seconds INTEGER,
                checkpoint_data TEXT NOT NULL DEFAULT '{}',
                progress     REAL NOT NULL DEFAULT 0.0,
                stage        TEXT NOT NULL DEFAULT '',
                error        TEXT NOT NULL DEFAULT ''
            )"""
        )
    return conn


# ── Public API ───────────────────────────────────────────────────────────────

def create_session(
    question: str,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    paper_ids: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new research session and return its metadata."""
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    session_id = f"session-{uuid.uuid4().hex[:16]}"
    now = _utc_now()
    checkpoint = {
        "question": question.strip(),
        "paperIds": paper_ids or [],
        "config": config or {},
        "findings": [],
        "conflicts": [],
        "evidenceItems": [],
        "completedSubQuestions": [],
        "currentSubQuestion": None,
    }

    db = _db()
    with db:
        db.execute(
            """INSERT INTO research_sessions
               (session_id, question, status, created_at, updated_at,
                token_budget_total, checkpoint_data)
               VALUES (?, ?, 'draft', ?, ?, ?, ?)""",
            (session_id, question.strip(), now, now, token_budget, json.dumps(checkpoint, ensure_ascii=False)),
        )
    return get_session(session_id)


def get_session(session_id: str) -> dict[str, Any] | None:
    """Return session metadata or None."""
    db = _db()
    row = db.execute(
        "SELECT * FROM research_sessions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def list_sessions(status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """List sessions, optionally filtered by status."""
    db = _db()
    if status and status in VALID_STATUSES:
        rows = db.execute(
            "SELECT * FROM research_sessions WHERE status=? ORDER BY updated_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM research_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_status(session_id: str, status: str, error: str = "") -> dict[str, Any] | None:
    """Update session status (running/paused/completed/failed/cancelled)."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    db = _db()
    with db:
        db.execute(
            "UPDATE research_sessions SET status=?, updated_at=?, error=? WHERE session_id=?",
            (status, _utc_now(), error[:500], session_id),
        )
    return get_session(session_id)


def checkpoint(
    session_id: str,
    findings: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    completed_sub_question: str | None = None,
    current_sub_question: str | None = None,
    progress: float = 0.0,
    stage: str = "",
    tokens_used: int = 0,
) -> dict[str, Any] | None:
    """Save a checkpoint — called after each sub-question completes."""
    db = _db()
    session = get_session(session_id)
    if not session:
        return None

    cp = json.loads(session.get("checkpointData", "{}")) if isinstance(session.get("checkpointData"), str) else session.get("checkpointData", {})

    if findings is not None:
        cp["findings"] = findings
    if conflicts is not None:
        cp["conflicts"] = conflicts
    if evidence_items is not None:
        cp["evidenceItems"] = evidence_items
    if completed_sub_question:
        cp["completedSubQuestions"] = list(set(cp.get("completedSubQuestions", []) + [completed_sub_question]))
    if current_sub_question is not None:
        cp["currentSubQuestion"] = current_sub_question

    used = (session.get("tokenBudgetUsed", 0) or 0) + tokens_used
    total = session.get("tokenBudgetTotal", DEFAULT_TOKEN_BUDGET) or DEFAULT_TOKEN_BUDGET
    remaining = max(0, total - used)

    # Estimate remaining time based on progress so far
    estimated = None
    if progress > 0.05 and used > 0:
        tokens_per_pct = used / progress
        remaining_tokens = max(0, total - used)
        remaining_pct = 1.0 - progress
        # Rough: 1 token ≈ 2ms on average
        estimated = int(min(remaining_tokens * 0.002, remaining_pct * 3600))

    with db:
        db.execute(
            """UPDATE research_sessions SET
               checkpoint_data=?, progress=?, stage=?, updated_at=?,
               token_budget_used=?, estimated_remaining_seconds=?
               WHERE session_id=?""",
            (json.dumps(cp, ensure_ascii=False), round(progress, 4), stage,
             _utc_now(), used, estimated, session_id),
        )
    return get_session(session_id)


def resume_session(session_id: str) -> dict[str, Any] | None:
    """Restore session checkpoint data for resume."""
    session = get_session(session_id)
    if not session:
        return None
    cp = session.get("checkpointData", {})
    if isinstance(cp, str):
        try:
            cp = json.loads(cp)
        except (json.JSONDecodeError, TypeError):
            cp = {}
    return {
        "sessionId": session_id,
        "question": session.get("question", ""),
        "status": session.get("status", ""),
        "checkpoint": cp,
        "progress": session.get("progress", 0),
        "tokenBudgetUsed": session.get("tokenBudgetUsed", 0),
        "tokenBudgetTotal": session.get("tokenBudgetTotal", DEFAULT_TOKEN_BUDGET),
        "estimatedRemainingSeconds": session.get("estimatedRemainingSeconds"),
    }


# ── Background execution ─────────────────────────────────────────────────────

_SESSION_EXECUTORS: dict[str, _SessionExecutor] = {}


class _SessionExecutor:
    """Runs a session in a background thread with checkpointing."""

    def __init__(
        self,
        session_id: str,
        execute_fn: Callable[..., Any],
        checkpoint_fn: Callable[..., Any] | None = None,
    ):
        self.session_id = session_id
        self._execute = execute_fn
        self._checkpoint = checkpoint_fn
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._paused = threading.Event()
        self.result: dict[str, Any] | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"session-{self.session_id[:12]}")
        self._thread.start()

    def _run(self) -> None:
        update_status(self.session_id, "running")
        try:
            self.result = self._execute(
                session_id=self.session_id,
                cancel_check=lambda: self._cancel.is_set(),
                pause_check=lambda: self._paused.is_set(),
                checkpoint_fn=self._checkpoint,
            )
            update_status(self.session_id, "completed")
        except Exception as exc:
            update_status(self.session_id, "failed", str(exc)[:500])

    def pause(self) -> bool:
        if not self._thread or not self._thread.is_alive():
            return False
        self._paused.set()
        update_status(self.session_id, "paused")
        return True

    def resume(self) -> bool:
        if not self._paused.is_set():
            return False
        self._paused.clear()
        update_status(self.session_id, "running")
        return True

    def cancel(self) -> bool:
        self._cancel.set()
        return True

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def launch_background_session(
    session_id: str,
    execute_fn: Callable[..., Any],
    checkpoint_fn: Callable[..., Any] | None = None,
) -> _SessionExecutor:
    """Launch session execution in a background thread."""
    executor = _SessionExecutor(session_id, execute_fn, checkpoint_fn)
    _SESSION_EXECUTORS[session_id] = executor
    executor.start()
    return executor


def get_executor(session_id: str) -> _SessionExecutor | None:
    return _SESSION_EXECUTORS.get(session_id)


def pause_session(session_id: str) -> bool:
    ex = get_executor(session_id)
    return ex.pause() if ex else False


def resume_execution(session_id: str) -> bool:
    ex = get_executor(session_id)
    return ex.resume() if ex else False


def cancel_session(session_id: str) -> bool:
    ex = get_executor(session_id)
    if ex:
        ex.cancel()
        update_status(session_id, "cancelled")
        return True
    return False


# ── Helpers ──────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    cp = d.get("checkpoint_data", "{}")
    if isinstance(cp, str):
        try:
            d["checkpointData"] = json.loads(cp)
        except (json.JSONDecodeError, TypeError):
            d["checkpointData"] = {}
    return d
