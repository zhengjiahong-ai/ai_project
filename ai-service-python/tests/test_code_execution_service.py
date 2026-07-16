import hashlib

import pytest

from code_worker.models import WorkerCleanup, WorkerOutput, WorkerResult
from services import code_execution_service


CSV = b"group,value\nA,1\nB,2\n"


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_EXECUTION_DB_PATH", str(tmp_path / "jobs.sqlite3"))
    monkeypatch.setenv("CODE_EXECUTION_ARTIFACT_DIR", str(tmp_path / "artifacts"))


def test_stage_artifact_generates_opaque_id_and_revalidates_content():
    artifact = code_execution_service.stage_csv_artifact("study.csv", CSV)

    assert artifact["artifactId"].startswith("artifact-")
    assert artifact["digest"] == hashlib.sha256(CSV).hexdigest()
    assert code_execution_service.resolve_artifact(artifact["artifactId"]).read_bytes() == CSV


@pytest.mark.parametrize(
    ("filename", "content"),
    [("study.txt", CSV), ("study.csv", b""), ("study.csv", b"\xff\xfe"), ("study.csv", b"x" * (1024 * 1024 + 1))],
    ids=["extension", "empty", "encoding", "oversize"],
)
def test_stage_artifact_rejects_unsupported_input(filename, content):
    with pytest.raises(ValueError):
        code_execution_service.stage_csv_artifact(filename, content)


def test_resolve_artifact_rejects_tampering():
    artifact = code_execution_service.stage_csv_artifact("study.csv", CSV)
    path = code_execution_service.resolve_artifact(artifact["artifactId"])
    path.write_bytes(b"changed")

    with pytest.raises(code_execution_service.ArtifactIntegrityError):
        code_execution_service.resolve_artifact(artifact["artifactId"])


def test_execution_and_publication_reviews_enforce_current_digests():
    artifact = code_execution_service.stage_csv_artifact("study.csv", CSV)
    job = code_execution_service.create_job(artifact["artifactId"])["job"]

    with pytest.raises(code_execution_service.ReviewConflictError):
        code_execution_service.review_execution(job["jobId"], "approved", "0" * 64)

    def runner(_job, _path):
        return WorkerResult(
            status="succeeded",
            reasonCode="completed",
            exitCode=0,
            outputs=[WorkerOutput(name="statistics", mediaType="application/json", sizeBytes=42, digest="b" * 64)],
            cleanup=WorkerCleanup(status="passed", stage="completed", residualCount=0),
        )

    completed = code_execution_service.review_execution(
        job["jobId"], "approved", job["taskDigest"], runner=runner
    )["job"]
    assert completed["status"] == "succeeded"
    assert completed["publishable"] is False

    published = code_execution_service.review_publication(
        job["jobId"], "approved", completed["publicationDigest"]
    )["job"]
    assert published["publishable"] is True


def test_failed_execution_cannot_enter_publication_review():
    artifact = code_execution_service.stage_csv_artifact("study.csv", CSV)
    job = code_execution_service.create_job(artifact["artifactId"])["job"]

    failed = code_execution_service.review_execution(
        job["jobId"],
        "approved",
        job["taskDigest"],
        runner=lambda *_: WorkerResult(status="failed", reasonCode="timeout", outputs=[]),
    )["job"]

    with pytest.raises(ValueError, match="successful"):
        code_execution_service.review_publication(
            job["jobId"], "approved", failed["publicationDigest"]
        )
