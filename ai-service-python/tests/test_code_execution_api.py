from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.api import router
from services import code_execution_service


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_upload_and_create_job_routes(monkeypatch):
    monkeypatch.setattr(
        code_execution_service,
        "stage_csv_artifact",
        lambda filename, content: {"artifactId": "artifact-1", "filename": filename, "sizeBytes": len(content)},
    )
    monkeypatch.setattr(
        code_execution_service,
        "create_job",
        lambda artifact_id: {"status": "success", "job": {"jobId": "job-1", "artifactId": artifact_id}},
    )

    uploaded = _client().post(
        "/api/code-execution-artifacts", files={"file": ("study.csv", b"a,b\n1,2\n", "text/csv")}
    )
    created = _client().post("/api/code-execution-jobs", json={"artifactId": "artifact-1"})

    assert uploaded.status_code == 200
    assert uploaded.json()["artifact"]["artifactId"] == "artifact-1"
    assert created.status_code == 200
    assert created.json()["job"]["jobId"] == "job-1"


def test_execution_review_maps_stale_digest_to_conflict(monkeypatch):
    def conflict(*_args, **_kwargs):
        raise code_execution_service.ReviewConflictError("stale")

    monkeypatch.setattr(code_execution_service, "review_execution", conflict)

    response = _client().post(
        "/api/code-execution-jobs/job-1/execution-review",
        json={"decision": "approved", "expectedTaskDigest": "a" * 64},
    )

    assert response.status_code == 409
    assert response.json()["status"] == "error"


def test_get_missing_job_returns_not_found(monkeypatch):
    monkeypatch.setattr(
        code_execution_service, "get_job", lambda _job_id: (_ for _ in ()).throw(KeyError("missing"))
    )

    response = _client().get("/api/code-execution-jobs/missing")

    assert response.status_code == 404


def test_publication_review_validates_request_shape():
    response = _client().post(
        "/api/code-execution-jobs/job-1/publication-review",
        json={"decision": "approved", "expectedPublicationDigest": "bad"},
    )

    assert response.status_code == 422
