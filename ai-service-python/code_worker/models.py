from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _WorkerModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class WorkerOutput(_WorkerModel):
    name: Literal["statistics"] = "statistics"
    media_type: Literal["application/json"] = Field(default="application/json", alias="mediaType")
    size_bytes: int = Field(alias="sizeBytes", ge=1, le=1024 * 1024)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class WorkerCleanup(_WorkerModel):
    status: Literal["passed", "failed"] = "passed"
    stage: Literal["not_started", "container", "temporary_directory", "completed"] = "not_started"
    residual_count: int = Field(default=0, alias="residualCount", ge=0, le=1000)


class WorkerResult(_WorkerModel):
    status: Literal["succeeded", "failed", "cancelled"]
    reason_code: str = Field(alias="reasonCode", pattern=r"^[a-z][a-z0-9_]{0,63}$")
    exit_code: Optional[int] = Field(default=None, alias="exitCode")
    outputs: List[WorkerOutput] = Field(default_factory=list, max_length=1)
    cleanup: WorkerCleanup = Field(default_factory=WorkerCleanup)


def failed(reason_code: str, exit_code: Optional[int] = None) -> WorkerResult:
    return WorkerResult(status="failed", reasonCode=reason_code, exitCode=exit_code, outputs=[])
