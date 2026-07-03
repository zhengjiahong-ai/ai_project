from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"
WORKER_IMAGE_DIGEST = "sha256:a86ea9eda049b10d4958ee67d7c6284d07ecbcab3a50d5778c44809318b6e237"
# Compatibility alias for P5-03 snapshots and imports. New code must use the Worker name.
BENCHMARK_IMAGE_DIGEST = WORKER_IMAGE_DIGEST
BENCHMARK_RUNTIME_NAME = "python"
BENCHMARK_RUNTIME_VERSION = "3.13.9"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class _ExecutionModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class InputArtifact(_ExecutionModel):
    artifact_id: str = Field(alias="artifactId")
    digest: str
    media_type: Literal["text/csv"] = Field(default="text/csv", alias="mediaType")
    size_bytes: int = Field(default=1, ge=1, le=1024 * 1024, alias="sizeBytes")

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("artifactId must be an opaque identifier, not a path or URI.")
        return value

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("digest must be a lowercase SHA-256 hex value.")
        return value


class RuntimeSpec(_ExecutionModel):
    name: Literal["python"] = BENCHMARK_RUNTIME_NAME
    version: Literal["3.13.9"] = BENCHMARK_RUNTIME_VERSION
    template_id: str = Field(default="descriptive-statistics-v1", alias="templateId")

    @field_validator("template_id")
    @classmethod
    def validate_template_id(cls, value: str) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("runtime templateId must be a bounded identifier.")
        return value


class ResourceLimits(_ExecutionModel):
    wall_clock_seconds: int = Field(default=5, ge=1, le=5, alias="wallClockSeconds")
    cpu_count: int = Field(default=1, ge=1, le=1, alias="cpuCount")
    memory_bytes: int = Field(default=128 * 1024 * 1024, ge=1024 * 1024, le=128 * 1024 * 1024, alias="memoryBytes")
    pids: int = Field(default=32, ge=1, le=32)
    stdout_bytes: int = Field(default=1024 * 1024, ge=1024, le=1024 * 1024, alias="stdoutBytes")
    tmpfs_bytes: int = Field(default=16 * 1024 * 1024, ge=1024 * 1024, le=16 * 1024 * 1024, alias="tmpfsBytes")
    input_bytes: int = Field(default=1024 * 1024, ge=1, le=1024 * 1024, alias="inputBytes")


class ExpectedOutput(_ExecutionModel):
    name: str = "statistics"
    format: Literal["json"] = "json"
    media_type: Literal["application/json"] = Field(default="application/json", alias="mediaType")
    max_bytes: int = Field(default=1024 * 1024, ge=1, le=1024 * 1024, alias="maxBytes")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("expectedOutputs name must be a bounded identifier.")
        return value


class ExecutionApproval(_ExecutionModel):
    decision: Literal["pending", "approved", "rejected"] = "pending"
    approved_by: Optional[str] = Field(default=None, alias="approvedBy", max_length=128)
    approved_at: Optional[str] = Field(default=None, alias="approvedAt", max_length=40)
    approved_task_digest: Optional[str] = Field(default=None, alias="approvedTaskDigest")

    @field_validator("approved_by")
    @classmethod
    def validate_approved_by(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("approvedBy must be a bounded opaque identifier.")
        return value

    @model_validator(mode="after")
    def validate_decision_fields(self) -> "ExecutionApproval":
        bound = (self.approved_by, self.approved_at, self.approved_task_digest)
        if self.decision == "approved":
            if not all(bound) or not SHA256_PATTERN.fullmatch(self.approved_task_digest or ""):
                raise ValueError("approved approval requires approvedBy, approvedAt and approvedTaskDigest.")
        elif any(value is not None for value in bound):
            raise ValueError("non-approved approval cannot retain approval binding fields.")
        return self


class AuditSummary(_ExecutionModel):
    created_at: str = Field(default="", alias="createdAt", max_length=40)
    updated_at: str = Field(default="", alias="updatedAt", max_length=40)
    event: Literal["code_execution_job_created"] = "code_execution_job_created"
    warnings: List[str] = Field(default_factory=list, max_length=20)

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, values: List[str]) -> List[str]:
        if any(not value or len(value) > 500 for value in values):
            raise ValueError("warnings must contain non-empty strings of at most 500 characters.")
        return values


