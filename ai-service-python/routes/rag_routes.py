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

from services import rag_service

rag_router = APIRouter()


@rag_router.post("/rag/add-literature")
async def rag_add_literature(file: UploadFile = File(...), metadata: dict | None = None):
    try:
        return JSONResponse(await rag_service.add_literature(file, metadata))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@rag_router.post("/rag/retrieve")
async def rag_retrieve(query: str, top_k: int = 5, filter_metadata: dict | None = None):
    try:
        return JSONResponse(rag_service.retrieve(query, top_k=top_k, filter_metadata=filter_metadata))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)
