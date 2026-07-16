try:
    from fastapi import APIRouter, File, UploadFile
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        File,
        JSONResponse,
        UploadFile,
    )

from schemas.requests import (
    CodeExecutionJobCreateRequest,
    CodeExecutionReviewRequest,
    CodePublicationReviewRequest,
)
from services import code_execution_service

code_execution_router = APIRouter()


@code_execution_router.post("/code-execution-artifacts")
async def upload_code_execution_artifact(file: UploadFile = File(...)):
    try:
        content = await file.read(code_execution_service.MAX_ARTIFACT_BYTES + 1)
        artifact = code_execution_service.stage_csv_artifact(file.filename or "", content)
        return JSONResponse({"status": "success", "artifact": artifact})
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@code_execution_router.post("/code-execution-jobs")
async def create_code_execution_job(request: CodeExecutionJobCreateRequest):
    try:
        return JSONResponse(code_execution_service.create_job(request.artifactId))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@code_execution_router.get("/code-execution-jobs")
async def list_code_execution_jobs():
    return JSONResponse(code_execution_service.list_jobs())


@code_execution_router.get("/code-execution-jobs/{job_id}")
async def get_code_execution_job(job_id: str):
    try:
        return JSONResponse(code_execution_service.get_job(job_id))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)


@code_execution_router.post("/code-execution-jobs/{job_id}/execution-review")
async def review_code_execution(job_id: str, request: CodeExecutionReviewRequest):
    try:
        return JSONResponse(code_execution_service.review_execution(
            job_id, request.decision, request.expectedTaskDigest, request.reason
        ))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except code_execution_service.ReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@code_execution_router.post("/code-execution-jobs/{job_id}/publication-review")
async def review_code_publication(job_id: str, request: CodePublicationReviewRequest):
    try:
        return JSONResponse(code_execution_service.review_publication(
            job_id, request.decision, request.expectedPublicationDigest, request.reason
        ))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except code_execution_service.ReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
