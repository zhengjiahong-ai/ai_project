from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from services.code_execution_models import CodeExecutionJob, WORKER_IMAGE_DIGEST

from .models import WorkerCleanup, WorkerOutput, WorkerResult, failed


PACKAGE_DIR = Path(__file__).resolve().parent
FIXED_TEMPLATE_PATH = PACKAGE_DIR / "fixed_template.py"
SECCOMP_PATH = PACKAGE_DIR / "seccomp.json"
OUTPUT_NAME = "statistics.json"
MAX_OUTPUT_FILES = 1


def _fixed_template_text() -> str:
    return FIXED_TEMPLATE_PATH.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class _ExecutionContext:
    name: str
    output_dir: Path
    cancel_event: threading.Event
    process: Optional[subprocess.Popen] = None
    container_created: bool = False


class _OutputBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.consumed = 0
        self._lock = threading.Lock()

    def consume(self, size: int) -> bool:
        with self._lock:
            self.consumed += size
            return self.consumed > self.limit


class WorkerExecution:
    def __init__(self, job: CodeExecutionJob, input_path: Path):
        self._context = _ExecutionContext(
            name=f"pixiu-code-worker-{uuid.uuid4().hex}",
            output_dir=Path(tempfile.mkdtemp(prefix="pixiu-code-worker-")),
            cancel_event=threading.Event(),
        )
        self._job = job
        self._input_path = Path(input_path)
        self._result: Optional[WorkerResult] = None
        self._thread = threading.Thread(target=self._run, name=self._context.name, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        result = _execute_job(self._job, self._input_path, self._context)
        cleanup = _cleanup_execution(self._context)
        if cleanup.status == "failed":
            result = failed("cleanup_failed", result.exit_code)
        self._result = result.model_copy(update={"cleanup": cleanup})

    def cancel(self) -> bool:
        if not self._thread.is_alive():
            return False
        self._context.cancel_event.set()
        process = self._context.process
        if process is not None:
            _docker(["kill", self._context.name], timeout=2)
        return True

    def wait(self, timeout: Optional[float] = None) -> WorkerResult:
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise TimeoutError("worker_wait_timeout")
        assert self._result is not None
        return self._result


def start_job(job: CodeExecutionJob, input_path: Path) -> WorkerExecution:
    return WorkerExecution(job, input_path)


def run_job(job: CodeExecutionJob, input_path: Path) -> WorkerResult:
    return start_job(job, input_path).wait()


def _validate_job(job: CodeExecutionJob, path: Path) -> Optional[WorkerResult]:
    if job.status not in {"approved", "running"} or job.approval.decision != "approved":
        return failed("job_not_approved")
    if job.script_text != _fixed_template_text():
        return failed("template_mismatch")
    if job.image != WORKER_IMAGE_DIGEST:
        return failed("image_mismatch")
    if not path.is_file() or path.is_symlink():
        return failed("input_not_regular_file")
    artifact = job.input_artifacts[0]
    size = path.stat().st_size
    if size != artifact.size_bytes or size > job.limits.input_bytes:
        return failed("input_size_mismatch")
    if _sha256(path) != artifact.digest:
        return failed("input_digest_mismatch")
    return None


def _docker(arguments: list[str], *, timeout: float = 5) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=timeout, check=False
    )


def _container_command(job: CodeExecutionJob, path: Path, context: _ExecutionContext) -> list[str]:
    limits = job.limits
    return [
        "docker", "run", "--name", context.name, "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
        "--security-opt", f"seccomp={SECCOMP_PATH}",
        "--memory", str(limits.memory_bytes), "--memory-swap", str(limits.memory_bytes),
        "--cpus", str(limits.cpu_count), "--pids-limit", str(limits.pids),
        "--ulimit", f"cpu={limits.wall_clock_seconds}:{limits.wall_clock_seconds}",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,size={limits.tmpfs_bytes}",
        "--mount", f"type=bind,src={path.resolve()},dst=/input/data.csv,readonly",
        "--mount", f"type=bind,src={context.output_dir.resolve()},dst=/output",
        WORKER_IMAGE_DIGEST,
    ]


def _drain_bounded(pipe: Optional[BinaryIO], budget: _OutputBudget, exceeded: threading.Event) -> None:
    if pipe is None:
        return
    try:
        while True:
            chunk = pipe.read(64 * 1024)
            if not chunk:
                return
            if budget.consume(len(chunk)):
                exceeded.set()
                return
    finally:
        pipe.close()


