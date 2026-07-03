import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from services.code_execution_models import (
    approve_code_execution_job,
    create_code_execution_job,
    transition_code_execution_job,
)

from code_worker import FIXED_TEMPLATE_TEXT, run_job, start_job
from code_worker.models import WorkerCleanup, WorkerOutput, WorkerResult
from code_worker.runner import _ExecutionContext, _container_command, _validate_job
from code_worker.fixed_template import analyze_csv
from services.code_execution_models import WORKER_IMAGE_DIGEST


def _job(input_path: Path, *, approved: bool = True):
    data = input_path.read_bytes()
    job = create_code_execution_job(
        job_id="job-001",
        artifact_id="artifact-001",
        artifact_digest=hashlib.sha256(data).hexdigest(),
        artifact_size_bytes=len(data),
        script_text=FIXED_TEMPLATE_TEXT,
    )
    if approved:
        job = approve_code_execution_job(
            job,
            approved_by="user-001",
            approved_at="2026-07-02T10:00:00Z",
        )
    return job


def _input(tmp_path: Path) -> Path:
    path = tmp_path / "input.csv"
    path.write_text("group,value\na,1\na,3\nb,2\n", encoding="utf-8")
    return path


def test_fixed_template_emits_complete_bounded_descriptive_statistics(tmp_path):
    input_path = tmp_path / "statistics.csv"
    output_path = tmp_path / "statistics.json"
    input_path.write_text("group,value\na,1\nb,2\nc,\nd,4\n", encoding="utf-8")

    analyze_csv(input_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["rowCount"] == 4
    assert payload["columns"]["value"] == {
        "missingCount": 1,
        "numericCount": 3,
        "min": 1.0,
        "max": 4.0,
        "mean": 7 / 3,
        "median": 2.0,
        "sampleStandardDeviation": 1.5275252316519468,
        "quartiles": [1.0, 2.0, 4.0],
    }


def test_fixed_template_rejects_duplicate_headers(tmp_path):
    input_path = tmp_path / "duplicate.csv"
    input_path.write_text("value,value\n1,2\n", encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="invalid_columns"):
        analyze_csv(input_path, tmp_path / "output.json")


def test_rejects_unapproved_job_without_starting_docker(tmp_path):
    input_path = _input(tmp_path)

    with patch("code_worker.runner.subprocess.run") as run:
        result = run_job(_job(input_path, approved=False), input_path)

    assert result.model_dump(by_alias=True) == {
        "status": "failed",
        "reasonCode": "job_not_approved",
        "exitCode": None,
        "outputs": [],
        "cleanup": {"status": "passed", "stage": "completed", "residualCount": 0},
    }
    run.assert_not_called()


def test_accepts_host_persisted_running_job_with_bound_approval(tmp_path):
    input_path = _input(tmp_path)
    running = transition_code_execution_job(_job(input_path), "running")

    assert _validate_job(running, input_path) is None


def test_rejects_non_file_digest_and_size_mismatches_before_docker(tmp_path):
    input_path = _input(tmp_path)
    job = _job(input_path)
    cases = [
        (tmp_path / "missing.csv", "input_not_regular_file"),
        (tmp_path, "input_not_regular_file"),
    ]
    input_path.write_text("changed", encoding="utf-8")
    cases.append((input_path, "input_size_mismatch"))

    with patch("code_worker.runner.subprocess.run") as run:
        for path, reason in cases:
            assert run_job(job, path).reason_code == reason

    run.assert_not_called()


def test_rejects_same_size_digest_mismatch_and_non_fixed_script(tmp_path):
    input_path = _input(tmp_path)
    job = _job(input_path)
    original = input_path.read_bytes()
    input_path.write_bytes(original.replace(b"a,1", b"a,9"))

    with patch("code_worker.runner.subprocess.run") as run:
        assert run_job(job, input_path).reason_code == "input_digest_mismatch"

        changed = job.model_dump(mode="json", by_alias=True)
        changed["scriptText"] = "print('arbitrary')\n"
        changed["scriptDigest"] = hashlib.sha256(changed["scriptText"].encode()).hexdigest()
        changed.pop("taskDigest")
        changed["status"] = "awaiting_approval"
        changed["approval"] = {"decision": "pending"}
        arbitrary = create_code_execution_job(
            job_id="job-002",
            artifact_id="artifact-001",
            artifact_digest=hashlib.sha256(input_path.read_bytes()).hexdigest(),
            artifact_size_bytes=len(input_path.read_bytes()),
            script_text=changed["scriptText"],
        )
        arbitrary = approve_code_execution_job(
            arbitrary, approved_by="user-001", approved_at="2026-07-02T10:00:00Z"
        )
        assert run_job(arbitrary, input_path).reason_code == "template_mismatch"

    run.assert_not_called()


def test_runs_hardened_container_and_returns_bounded_output_metadata(tmp_path):
    input_path = _input(tmp_path)
    job = _job(input_path)
    context = _ExecutionContext("test-container", tmp_path / "output", __import__("threading").Event())
    command = _container_command(job, input_path, context)
    assert command[:2] == ["docker", "run"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--cap-drop"):command.index("--cap-drop") + 2] == ["--cap-drop", "ALL"]
    assert "no-new-privileges=true" in command
    assert command[command.index("--memory-swap") + 1] == str(job.limits.memory_bytes)
    assert command[command.index("--pids-limit") + 1] == str(job.limits.pids)
    assert command[command.index("--ulimit") + 1] == "cpu=5:5"
    assert not any("docker.sock" in part for part in command)
    assert not any("code_execution" in part or ".sqlite" in part for part in command)

    completed = WorkerResult(
        status="succeeded", reasonCode="completed", exitCode=0,
        outputs=[WorkerOutput(sizeBytes=10, digest="0" * 64)],
    )
    with patch("code_worker.runner._execute_job", return_value=completed):
        result = run_job(job, input_path)

    assert result.status == "succeeded"
    assert result.reason_code == "completed"
    assert result.exit_code == 0
    assert len(result.outputs) == 1
    assert result.outputs[0].name == "statistics"
    assert result.outputs[0].media_type == "application/json"
    assert result.outputs[0].size_bytes > 0
    assert len(result.outputs[0].digest) == 64


def test_docker_failures_are_stable_and_do_not_leak_paths_or_stderr(tmp_path):
    input_path = _input(tmp_path)
    job = _job(input_path)

    with patch("code_worker.runner.subprocess.Popen", side_effect=OSError(str(Path.home()) + " secret")):
        unavailable = run_job(job, input_path)
    with patch("code_worker.runner._execute_job", return_value=WorkerResult(status="failed", reasonCode="container_failed", exitCode=17)):
        failed = run_job(job, input_path)

    assert unavailable.reason_code == "docker_unavailable"
    assert unavailable.exit_code is None
    assert failed.reason_code == "container_failed"
    assert failed.exit_code == 17
    serialized = json.dumps([unavailable.model_dump(by_alias=True), failed.model_dump(by_alias=True)])
    assert "secret" not in serialized
    assert str(tmp_path) not in serialized


def test_container_timeout_has_a_distinct_stable_reason(tmp_path):
    input_path = _input(tmp_path)
    with patch("code_worker.runner._execute_job", return_value=WorkerResult(status="failed", reasonCode="wall_clock_limit_exceeded")):
        result = run_job(_job(input_path), input_path)

    assert result.reason_code == "wall_clock_limit_exceeded"
    assert result.exit_code is None
    assert "sensitive" not in json.dumps(result.model_dump(by_alias=True))


def test_worker_result_exposes_bounded_cleanup_and_cancelled_status():
    result = WorkerResult(
        status="cancelled",
        reasonCode="cancelled",
        cleanup=WorkerCleanup(status="passed", stage="completed", residualCount=0),
    )

    assert result.model_dump(by_alias=True) == {
        "status": "cancelled",
        "reasonCode": "cancelled",
        "exitCode": None,
        "outputs": [],
        "cleanup": {"status": "passed", "stage": "completed", "residualCount": 0},
    }


def test_start_job_returns_cancellable_execution_handle_without_changing_run_job_contract(tmp_path):
    input_path = _input(tmp_path)

    with patch("code_worker.runner._execute_job") as execute:
        execute.return_value = WorkerResult(status="failed", reasonCode="docker_unavailable")
        execution = start_job(_job(input_path), input_path)
        result = execution.wait()

    assert execution.cancel() is False
    assert result.reason_code == "docker_unavailable"


def test_cleanup_failure_overrides_execution_result_without_leaking_directory(tmp_path):
    input_path = _input(tmp_path)
    completed = WorkerResult(status="succeeded", reasonCode="completed", exitCode=0)
    isolated_output = tmp_path / "isolated-output"

    with patch("code_worker.runner.tempfile.mkdtemp", return_value=str(isolated_output)), patch(
        "code_worker.runner._execute_job", return_value=completed
    ), patch(
        "code_worker.runner._cleanup_execution", return_value=WorkerCleanup(
            status="failed", stage="temporary_directory", residualCount=1
        )
    ):
        result = start_job(_job(input_path), input_path).wait()

    assert result.status == "failed"
    assert result.reason_code == "cleanup_failed"
    assert result.cleanup.stage == "temporary_directory"
    assert str(tmp_path) not in json.dumps(result.model_dump(by_alias=True))


def test_live_fixed_worker_image_executes_when_available(tmp_path):
    inspected = subprocess.run(
        ["docker", "image", "inspect", WORKER_IMAGE_DIGEST],
        capture_output=True,
        check=False,
    )
    if inspected.returncode != 0:
        import pytest

        pytest.skip("fixed P5-04 Worker image is not available locally")

    input_path = _input(tmp_path)
    original = input_path.read_bytes()
    result = run_job(_job(input_path), input_path)

    assert result.status == "succeeded"
    assert result.reason_code == "completed"
    assert result.outputs[0].size_bytes <= 1024 * 1024
    assert input_path.read_bytes() == original
