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
    def __init__(self, prefix: str = "", tags: list = None, **kwargs) -> None:
        self.prefix = prefix
        self.tags = tags or []
        self.routes: list = []

    def include_router(self, router, **kwargs) -> None:
        prefix = kwargs.get("prefix", "")
        for route in getattr(router, "routes", []):
            self.routes.append(_Route(f"{self.prefix}{prefix}{route.path}", route.methods))

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

    # Provide a minimal Request stub for routes that reference it in type hints
    if "fastapi" in sys.modules and not hasattr(sys.modules["fastapi"], "Request"):
        class _Request:
            class client:
                host = "127.0.0.1"
            def __init__(self):
                self.client = self.client()
        sys.modules["fastapi"].Request = _Request

    if "pydantic" not in sys.modules:
        pm = types.ModuleType("pydantic")
        class _BaseModel:
            pass
        def _Field(default="", **kwargs):
            return default
        pm.BaseModel = _BaseModel
        pm.Field = _Field
        sys.modules["pydantic"] = pm
