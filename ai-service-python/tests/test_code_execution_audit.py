import hashlib
import json

from code_worker import FIXED_TEMPLATE_TEXT
from code_worker.models import WorkerCleanup, WorkerOutput, WorkerResult
from services import trace_service
from services.code_execution_models import approve_code_execution_job, create_code_execution_job
from services.code_execution_store import execute_audited_job, list_code_execution_audit_events, load_code_execution_job


def _job(source: bytes):
    job = create_code_execution_job(
        job_id="execution-job",
        artifact_id="artifact-001",
        artifact_digest=hashlib.sha256(source).hexdigest(),
        artifact_size_bytes=len(source),
        script_text=FIXED_TEMPLATE_TEXT,
    )
    return approve_code_execution_job(
        job, approved_by="user-001", approved_at="2026-07-03T10:00:00Z"
    )


def test_audited_execution_persists_bounded_success_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(tmp_path / "execution.sqlite3"))
    source = tmp_path / "input.csv"
    source.write_bytes(b"value\n1\n")
    output_digest = "a" * 64
    result = WorkerResult(
        status="succeeded",
        reasonCode="completed",
        exitCode=0,
        outputs=[WorkerOutput(sizeBytes=42, digest=output_digest)],
        cleanup=WorkerCleanup(status="passed", stage="completed", residualCount=0),
    )
    trace_id = trace_service.start_trace("code_execution")

    returned = execute_audited_job(_job(source.read_bytes()), source, runner=lambda *_: result)

    assert returned == result
    assert load_code_execution_job("execution-job").status == "succeeded"
    events = list_code_execution_audit_events("execution-job")
    assert [item["eventType"] for item in events] == [
        "job_created", "job_approved", "execution_started", "execution_finished"
    ]
    finished = events[-1]["payload"]
    assert finished["outputs"] == [{
        "name": "statistics", "mediaType": "application/json", "sizeBytes": 42,
        "digest": output_digest,
    }]
    assert finished["exitStatus"] == {"status": "succeeded", "reasonCode": "completed", "exitCode": 0}
    serialized = json.dumps(events)
    assert FIXED_TEMPLATE_TEXT not in serialized
    assert str(tmp_path) not in serialized
    snapshot = trace_service.get_trace_snapshot(trace_id)
    assert snapshot["counters"]["codeExecutionCalls"] == 1
    assert snapshot["counters"]["codeExecutionOutputCount"] == 1
    assert snapshot["steps"][-1]["name"] == "code_execution"


def test_audited_execution_records_failure_without_raw_error(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(tmp_path / "failed.sqlite3"))
    source = tmp_path / "input.csv"
    source.write_bytes(b"value\n1\n")
    result = WorkerResult(
        status="failed", reasonCode="wall_clock_limit_exceeded",
        cleanup=WorkerCleanup(status="passed", stage="completed", residualCount=0),
    )
    trace_id = trace_service.start_trace("code_execution")

    execute_audited_job(_job(source.read_bytes()), source, runner=lambda *_: result)

    assert load_code_execution_job("execution-job").status == "failed"
    snapshot = trace_service.get_trace_snapshot(trace_id)
    assert snapshot["counters"]["codeExecutionFailures"] == 1
    serialized = json.dumps(list_code_execution_audit_events("execution-job")).lower()
    assert '"stdout":' not in serialized
    assert '"stderr":' not in serialized
