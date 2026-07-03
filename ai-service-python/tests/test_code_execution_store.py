import hashlib
import json
import sqlite3

import pytest

from code_worker import FIXED_TEMPLATE_TEXT
from services.code_execution_models import approve_code_execution_job, create_code_execution_job
from services.code_execution_store import (
    AuditIntegrityError,
    list_code_execution_audit_events,
    load_code_execution_job,
    save_code_execution_job,
)


def _approved_job():
    source = b"value\n1\n"
    job = create_code_execution_job(
        job_id="audit-job",
        artifact_id="artifact-001",
        artifact_digest=hashlib.sha256(source).hexdigest(),
        artifact_size_bytes=len(source),
        script_text=FIXED_TEMPLATE_TEXT,
    )
    return approve_code_execution_job(
        job,
        approved_by="user-001",
        approved_at="2026-07-03T10:00:00Z",
    )


def test_approved_job_is_split_persisted_and_restored(monkeypatch, tmp_path):
    database = tmp_path / "code-execution.sqlite3"
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(database))
    job = _approved_job()

    save_code_execution_job(job)
    restored = load_code_execution_job(job.job_id)

    assert restored == job
    with sqlite3.connect(database) as connection:
        snapshot = connection.execute(
            "SELECT snapshot_json FROM code_execution_jobs WHERE job_id = ?", (job.job_id,)
        ).fetchone()[0]
        script = connection.execute(
            "SELECT script_text FROM code_execution_scripts WHERE job_id = ?", (job.job_id,)
        ).fetchone()[0]
    assert "scriptText" not in json.loads(snapshot)
    assert script == FIXED_TEMPLATE_TEXT


def test_initial_save_is_idempotent_and_records_approval_binding(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(tmp_path / "audit.sqlite3"))
    job = _approved_job()

    save_code_execution_job(job)
    save_code_execution_job(job)
    events = list_code_execution_audit_events(job.job_id)

    assert [event["eventType"] for event in events] == ["job_created", "job_approved"]
    assert events[1]["payload"]["approvedBy"] == "user-001"
    assert events[1]["payload"]["approvedAt"] == "2026-07-03T10:00:00Z"
    assert events[1]["payload"]["taskDigest"] == job.task_digest
    assert events[1]["payload"]["scriptDigest"] == job.script_digest


@pytest.mark.parametrize("tamper", ["script", "event", "delete_event"])
def test_restore_fails_closed_when_persisted_state_is_tampered(monkeypatch, tmp_path, tamper):
    database = tmp_path / "tampered.sqlite3"
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(database))
    job = _approved_job()
    save_code_execution_job(job)

    with sqlite3.connect(database) as connection:
        if tamper == "script":
            connection.execute(
                "UPDATE code_execution_scripts SET script_text = ? WHERE job_id = ?",
                ("print('changed')", job.job_id),
            )
        elif tamper == "event":
            connection.execute(
                "UPDATE code_execution_audit_events SET payload_json = ? WHERE job_id = ? AND sequence = 2",
                ('{"approvedBy":"attacker"}', job.job_id),
            )
        else:
            connection.execute(
                "DELETE FROM code_execution_audit_events WHERE job_id = ? AND sequence = 2",
                (job.job_id,),
            )
        connection.commit()

    with pytest.raises(AuditIntegrityError):
        load_code_execution_job(job.job_id)


def test_failed_audit_insert_rolls_back_job_and_script(monkeypatch, tmp_path):
    database = tmp_path / "rollback.sqlite3"
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(database))
    import services.code_execution_store as store

    with sqlite3.connect(database) as connection:
        store._initialize(connection)
        connection.execute(
            """
            CREATE TRIGGER reject_audit BEFORE INSERT ON code_execution_audit_events
            BEGIN SELECT RAISE(ABORT, 'audit rejected'); END
            """
        )
        connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        save_code_execution_job(_approved_job())

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM code_execution_jobs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM code_execution_scripts").fetchone()[0] == 0


def test_save_validates_existing_chain_before_updating(monkeypatch, tmp_path):
    database = tmp_path / "validate-before-save.sqlite3"
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(database))
    job = _approved_job()
    save_code_execution_job(job)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE code_execution_audit_events SET event_digest = ? WHERE job_id = ? AND sequence = 1",
            ("f" * 64, job.job_id),
        )
        connection.commit()

    with pytest.raises(AuditIntegrityError):
        save_code_execution_job(job)


def test_terminal_job_cannot_be_overwritten_by_an_older_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(tmp_path / "terminal.sqlite3"))
    from code_worker.models import WorkerResult
    from services.code_execution_models import transition_code_execution_job

    approved = _approved_job()
    save_code_execution_job(approved)
    running = transition_code_execution_job(approved, "running")
    save_code_execution_job(running, event_type="execution_started")
    failed = transition_code_execution_job(running, "failed")
    save_code_execution_job(
        failed,
        event_type="execution_finished",
        result=WorkerResult(status="failed", reasonCode="container_failed"),
    )

    with pytest.raises(ValueError, match="Invalid persisted code execution transition"):
        save_code_execution_job(approved)
