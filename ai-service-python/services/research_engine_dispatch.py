"""Route a research run by its persisted engine, independently of rollout policy.

Disabling new v2 runs never hands an existing v2 run to the legacy executor.
The application supplies the durable facade and lookup at startup; imports do
not create databases, workers, or model clients.
"""
from __future__ import annotations

from typing import Any, Callable

from services.deep_research.contracts import (
    DeepResearchError, ENGINE_VERSION, RunNotFoundError,
)


class ResearchEngineDispatcher:
    def __init__(self, *, legacy=None, facade=None, lookup: Callable | None = None,
                 allow_new: Callable[[], bool] = lambda: False):
        if legacy is None:
            from services import research_task_service
            legacy = research_task_service
        self.legacy = legacy
        self.facade = facade
        self.lookup = lookup or (lambda _id: None)
        self.allow_new = allow_new

    def _is_v2(self, run_id: str) -> bool:
        record = self.lookup(run_id)
        if record is not None:
            if record.get("engineVersion") != ENGINE_VERSION:
                raise DeepResearchError("unsupported_engine", "运行使用了不支持的研究引擎")
            if self.facade is None:
                raise DeepResearchError("engine_unavailable", "新版研究服务暂未就绪", {"status_code": 503})
            return True
        # Prefix is only a missing-record guard, never the engine authority.
        if run_id.startswith("dr_run_"):
            raise RunNotFoundError(run_id)
        return False

    def create(self, request: dict[str, Any]):
        engine = request.get("engineVersion")
        if engine is None or engine == "legacy":
            from schemas.requests import ResearchTaskCreateRequest
            return self.legacy.create_research_task(ResearchTaskCreateRequest.model_validate(request))
        if engine != ENGINE_VERSION or request.get("contractVersion") != 2:
            raise DeepResearchError("unsupported_engine", "研究引擎或契约版本无效")
        if self.facade is None or not self.allow_new():
            raise DeepResearchError("engine_unavailable", "新版研究入口尚未启用", {"status_code": 503})
        record, _ = self.facade.create(request, start_async=not bool(request.get("deferStart")))
        return {"status": "success", "task": self.facade.get(record["runId"])}

    def get(self, run_id: str):
        if self._is_v2(run_id):
            return {"status": "success", "task": self.facade.get(run_id)}
        return self.legacy.get_research_task(run_id)

    def action(self, run_id: str, name: str, payload: dict | None = None):
        if self._is_v2(run_id):
            result = self.facade.action(run_id, name, payload or {})
            # A continuation returns the child identity; the parent stays intact.
            return {"status": "success", "task": result}
        if name not in {"resume", "cancel"}:
            raise DeepResearchError("unsupported_action", "此操作仅适用于新版研究")
        return getattr(self.legacy, name + "_research_task")(run_id)

    def detail(self, run_id: str, name: str):
        if not self._is_v2(run_id):
            raise DeepResearchError("unsupported_action", "此视图仅适用于新版研究")
        return {"status": "success", name: getattr(self.facade, "get_" + name)(run_id)}


_dispatcher: ResearchEngineDispatcher | None = None


def configure_dispatcher(dispatcher: ResearchEngineDispatcher | None):
    """Called by application lifecycle, or explicitly injected in tests."""
    global _dispatcher
    _dispatcher = dispatcher


def get_dispatcher() -> ResearchEngineDispatcher:
    if _dispatcher is not None:
        return _dispatcher
    # Legacy availability does not depend on optional LangGraph installation.
    return ResearchEngineDispatcher()
