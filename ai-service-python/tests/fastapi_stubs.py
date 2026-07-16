"""Shared FastAPI mock stubs for offline testing.

Used by both ``routes/api.py`` (when FastAPI is not installed) and
``test_api_contract_smoke.py`` to avoid duplicating the same mock classes.
"""
from __future__ import annotations

import json
import sys
import types


class UploadFile:
    filename: str = ""

    async def read(self, *_args, **_kwargs) -> bytes:
        return b""


class JSONResponse:
    def __init__(self, content, status_code: int = 200) -> None:
        self.status_code = status_code
        self.body = json.dumps(content, ensure_ascii=False).encode("utf-8")


class _Route:
    def __init__(self, path: str, methods: set) -> None:
        self.path = path
        self.methods = methods


class APIRouter:
    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self.routes: list = []

    def _register(self, path: str, method: str, func):
        self.routes.append(_Route(f"{self.prefix}{path}", {method}))
        return func

    def post(self, path: str):
        return lambda func: self._register(path, "POST", func)

    def get(self, path: str):
        return lambda func: self._register(path, "GET", func)

    def patch(self, path: str):
        return lambda func: self._register(path, "PATCH", func)

    def delete(self, path: str):
        return lambda func: self._register(path, "DELETE", func)


def Body(default=None):
    return default


def File(default=None):
    return default


def install_fastapi_stubs() -> None:
    """Inject stub modules into ``sys.modules`` so that ``import fastapi``
    and ``from fastapi.responses import JSONResponse`` succeed without the
    real packages installed."""
    if "fastapi" not in sys.modules:
        fm = types.ModuleType("fastapi")
        fm.APIRouter = APIRouter
        fm.Body = Body
        fm.File = File
        fm.UploadFile = UploadFile
        sys.modules["fastapi"] = fm

    if "fastapi.responses" not in sys.modules:
        rm = types.ModuleType("fastapi.responses")
        rm.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = rm
