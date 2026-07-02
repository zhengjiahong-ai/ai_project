from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from services.code_execution_models import CodeExecutionJob, WORKER_IMAGE_DIGEST

from .models import WorkerOutput, WorkerResult, failed


PACKAGE_DIR = Path(__file__).resolve().parent
FIXED_TEMPLATE_PATH = PACKAGE_DIR / "fixed_template.py"
SECCOMP_PATH = PACKAGE_DIR / "seccomp.json"
OUTPUT_NAME = "statistics.json"


def _fixed_template_text() -> str:
    return FIXED_TEMPLATE_PATH.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_job(job: CodeExecutionJob, input_path: Path) -> WorkerResult:
    path = Path(input_path)
    if job.status != "approved" or job.approval.decision != "approved":
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

    with tempfile.TemporaryDirectory(prefix="pixiu-code-worker-") as temporary:
        output_dir = Path(temporary)
        command = [
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
            "--security-opt", f"seccomp={SECCOMP_PATH}",
            "--memory", str(job.limits.memory_bytes), "--memory-swap", str(job.limits.memory_bytes),
            "--cpus", str(job.limits.cpu_count), "--pids-limit", str(job.limits.pids),
            "--tmpfs", f"/tmp:rw,noexec,nosuid,size={job.limits.tmpfs_bytes}",
            "--mount", f"type=bind,src={path.resolve()},dst=/input/data.csv,readonly",
            "--mount", f"type=bind,src={output_dir.resolve()},dst=/output",
            WORKER_IMAGE_DIGEST,
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=job.limits.wall_clock_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return failed("container_timeout")
        except OSError:
            return failed("docker_unavailable")
        if completed.returncode != 0:
            return failed("container_failed", completed.returncode)

        output = output_dir / OUTPUT_NAME
        if not output.is_file() or output.is_symlink():
            return failed("output_missing", completed.returncode)
        output_size = output.stat().st_size
        expected = job.expected_outputs[0]
        if output_size < 1 or output_size > expected.max_bytes:
            return failed("output_size_invalid", completed.returncode)
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return failed("output_invalid", completed.returncode)
        if not isinstance(payload, dict) or payload.get("schemaVersion") != "1.0":
            return failed("output_invalid", completed.returncode)

        metadata = WorkerOutput(
            name="statistics",
            mediaType="application/json",
            sizeBytes=output_size,
            digest=_sha256(output),
        )
        return WorkerResult(status="succeeded", reasonCode="completed", exitCode=0, outputs=[metadata])