def _execute_job(job: CodeExecutionJob, path: Path, context: _ExecutionContext) -> WorkerResult:
    invalid = _validate_job(job, path)
    if invalid is not None:
        return invalid
    stdout_exceeded = threading.Event()
    output_budget = _OutputBudget(job.limits.stdout_bytes)
    try:
        process = subprocess.Popen(
            _container_command(job, path, context), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except OSError:
        return failed("docker_unavailable")
    context.process = process
    context.container_created = True
    readers = [
        threading.Thread(
            target=_drain_bounded,
            args=(pipe, output_budget, stdout_exceeded),
            daemon=True,
        )
        for pipe in (process.stdout, process.stderr)
    ]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + job.limits.wall_clock_seconds
    reason: Optional[str] = None
    while process.poll() is None:
        if context.cancel_event.is_set():
            reason = "cancelled"
            break
        if stdout_exceeded.is_set():
            reason = "stdout_limit_exceeded"
            break
        if time.monotonic() >= deadline:
            reason = "wall_clock_limit_exceeded"
            break
        time.sleep(0.02)
    if reason is not None:
        _docker(["kill", context.name], timeout=2)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        for reader in readers:
            reader.join(timeout=1)
        if reason == "cancelled":
            return WorkerResult(status="cancelled", reasonCode=reason)
        return failed(reason)
    for reader in readers:
        reader.join(timeout=1)
    if stdout_exceeded.is_set():
        return failed("stdout_limit_exceeded", process.returncode)
    if process.returncode != 0:
        return failed(_classify_container_failure(context.name, process.returncode), process.returncode)
    return _validate_outputs(job, context.output_dir, process.returncode)


def _classify_container_failure(name: str, exit_code: Optional[int]) -> str:
    try:
        inspected = _docker(["inspect", name, "--format", "{{json .State}}"], timeout=2)
        state = json.loads(inspected.stdout) if inspected.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        state = {}
    if state.get("OOMKilled") is True:
        return "memory_limit_exceeded"
    error = str(state.get("Error") or "").lower()
    if "pids" in error or "resource temporarily unavailable" in error:
        return "process_limit_exceeded"
    if exit_code in (152,):
        return "cpu_limit_exceeded"
    return "container_failed"


def _validate_outputs(job: CodeExecutionJob, output_dir: Path, exit_code: int) -> WorkerResult:
    entries = list(output_dir.rglob("*"))
    files = [entry for entry in entries if entry.is_file() and not entry.is_symlink()]
    if len(entries) > MAX_OUTPUT_FILES or len(files) > MAX_OUTPUT_FILES:
        return failed("output_file_count_exceeded", exit_code)
    output = output_dir / OUTPUT_NAME
    if len(files) != 1 or files[0] != output:
        return failed("output_missing", exit_code)
    output_size = output.stat().st_size
    expected = job.expected_outputs[0]
    if output_size < 1:
        return failed("output_size_invalid", exit_code)
    if output_size > expected.max_bytes:
        return failed("output_size_exceeded", exit_code)
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return failed("output_invalid", exit_code)
    if not isinstance(payload, dict) or payload.get("schemaVersion") != "1.0":
        return failed("output_invalid", exit_code)
    metadata = WorkerOutput(
        name="statistics", mediaType="application/json", sizeBytes=output_size, digest=_sha256(output)
    )
    return WorkerResult(status="succeeded", reasonCode="completed", exitCode=0, outputs=[metadata])


def _cleanup_execution(context: _ExecutionContext) -> WorkerCleanup:
    residual = 0
    failed_stage: Optional[str] = None
    if context.container_created:
        try:
            _docker(["kill", context.name], timeout=2)
            _docker(["rm", "-f", context.name], timeout=3)
            checked = _docker(["ps", "-aq", "--filter", f"name=^{context.name}$"], timeout=2)
            residual = len([line for line in checked.stdout.splitlines() if line.strip()])
            if checked.returncode != 0 or residual:
                failed_stage = "container"
                residual = max(1, residual)
        except (OSError, subprocess.TimeoutExpired):
            failed_stage = "container"
            residual = 1
    try:
        shutil.rmtree(context.output_dir)
    except OSError:
        if failed_stage is None:
            failed_stage = "temporary_directory"
        residual = max(1, residual)
    if failed_stage is not None:
        return WorkerCleanup(status="failed", stage=failed_stage, residualCount=residual)
    return WorkerCleanup(status="passed", stage="completed", residualCount=0)