class CodeExecutionJob(_ExecutionModel):
    schema_version: Literal["1.0"] = Field(default=SCHEMA_VERSION, alias="schemaVersion")
    job_id: str = Field(alias="jobId")
    status: Literal[
        "draft",
        "awaiting_approval",
        "approved",
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    ] = "awaiting_approval"
    input_artifacts: List[InputArtifact] = Field(alias="inputArtifacts", min_length=1, max_length=1)
    script_text: str = Field(alias="scriptText", min_length=1, max_length=256 * 1024)
    script_digest: str = Field(alias="scriptDigest")
    runtime: RuntimeSpec = Field(default_factory=RuntimeSpec)
    image: Literal[WORKER_IMAGE_DIGEST] = WORKER_IMAGE_DIGEST
    limits: ResourceLimits = Field(default_factory=ResourceLimits)
    network_policy: Literal["none"] = Field(default="none", alias="networkPolicy")
    expected_outputs: List[ExpectedOutput] = Field(
        default_factory=lambda: [ExpectedOutput()], alias="expectedOutputs", min_length=1, max_length=1
    )
    approval: ExecutionApproval = Field(default_factory=ExecutionApproval)
    audit_summary: AuditSummary = Field(default_factory=AuditSummary, alias="auditSummary")
    task_digest: str = Field(default="", alias="taskDigest")

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, value: str) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("jobId must be a bounded opaque identifier.")
        return value

    @model_validator(mode="after")
    def validate_digests_and_approval(self) -> "CodeExecutionJob":
        script_digest = hashlib.sha256(self.script_text.encode("utf-8")).hexdigest()
        if self.script_digest != script_digest:
            raise ValueError("scriptDigest does not match scriptText.")
        calculated = _canonical_digest(self.approval_payload())
        if self.task_digest and self.task_digest != calculated:
            raise ValueError("taskDigest does not match the execution description.")
        object.__setattr__(self, "task_digest", calculated)
        if self.approval.decision == "approved":
            if self.approval.approved_task_digest != calculated:
                raise ValueError("approval does not match taskDigest.")
            if self.status not in {"approved", "queued", "running", "succeeded", "failed", "cancelled"}:
                raise ValueError("approved approval requires an approved execution status.")
        elif self.status == "approved":
            raise ValueError("approved job status requires approved approval.")
        return self

    def approval_payload(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "jobId": self.job_id,
            "inputArtifacts": [item.model_dump(mode="json", by_alias=True) for item in self.input_artifacts],
            "scriptDigest": self.script_digest,
            "runtime": self.runtime.model_dump(mode="json", by_alias=True),
            "image": self.image,
            "limits": self.limits.model_dump(mode="json", by_alias=True),
            "networkPolicy": self.network_policy,
            "expectedOutputs": [item.model_dump(mode="json", by_alias=True) for item in self.expected_outputs],
        }


def create_code_execution_job(
    *,
    job_id: str,
    artifact_id: str,
    artifact_digest: str,
    script_text: str,
    media_type: str = "text/csv",
    artifact_size_bytes: int = 1,
    runtime_name: str = BENCHMARK_RUNTIME_NAME,
    runtime_version: str = BENCHMARK_RUNTIME_VERSION,
    image: str = WORKER_IMAGE_DIGEST,
    network_policy: str = "none",
    limits: Optional[Dict[str, Any]] = None,
    expected_output_format: str = "json",
) -> CodeExecutionJob:
    script_digest = hashlib.sha256(script_text.encode("utf-8")).hexdigest()
    return CodeExecutionJob.model_validate({
        "jobId": job_id,
        "status": "awaiting_approval",
        "inputArtifacts": [{
            "artifactId": artifact_id,
            "digest": artifact_digest,
            "mediaType": media_type,
            "sizeBytes": artifact_size_bytes,
        }],
        "scriptText": script_text,
        "scriptDigest": script_digest,
        "runtime": {"name": runtime_name, "version": runtime_version},
        "image": image,
        "limits": limits or {},
        "networkPolicy": network_policy,
        "expectedOutputs": [{"format": expected_output_format}],
    })


def approve_code_execution_job(
    job: CodeExecutionJob,
    *,
    approved_by: str,
    approved_at: str,
) -> CodeExecutionJob:
    if job.status != "awaiting_approval" or job.approval.decision != "pending":
        raise ValueError("Only a pending awaiting_approval job can be approved.")
    snapshot = job.model_dump(mode="json", by_alias=True)
    snapshot["status"] = "approved"
    snapshot["approval"] = {
        "decision": "approved",
        "approvedBy": approved_by,
        "approvedAt": approved_at,
        "approvedTaskDigest": job.task_digest,
    }
    return CodeExecutionJob.model_validate(snapshot)


def update_code_execution_job(job: CodeExecutionJob, changes: Dict[str, Any]) -> CodeExecutionJob:
    snapshot = job.model_dump(mode="json", by_alias=True)
    _deep_update(snapshot, deepcopy(changes))
    if "scriptText" in changes and "scriptDigest" not in changes:
        snapshot["scriptDigest"] = hashlib.sha256(snapshot["scriptText"].encode("utf-8")).hexdigest()
    snapshot.pop("taskDigest", None)
    snapshot["status"] = "awaiting_approval"
    snapshot["approval"] = {"decision": "pending"}
    candidate = CodeExecutionJob.model_validate(snapshot)
    if candidate.task_digest != job.task_digest:
        return candidate
    snapshot["status"] = job.status
    snapshot["approval"] = job.approval.model_dump(mode="json", by_alias=True)
    snapshot["taskDigest"] = job.task_digest
    return CodeExecutionJob.model_validate(snapshot)


def transition_code_execution_job(job: CodeExecutionJob, status: str) -> CodeExecutionJob:
    allowed = {
        "approved": {"queued", "running", "cancelled"},
        "queued": {"running", "cancelled"},
        "running": {"succeeded", "failed", "cancelled"},
    }
    if status not in allowed.get(job.status, set()):
        raise ValueError(f"Invalid code execution status transition: {job.status} -> {status}.")
    snapshot = job.model_dump(mode="json", by_alias=True)
    snapshot["status"] = status
    return CodeExecutionJob.model_validate(snapshot)


def _deep_update(target: Dict[str, Any], changes: Dict[str, Any]) -> None:
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _canonical_digest(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
