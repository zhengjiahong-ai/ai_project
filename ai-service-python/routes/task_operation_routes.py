from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.task_operation_service import OperationConflict, OperationNotFound, get_operation_store

router = APIRouter()


class OperationRequest(BaseModel):
    taskId: str = Field(min_length=1, max_length=255)
    requestId: str = Field(min_length=1, max_length=128)
    kind: Literal["learning.start", "learning.action", "research.start", "conversation.execute"]
    input: dict[str, Any]


@router.post("/task-operations")
def submit(request: OperationRequest):
    try:
        return get_operation_store().submit(request.taskId, request.requestId, request.kind, request.input)
    except OperationConflict as error:
        return JSONResponse({"message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"message": str(error)}, status_code=422)


@router.get("/task-operations/{task_id}")
def list_operations(task_id: str):
    return get_operation_store().list(task_id)


@router.post("/task-operations/cancel-before-start")
def cancel_before_start(request: OperationRequest):
    try:
        return get_operation_store().submit(request.taskId, request.requestId, request.kind, request.input, cancelled=True)
    except OperationConflict as error:
        return JSONResponse({"message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"message": str(error)}, status_code=422)


@router.get("/task-operations/{task_id}/{request_id}")
def get_operation(task_id: str, request_id: str):
    try:
        return get_operation_store().get(task_id, request_id)
    except OperationNotFound:
        return JSONResponse({"message": "请求不存在"}, status_code=404)


@router.post("/task-operations/{task_id}/{request_id}/cancel")
def cancel_operation(task_id: str, request_id: str):
    try:
        return get_operation_store().cancel(task_id, request_id)
    except OperationNotFound:
        return JSONResponse({"message": "请求不存在"}, status_code=404)
