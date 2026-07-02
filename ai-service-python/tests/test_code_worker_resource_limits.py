import io
import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmarks.code_sandbox.runner import existing_image_id, run_docker_candidate
from code_worker.models import WorkerResult
from code_worker.runner import (
    _ExecutionContext,
    _OutputBudget,
    _classify_container_failure,
    _cleanup_execution,
    _drain_bounded,
    _validate_outputs,
)
from services.code_execution_models import approve_code_execution_job, create_code_execution_job
from code_worker import FIXED_TEMPLATE_TEXT, start_job


def _job(tmp_path: Path):
    source = tmp_path / "input.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    import hashlib
    data = source.read_bytes()
    job = create_code_execution_job(
        job_id="resource-job", artifact_id="resource-artifact",
        artifact_digest=hashlib.sha256(data).hexdigest(), artifact_size_bytes=len(data),
        script_text=FIXED_TEMPLATE_TEXT,
    )
    return approve_code_execution_job(job, approved_by="user", approved_at="2026-07-02T10:00:00Z"), source


def test_stdout_and_stderr_share_one_output_budget():
    exceeded = threading.Event()
    budget = _OutputBudget(10)

    _drain_bounded(io.BytesIO(b"123456"), budget, exceeded)
    _drain_bounded(io.BytesIO(b"abcdef"), budget, exceeded)

    assert exceeded.is_set()
    assert budget.consumed == 12


def test_output_file_count_and_total_size_are_enforced(tmp_path):
    job, _ = _job(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "statistics.json").write_text(json.dumps({"schemaVersion": "1.0"}), encoding="utf-8")
    (output / "extra.txt").write_text("unexpected", encoding="utf-8")

    result = _validate_outputs(job, output, 0)

    assert result.reason_code == "output_file_count_exceeded"


def test_output_byte_limit_has_a_stable_reason(tmp_path):
    job, _ = _job(tmp_path)
    output = tmp_path / "oversized"
    output.mkdir()
    (output / "statistics.json").write_bytes(b"x" * (job.expected_outputs[0].max_bytes + 1))

    assert _validate_outputs(job, output, 0).reason_code == "output_size_exceeded"


@pytest.mark.parametrize(
    ("state", "exit_code", "reason"),
    [
        ({"OOMKilled": True}, 137, "memory_limit_exceeded"),
        ({"Error": "resource temporarily unavailable (pids limit)"}, 1, "process_limit_exceeded"),
        ({}, 152, "cpu_limit_exceeded"),
    ],
)
def test_runtime_limit_failures_have_stable_reasons(state, exit_code, reason):
    inspected = subprocess.CompletedProcess([], 0, stdout=json.dumps(state), stderr="")
    with patch("code_worker.runner._docker", return_value=inspected):
        assert _classify_container_failure("bounded-container", exit_code) == reason


def test_cancel_marks_running_execution_and_leaves_cleanup_observable(tmp_path):
    job, source = _job(tmp_path)

    def wait_for_cancel(job, path, context):
        assert context.cancel_event.wait(timeout=2)
        return WorkerResult(status="cancelled", reasonCode="cancelled")

    with patch("code_worker.runner._execute_job", side_effect=wait_for_cancel):
        execution = start_job(job, source)
        assert execution.cancel() is True
        result = execution.wait()

    assert result.status == "cancelled"
    assert result.cleanup.status == "passed"


def test_temporary_directory_cleanup_is_attempted_when_container_cleanup_fails(tmp_path):
    directory = tmp_path / "polluted"
    directory.mkdir()
    context = _ExecutionContext("resource-container", directory, threading.Event(), container_created=True)
    failed = subprocess.CompletedProcess([], 1, stdout="", stderr="")

    with patch("code_worker.runner._docker", return_value=failed), patch(
        "code_worker.runner.shutil.rmtree"
    ) as remove_tree:
        cleanup = _cleanup_execution(context)

    remove_tree.assert_called_once_with(directory)
    assert cleanup.status == "failed"
    assert cleanup.stage == "container"


def test_missing_container_is_clean_when_residual_check_is_empty(tmp_path):
    directory = tmp_path / "finished"
    directory.mkdir()
    context = _ExecutionContext("already-removed", directory, threading.Event(), container_created=True)
    responses = [
        subprocess.CompletedProcess([], 1, stdout="", stderr=""),
        subprocess.CompletedProcess([], 1, stdout="", stderr=""),
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    ]

    with patch("code_worker.runner._docker", side_effect=responses):
        cleanup = _cleanup_execution(context)

    assert cleanup.status == "passed"
    assert cleanup.residual_count == 0


def test_live_docker_resource_attacks_when_runtime_is_available(tmp_path):
    directory = Path(__file__).parents[1] / "benchmarks" / "code_sandbox"
    if not existing_image_id("pixiu-code-sandbox-benchmark:p5-02"):
        pytest.skip("fixed P5-02 resource attack image is not available locally")
    input_file = directory / "fixtures" / "normal.csv"

    candidate, _ = run_docker_candidate(directory, input_file)

    assert candidate["available"] is True
    for probe in ("cpu_limit", "memory_limit", "stdout_limit", "subprocess", "cleanup"):
        assert candidate["probes"][probe]["status"] == "passed"
