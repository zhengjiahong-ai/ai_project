from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from code_worker.models import WorkerResult, failed
from services.code_execution_models import CodeExecutionJob, transition_code_execution_job
from services.trace_service import record_counter, trace_step


ZERO_DIGEST = "0" * 64
AUDIT_SCHEMA_VERSION = "1.0"


class AuditIntegrityError(RuntimeError):
    pass


def save_code_execution_job(
    job: CodeExecutionJob,
    *,
    event_type: Optional[str] = None,
    result: Optional[WorkerResult] = None,
    occurred_at: Optional[str] = None,
) -> None:
    database = _database_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        _initialize(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM code_execution_jobs WHERE job_id = ?", (job.job_id,)
            ).fetchone()
            existing_script = connection.execute(
                "SELECT script_digest FROM code_execution_scripts WHERE job_id = ?", (job.job_id,)
            ).fetchone()
            if existing is not None:
                _validated_events(
                    connection,
                    job.job_id,
                    existing["audit_event_count"],
                    existing["audit_head_digest"],
                )
                if existing_script is None or existing_script["script_digest"] != job.script_digest:
                    raise AuditIntegrityError("Persisted code execution script binding mismatch.")
                if existing["task_digest"] != job.task_digest:
                    raise AuditIntegrityError("Persisted code execution task binding mismatch.")
                _validate_persisted_transition(existing["status"], job.status, event_type)
            snapshot = job.model_dump(mode="json", by_alias=True)
            script_text = snapshot.pop("scriptText")
            now = occurred_at or _utc_now()
            connection.execute(
                """
                INSERT INTO code_execution_jobs(
                    job_id, schema_version, status, task_digest, snapshot_json,
                    audit_event_count, audit_head_digest, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    schema_version=excluded.schema_version,
                    status=excluded.status,
                    task_digest=excluded.task_digest,
                    snapshot_json=excluded.snapshot_json,
                    updated_at=excluded.updated_at
                """,
                (
                    job.job_id, job.schema_version, job.status, job.task_digest,
                    _canonical_json(snapshot), ZERO_DIGEST, now, now,
                ),
            )
            connection.execute(
                """
                INSERT INTO code_execution_scripts(job_id, script_text, script_digest)
                VALUES (?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    script_text=excluded.script_text,
                    script_digest=excluded.script_digest
                """,
                (job.job_id, script_text, job.script_digest),
            )
            if existing is None:
                _append_event(connection, job, "job_created", None, now)
                if job.approval.decision == "approved":
                    _append_event(
                        connection, job, "job_approved", None,
                        job.approval.approved_at or now,
                    )
            if event_type:
                _append_event(connection, job, event_type, result, now)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def load_code_execution_job(job_id: str) -> CodeExecutionJob:
    database = _database_path()
    try:
        with closing(sqlite3.connect(database)) as connection:
            connection.row_factory = sqlite3.Row
            _initialize(connection)
            row = connection.execute(
                "SELECT * FROM code_execution_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            script = connection.execute(
                "SELECT * FROM code_execution_scripts WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Code execution job not found: {job_id}")
            if script is None:
                raise AuditIntegrityError("Code execution script record is missing.")
            if hashlib.sha256(script["script_text"].encode("utf-8")).hexdigest() != script["script_digest"]:
                raise AuditIntegrityError("Code execution script digest mismatch.")
            snapshot = json.loads(row["snapshot_json"])
            snapshot["scriptText"] = script["script_text"]
            if snapshot.get("scriptDigest") != script["script_digest"]:
                raise AuditIntegrityError("Code execution snapshot script digest mismatch.")
            try:
                job = CodeExecutionJob.model_validate(snapshot)
            except Exception as error:
                raise AuditIntegrityError("Code execution snapshot validation failed.") from error
            if job.task_digest != row["task_digest"] or job.status != row["status"]:
                raise AuditIntegrityError("Code execution snapshot metadata mismatch.")
            _validated_events(connection, job_id, row["audit_event_count"], row["audit_head_digest"])
            return job
    except sqlite3.Error as error:
        raise AuditIntegrityError("Code execution storage cannot be read.") from error


