import asyncio
import json
from unittest.mock import Mock

import pytest

from services.deep_research.contracts import DeepResearchError, ENGINE_VERSION, RunNotFoundError
from services.research_engine_dispatch import ResearchEngineDispatcher, configure_dispatcher


@pytest.fixture
def dispatch():
    legacy = Mock()
    facade = Mock()
    records = {"opaque-existing-id": {"engineVersion": ENGINE_VERSION}}
    service = ResearchEngineDispatcher(legacy=legacy, facade=facade, lookup=records.get)
    yield service, legacy, facade, records
    configure_dispatcher(None)


def test_rollback_disables_creation_but_keeps_existing_engine(dispatch):
    service, legacy, facade, _ = dispatch
    with pytest.raises(DeepResearchError, match="尚未启用"):
        service.create({"engineVersion": ENGINE_VERSION, "contractVersion": 2})
    facade.get.return_value = {"runId": "opaque-existing-id", "status": "paused"}
    assert service.get("opaque-existing-id")["task"]["status"] == "paused"
    facade.action.return_value = {"runId": "opaque-existing-id", "status": "running"}
    assert service.action("opaque-existing-id", "resume", {"requestId": "one"})["task"]["status"] == "running"
    legacy.get_research_task.assert_not_called()
    legacy.resume_research_task.assert_not_called()
    facade.create.assert_not_called()


def test_missing_v2_record_never_runs_legacy(dispatch):
    service, legacy, _, _ = dispatch
    with pytest.raises(RunNotFoundError):
        service.get("dr_run_missing")
    legacy.get_research_task.assert_not_called()


def test_unknown_stored_engine_rejected(dispatch):
    service, legacy, _, records = dispatch
    records["future"] = {"engineVersion": "v99"}
    with pytest.raises(DeepResearchError, match="不支持"):
        service.action("future", "resume", {})
    legacy.resume_research_task.assert_not_called()


def test_legacy_request_still_uses_validated_model(dispatch):
    service, legacy, _, _ = dispatch
    legacy.create_research_task.return_value = {"status": "success", "task": {"taskId": "old"}}
    assert service.create({"question": "why", "pdfId": "p"})["task"]["taskId"] == "old"
    assert legacy.create_research_task.call_args.args[0].pdfId == "p"
    service.action("old", "cancel")
    legacy.cancel_research_task.assert_called_once_with("old")


def test_explicit_v2_create_and_child_identity(dispatch):
    service, _, facade, _ = dispatch
    service.allow_new = lambda: True
    facade.create.return_value = ({"runId": "new"}, True)
    facade.get.return_value = {"runId": "new", "taskId": "workspace"}
    assert service.create({"engineVersion": ENGINE_VERSION, "contractVersion": 2})["task"]["runId"] == "new"
    facade.action.return_value = {"runId": "child", "parentRunId": "opaque-existing-id"}
    result = service.action("opaque-existing-id", "continue", {"requestId": "next"})
    assert result["task"]["runId"] == "child"
    assert result["task"]["parentRunId"] == "opaque-existing-id"


def test_get_sources_does_not_generate(dispatch):
    service, _, facade, _ = dispatch
    facade.get_sources.return_value = [{"sourceId": "s"}]
    assert service.detail("opaque-existing-id", "sources")["sources"] == [{"sourceId": "s"}]
    facade.create.assert_not_called()
    facade.action.assert_not_called()


def test_routes_use_same_dispatch_and_error_status(dispatch):
    from routes import research_routes
    service, _, facade, _ = dispatch
    configure_dispatcher(service)
    response = asyncio.run(research_routes.create_research_task({"engineVersion": ENGINE_VERSION, "contractVersion": 2}))
    assert response.status_code == 503
    assert json.loads(response.body)["errorCode"] == "engine_unavailable"
    response = asyncio.run(research_routes.get_research_task("dr_run_absent"))
    assert response.status_code == 404
    facade.action.return_value = {"runId": "opaque-existing-id", "status": "paused"}
    response = asyncio.run(research_routes.pause_research_task("opaque-existing-id", {"requestId": "pause"}))
    assert json.loads(response.body)["task"]["status"] == "paused"
