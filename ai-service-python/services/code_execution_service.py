from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_worker.models import WorkerResult
from services.code_execution_models import (
    approve_code_execution_job,
    attach_execution_result,
    create_code_execution_job,
    reject_code_execution_job,
    review_code_execution_publication,
)
from services.code_execution_store import (
    execute_audited_job,
    get_code_execution_audit_head,
    list_code_execution_audit_events,
    list_code_execution_jobs,
    load_code_execution_job,
    save_code_execution_job,
)

MAX_ARTIFACT_BYTES = 1024 * 1024
LOCAL_ACTOR = "local-user"


class ArtifactIntegrityError(RuntimeError):
    pass


class ReviewConflictError(RuntimeError):
    pass


def stage_csv_artifact(filename: str, content: bytes) -> dict[str, Any]:
    if not filename or not filename.lower().endswith(".csv"):
        raise ValueError("Only .csv artifacts are accepted.")
    if not content or len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("CSV artifact size must be between 1 byte and 1 MiB.")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("CSV artifact must be UTF-8 encoded.") from error
    if b"\x00" in content:
        raise ValueError("CSV artifact cannot contain NUL bytes.")
    artifact_id = f"artifact-{uuid.uuid4().hex}"
    digest = hashlib.sha256(content).hexdigest()
    root = _artifact_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{artifact_id}.csv"
    metadata = {
        "artifactId": artifact_id,
        "filename": Path(filename).name[:255],
        "digest": digest,
        "mediaType": "text/csv",
        "sizeBytes": len(content),
        "createdAt": _utc_now(),
    }
    path.write_bytes(content)
    (root / f"{artifact_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return metadata


def resolve_artifact(artifact_id: str) -> Path:
    if not artifact_id.startswith("artifact-") or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in artifact_id):
        raise KeyError(f"Code execution artifact not found: {artifact_id}")
    root = _artifact_root()
    path = root / f"{artifact_id}.csv"
    metadata_path = root / f"{artifact_id}.json"
    if not path.is_file() or not metadata_path.is_file():
        raise KeyError(f"Code execution artifact not found: {artifact_id}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ArtifactIntegrityError("Code execution artifact metadata is invalid.") from error
    content = path.read_bytes()
    if (
        metadata.get("artifactId") != artifact_id
        or metadata.get("sizeBytes") != len(content)
        or metadata.get("digest") != hashlib.sha256(content).hexdigest()
    ):
        raise ArtifactIntegrityError("Code execution artifact binding mismatch.")
    return path


def create_job(artifact_id: str) -> dict[str, Any]:
    path = resolve_artifact(artifact_id)
    metadata = _artifact_metadata(artifact_id)
    script = (Path(__file__).parents[1] / "code_worker" / "fixed_template.py").read_text(encoding="utf-8")
    job = create_code_execution_job(
        job_id=f"job-{uuid.uuid4().hex}", artifact_id=artifact_id,
        artifact_digest=metadata["digest"], artifact_size_bytes=metadata["sizeBytes"], script_text=script,
    )
    if path.stat().st_size != metadata["sizeBytes"]:
        raise ArtifactIntegrityError("Code execution artifact size changed.")
    save_code_execution_job(job)
    return {"status": "success", "job": _job_view(job)}


def list_jobs() -> dict[str, Any]:
    return {"status": "success", "jobs": [_job_view(job) for job in list_code_execution_jobs()]}


def get_job(job_id: str) -> dict[str, Any]:
    return {"status": "success", "job": _job_view(load_code_execution_job(job_id))}


def review_execution(
    job_id: str,
    decision: str,
    expected_task_digest: str,
    reason: str | None = None,
    *,
    runner: Callable[..., WorkerResult] | None = None,
) -> dict[str, Any]:
    job = load_code_execution_job(job_id)
    if expected_task_digest != job.task_digest:
        raise ReviewConflictError("Execution task digest is stale.")
    now = _utc_now()
    if decision == "rejected":
        reviewed = reject_code_execution_job(job, rejected_by=LOCAL_ACTOR, rejected_at=now, reason=reason)
        save_code_execution_job(reviewed, event_type="job_rejected")
        return {"status": "success", "job": _job_view(reviewed)}
    if decision != "approved":
        raise ValueError("Execution decision must be approved or rejected.")
    approved = approve_code_execution_job(job, approved_by=LOCAL_ACTOR, approved_at=now)
    save_code_execution_job(approved, event_type="job_approved")
    input_path = resolve_artifact(approved.input_artifacts[0].artifact_id)
    result = execute_audited_job(approved, input_path, runner=runner)
    terminal = load_code_execution_job(job_id)
    completed = attach_execution_result(
        approved, result, audit_head_digest=get_code_execution_audit_head(job_id)
    )
    if completed.status != terminal.status:
        raise ArtifactIntegrityError("Persisted execution status mismatch.")
    save_code_execution_job(completed)
    return {"status": "success", "job": _job_view(completed)}


def review_publication(
    job_id: str, decision: str, expected_publication_digest: str, reason: str | None = None
) -> dict[str, Any]:
    job = load_code_execution_job(job_id)
    if expected_publication_digest != job.publication_digest:
        raise ReviewConflictError("Publication digest is stale.")
    reviewed = review_code_execution_publication(
        job, decision=decision, reviewed_by=LOCAL_ACTOR, reviewed_at=_utc_now(),
        expected_publication_digest=expected_publication_digest, reason=reason,
    )
    save_code_execution_job(reviewed, event_type=f"publication_{decision}")
    return {"status": "success", "job": _job_view(reviewed)}


def _job_view(job) -> dict[str, Any]:
    payload = job.model_dump(mode="json", by_alias=True)
    payload["publishable"] = job.publishable
    try:
        payload["auditEvents"] = list_code_execution_audit_events(job.job_id)
    except KeyError:
        payload["auditEvents"] = []
    return payload


def _artifact_metadata(artifact_id: str) -> dict[str, Any]:
    resolve_artifact(artifact_id)
    return json.loads((_artifact_root() / f"{artifact_id}.json").read_text(encoding="utf-8"))


def _artifact_root() -> Path:
    configured = os.getenv("CODE_EXECUTION_ARTIFACT_DIR", "").strip()
    return Path(configured) if configured else Path(__file__).parents[1] / "data" / "code_execution_artifacts"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