def list_code_execution_audit_events(job_id: str) -> List[Dict[str, Any]]:
    database = _database_path()
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        _initialize(connection)
        job = connection.execute(
            "SELECT audit_event_count, audit_head_digest FROM code_execution_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if job is None:
            raise KeyError(f"Code execution job not found: {job_id}")
        rows = _validated_events(connection, job_id, job["audit_event_count"], job["audit_head_digest"])
        return [_public_event(row) for row in rows]


def list_code_execution_jobs() -> List[CodeExecutionJob]:
    database = _database_path()
    if not database.exists():
        return []
    with closing(sqlite3.connect(database)) as connection:
        _initialize(connection)
        job_ids = [row[0] for row in connection.execute(
            "SELECT job_id FROM code_execution_jobs ORDER BY updated_at DESC"
        ).fetchall()]
    return [load_code_execution_job(job_id) for job_id in job_ids]


def get_code_execution_audit_head(job_id: str) -> str:
    database = _database_path()
    with closing(sqlite3.connect(database)) as connection:
        _initialize(connection)
        row = connection.execute(
            "SELECT audit_head_digest FROM code_execution_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Code execution job not found: {job_id}")
        return str(row[0])


def execute_audited_job(
    job: CodeExecutionJob,
    input_path: Path,
    *,
    runner: Optional[Callable[[CodeExecutionJob, Path], WorkerResult]] = None,
) -> WorkerResult:
    if job.status != "approved" or job.approval.decision != "approved":
        raise ValueError("Audited execution requires an approved job.")
    if runner is None:
        from code_worker import run_job
        runner = run_job
    save_code_execution_job(job)
    running = transition_code_execution_job(job, "running")
    save_code_execution_job(running, event_type="execution_started")
    record_counter("codeExecutionCalls")
    with trace_step(
        "code_execution",
        meta={
            "jobId": job.job_id,
            "taskDigest": job.task_digest,
            "scriptDigest": job.script_digest,
            "runtime": job.runtime.model_dump(mode="json", by_alias=True),
            "image": job.image,
        },
    ) as details:
        try:
            result = runner(running, Path(input_path))
        except Exception:
            result = failed("worker_exception")
        terminal = transition_code_execution_job(running, result.status)
        save_code_execution_job(terminal, event_type="execution_finished", result=result)
        record_counter("codeExecutionOutputCount", len(result.outputs))
        if result.status != "succeeded":
            record_counter("codeExecutionFailures")
        details["outputSize"] = sum(item.size_bytes for item in result.outputs)
        details["meta"] = {
            **details["meta"],
            "status": result.status,
            "reasonCode": result.reason_code,
            "exitCode": result.exit_code,
            "outputCount": len(result.outputs),
        }
        return result


def _initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS code_execution_jobs (
            job_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            status TEXT NOT NULL,
            task_digest TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            audit_event_count INTEGER NOT NULL DEFAULT 0,
            audit_head_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS code_execution_scripts (
            job_id TEXT PRIMARY KEY REFERENCES code_execution_jobs(job_id),
            script_text TEXT NOT NULL,
            script_digest TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS code_execution_audit_events (
            job_id TEXT NOT NULL REFERENCES code_execution_jobs(job_id),
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            previous_digest TEXT NOT NULL,
            event_digest TEXT NOT NULL,
            PRIMARY KEY(job_id, sequence),
            UNIQUE(job_id, event_digest)
        );
        """
    )


def _append_event(
    connection: sqlite3.Connection,
    job: CodeExecutionJob,
    event_type: str,
    result: Optional[WorkerResult],
    occurred_at: str,
) -> None:
    allowed = {
        "job_created", "job_approved", "job_rejected", "execution_started", "execution_finished",
        "publication_approved", "publication_rejected",
    }
    if event_type not in allowed:
        raise ValueError(f"Unsupported code execution audit event: {event_type}")
    current = connection.execute(
        "SELECT audit_event_count, audit_head_digest FROM code_execution_jobs WHERE job_id = ?",
        (job.job_id,),
    ).fetchone()
    sequence = int(current[0]) + 1
    previous_digest = current[1]
    payload = _event_payload(job, event_type, result)
    digest_payload = {
        "schemaVersion": AUDIT_SCHEMA_VERSION,
        "jobId": job.job_id,
        "sequence": sequence,
        "eventType": event_type,
        "occurredAt": occurred_at,
        "payload": payload,
        "previousDigest": previous_digest,
    }
    event_digest = _digest(digest_payload)
    connection.execute(
        """
        INSERT INTO code_execution_audit_events(
            job_id, sequence, event_type, occurred_at, payload_json, previous_digest, event_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.job_id, sequence, event_type, occurred_at,
            _canonical_json(payload), previous_digest, event_digest,
        ),
    )
    connection.execute(
        "UPDATE code_execution_jobs SET audit_event_count = ?, audit_head_digest = ? WHERE job_id = ?",
        (sequence, event_digest, job.job_id),
    )


def _validate_persisted_transition(
    existing_status: str, new_status: str, event_type: Optional[str]
) -> None:
    if event_type is None and existing_status == new_status:
        return
    if event_type == "execution_started" and existing_status in {"approved", "queued"} and new_status == "running":
        return
    if event_type == "execution_finished" and existing_status == "running" and new_status in {
        "succeeded", "failed", "cancelled"
    }:
        return
    if event_type == "job_approved" and existing_status == "awaiting_approval" and new_status == "approved":
        return
    if event_type == "job_rejected" and existing_status == "awaiting_approval" and new_status == "rejected":
        return
    if event_type in {"publication_approved", "publication_rejected"} and existing_status == new_status == "succeeded":
        return
    raise ValueError(
        f"Invalid persisted code execution transition: {existing_status} -> {new_status}."
    )


def _event_payload(
    job: CodeExecutionJob, event_type: str, result: Optional[WorkerResult]
) -> Dict[str, Any]:
    common = {
        "taskDigest": job.task_digest,
        "scriptDigest": job.script_digest,
        "runtime": job.runtime.model_dump(mode="json", by_alias=True),
        "image": job.image,
        "inputs": [item.model_dump(mode="json", by_alias=True) for item in job.input_artifacts],
        "limits": job.limits.model_dump(mode="json", by_alias=True),
        "networkPolicy": job.network_policy,
    }
    if event_type == "job_created":
        return common
    if event_type == "job_approved":
        return {
            "approvedBy": job.approval.approved_by,
            "approvedAt": job.approval.approved_at,
            "approvedTaskDigest": job.approval.approved_task_digest,
            "taskDigest": job.task_digest,
            "scriptDigest": job.script_digest,
        }
    if event_type == "job_rejected":
        return {
            "decision": "rejected", "reviewedBy": job.approval.approved_by,
            "reviewedAt": job.approval.approved_at, "reason": job.approval.reason,
            "taskDigest": job.task_digest,
        }
    if event_type in {"publication_approved", "publication_rejected"}:
        return {
            "decision": job.publication_approval.decision,
            "reviewedBy": job.publication_approval.reviewed_by,
            "reviewedAt": job.publication_approval.reviewed_at,
            "publicationDigest": job.publication_digest,
            "reason": job.publication_approval.reason,
        }
    if event_type == "execution_started":
        return {**common, "status": "running"}
    assert result is not None
    return {
        "taskDigest": job.task_digest,
        "scriptDigest": job.script_digest,
        "outputs": [item.model_dump(mode="json", by_alias=True) for item in result.outputs],
        "exitStatus": {
            "status": result.status,
            "reasonCode": result.reason_code,
            "exitCode": result.exit_code,
        },
        "cleanup": result.cleanup.model_dump(mode="json", by_alias=True),
    }


def _validated_events(
    connection: sqlite3.Connection, job_id: str, expected_count: int, expected_head: str
) -> List[sqlite3.Row]:
    rows = connection.execute(
        "SELECT * FROM code_execution_audit_events WHERE job_id = ? ORDER BY sequence",
        (job_id,),
    ).fetchall()
    previous = ZERO_DIGEST
    for expected_sequence, row in enumerate(rows, start=1):
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError as error:
            raise AuditIntegrityError("Code execution audit payload is invalid.") from error
        digest_payload = {
            "schemaVersion": AUDIT_SCHEMA_VERSION,
            "jobId": job_id,
            "sequence": row["sequence"],
            "eventType": row["event_type"],
            "occurredAt": row["occurred_at"],
            "payload": payload,
            "previousDigest": row["previous_digest"],
        }
        if (
            row["sequence"] != expected_sequence
            or row["previous_digest"] != previous
            or row["event_digest"] != _digest(digest_payload)
        ):
            raise AuditIntegrityError("Code execution audit chain validation failed.")
        previous = row["event_digest"]
    if len(rows) != expected_count or previous != expected_head:
        raise AuditIntegrityError("Code execution audit chain head mismatch.")
    return rows


def _public_event(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "schemaVersion": AUDIT_SCHEMA_VERSION,
        "jobId": row["job_id"],
        "sequence": row["sequence"],
        "eventType": row["event_type"],
        "occurredAt": row["occurred_at"],
        "payload": json.loads(row["payload_json"]),
        "previousDigest": row["previous_digest"],
        "eventDigest": row["event_digest"],
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _database_path() -> Path:
    configured = os.environ.get("CODE_EXECUTION_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "code_execution.sqlite3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
