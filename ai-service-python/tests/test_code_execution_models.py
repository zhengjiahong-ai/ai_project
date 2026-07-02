import hashlib
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from services.code_execution_models import (
    BENCHMARK_IMAGE_DIGEST,
    CodeExecutionJob,
    approve_code_execution_job,
    create_code_execution_job,
    update_code_execution_job,
)


SCRIPT = "print('fixed descriptive statistics template')\n"
SCRIPT_DIGEST = hashlib.sha256(SCRIPT.encode("utf-8")).hexdigest()


def _job(**overrides):
    values = {
        "job_id": "job-001",
        "artifact_id": "artifact-001",
        "artifact_digest": "a" * 64,
        "script_text": SCRIPT,
    }
    values.update(overrides)
    return create_code_execution_job(**values)


def test_valid_job_has_stable_camel_case_snapshot_and_round_trips():
    job = _job()

    snapshot = job.model_dump(mode="json", by_alias=True)
    restored = CodeExecutionJob.model_validate(snapshot)

    assert snapshot["schemaVersion"] == "1.0"
    assert snapshot["jobId"] == "job-001"
    assert snapshot["status"] == "awaiting_approval"
    assert snapshot["scriptText"] == SCRIPT
    assert snapshot["scriptDigest"] == SCRIPT_DIGEST
    assert snapshot["image"] == BENCHMARK_IMAGE_DIGEST
    assert snapshot["networkPolicy"] == "none"
    assert restored == job
    assert restored.task_digest == job.task_digest


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"artifact_id": "../secret.csv"}, "artifactId"),
        ({"artifact_digest": "not-a-digest"}, "digest"),
        ({"media_type": "application/json"}, "mediaType"),
        ({"runtime_name": "node"}, "runtime"),
        ({"runtime_version": "latest"}, "runtime"),
        ({"image": "python:latest"}, "image"),
        ({"network_policy": "bridge"}, "networkPolicy"),
        ({"limits": {"wallClockSeconds": 6}}, "limits"),
        ({"expected_output_format": "csv"}, "expectedOutputs"),
    ],
)
def test_rejects_execution_configuration_outside_benchmark_boundary(overrides, message):
    with pytest.raises((ValidationError, ValueError), match=message):
        _job(**overrides)


def test_task_digest_is_deterministic_and_independent_of_mapping_order():
    first = _job()
    snapshot = first.model_dump(mode="json", by_alias=True)
    reordered = {key: snapshot[key] for key in reversed(snapshot)}

    second = CodeExecutionJob.model_validate(reordered)

    assert second.task_digest == first.task_digest
    assert json.dumps(first.approval_payload(), sort_keys=True) == json.dumps(
        second.approval_payload(), sort_keys=True
    )


def test_script_text_and_digest_are_separate_and_mismatch_is_rejected():
    job = _job()
    snapshot = job.model_dump(mode="json", by_alias=True)
    snapshot["scriptDigest"] = "b" * 64

    assert job.script_text == SCRIPT
    assert job.script_digest == SCRIPT_DIGEST
    with pytest.raises(ValidationError, match="scriptDigest"):
        CodeExecutionJob.model_validate(snapshot)


@pytest.mark.parametrize(
    "changes",
    [
        {"scriptText": "print('changed template')\n"},
        {"inputArtifacts": [{"artifactId": "artifact-002", "digest": "b" * 64, "mediaType": "text/csv", "sizeBytes": 10}]},
        {"runtime": {"name": "python", "version": "3.13.9", "templateId": "descriptive-statistics-v2"}},
        {"limits": {"wallClockSeconds": 4}},
        {"expectedOutputs": [{"name": "statistics-v2", "format": "json", "mediaType": "application/json", "maxBytes": 1048576}]},
    ],
)
def test_execution_description_change_invalidates_approval(changes):
    approved = approve_code_execution_job(
        _job(), approved_by="user-001", approved_at="2026-07-02T10:00:00Z"
    )

    updated = update_code_execution_job(approved, changes)

    assert updated.status == "awaiting_approval"
    assert updated.approval.decision == "pending"
    assert updated.approval.approved_by is None
    assert updated.approval.approved_at is None
    assert updated.approval.approved_task_digest is None
    assert updated.task_digest != approved.task_digest


def test_non_execution_metadata_does_not_change_task_digest_or_forge_approval():
    approved = approve_code_execution_job(
        _job(), approved_by="user-001", approved_at="2026-07-02T10:00:00Z"
    )
    snapshot = approved.model_dump(mode="json", by_alias=True)
    snapshot["status"] = "approved"
    snapshot["auditSummary"] = {
        **snapshot["auditSummary"],
        "updatedAt": "2026-07-02T11:00:00Z",
        "warnings": ["bounded warning"],
    }

    restored = CodeExecutionJob.model_validate(snapshot)

    assert restored.task_digest == approved.task_digest
    assert restored.approval.approved_task_digest == approved.task_digest


def test_update_preserves_approval_when_only_audit_metadata_changes():
    approved = approve_code_execution_job(
        _job(), approved_by="user-001", approved_at="2026-07-02T10:00:00Z"
    )

    updated = update_code_execution_job(
        approved,
        {"auditSummary": {"updatedAt": "2026-07-02T11:00:00Z", "warnings": ["bounded warning"]}},
    )

    assert updated.status == "approved"
    assert updated.task_digest == approved.task_digest
    assert updated.approval == approved.approval


def test_audit_summary_is_bounded_and_rejects_sensitive_or_raw_content():
    job = _job()
    serialized = json.dumps(job.audit_summary.model_dump(by_alias=True))

    assert SCRIPT not in serialized
    assert "artifact-001" not in serialized
    snapshot = job.model_dump(mode="json", by_alias=True)
    snapshot["auditSummary"]["warnings"] = ["x" * 501]
    with pytest.raises(ValidationError, match="warnings"):
        CodeExecutionJob.model_validate(snapshot)
