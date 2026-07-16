"""Standardised Pydantic response models for the Pixiu API."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    """Error detail included in an ``ApiResponse`` when ``status == \"error\"``."""

    errorCode: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error message.")


class ApiResponse(BaseModel):
    """Top-level envelope returned by every ``/api`` endpoint.

    Success: ``{\"status\": \"success\", \"data\": ...}``
    Error:   ``{\"status\": \"error\", \"errorCode\": \"...\", \"message\": \"...\"}``
    """

    status: str = Field(..., pattern=r"^(success|error)$")
    data: Optional[Any] = Field(default=None)
    errorCode: Optional[str] = Field(default=None)
    message: Optional[str] = Field(default=None)
