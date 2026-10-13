from datetime import datetime, UTC, timedelta
from unittest.mock import Mock

import pytest

from llm.provider import LLMRequest
from services.deep_research.contracts import DeepResearchError
from services.deep_research.runtime import AuthoritativeScopeValidator, ScopedModelClient, read_acquired_source


def repo():
    value = Mock()
    value.require_run.return_value = {"taskId": "task/中文", "materials": [{"materialId": "p"}],
        "materialSnapshot": {"snapshotHash": "h"}, "budget": {"maxWallClockSeconds": 360},
        "startedAt": (datetime.now(UTC) - timedelta(seconds=350)).isoformat()}
    return value


def test_authoritative_scope_identity_readiness_and_no_redirect():
    store = repo()
    post = Mock()
    post.return_value = Mock(status_code=200, content=b"{}")
    post.return_value.json.return_value = {"valid": True, "snapshotValid": True,
        "taskId": "task/中文", "runId": "run"}
    validate = AuthoritativeScopeValidator(store, post=post)
    assert validate("run", "p")
    args, kwargs = post.call_args
    assert "task%2F%E4%B8%AD%E6%96%87" in args[0]
    assert kwargs == {"json": {"snapshotHash": "h"}, "timeout": 3, "allow_redirects": False}
    post.return_value.json.return_value["runId"] = "foreign"
    assert not validate("run", "p")
    post.return_value.status_code = 302
    assert not validate("run", "p")
    assert not validate("run", "foreign-paper")


def test_scope_failure_prevents_provider_send_and_deadline_caps_request():
    store = repo()
    provider = Mock()
    validate = Mock(return_value=False)
    client = ScopedModelClient(store, validate, lambda: provider).for_run("run")
    with pytest.raises(DeepResearchError, match="材料"):
        client.invoke(LLMRequest(prompt="answer", timeout_seconds=60))
    provider.invoke.assert_not_called()

    validate.return_value = True
    client.invoke(LLMRequest(prompt="answer", timeout_seconds=60))
    request = provider.invoke.call_args.args[0]
    assert 0 < request.timeout_seconds <= 10
    assert request.messages[0]["role"] == "system"
    assert request.extra_body["thinking"] == {"type": "disabled"}
    store.require_run.return_value["startedAt"] = (datetime.now(UTC) - timedelta(seconds=361)).isoformat()
    provider.reset_mock()
    with pytest.raises(DeepResearchError, match="预算"):
        client.invoke(LLMRequest(prompt="answer"))
    provider.invoke.assert_not_called()


def test_authoritative_model_send_checks_whole_snapshot_once_without_caching():
    store, provider, post = repo(), Mock(), Mock()
    store.require_run.return_value['materials'] = [{'materialId': 'p'}, {'materialId': 'q'}]
    post.return_value = Mock(status_code=200, content=b'{}')
    post.return_value.json.return_value = {'valid': True, 'snapshotValid': True,
                                         'taskId': 'task/中文', 'runId': 'run'}
    validate = AuthoritativeScopeValidator(store, post=post)
    client = ScopedModelClient(store, validate, lambda: provider).for_run('run')
    client.invoke(LLMRequest(prompt='first'))
    assert post.call_count == 1 and provider.invoke.call_count == 1
    post.return_value.json.return_value['valid'] = False
    with pytest.raises(DeepResearchError):
        client.invoke(LLMRequest(prompt='revoked'))
    assert post.call_count == 2 and provider.invoke.call_count == 1
    post.reset_mock()
    assert not validate.validate_materials('run', ['foreign'])
    post.assert_not_called()


def test_external_only_model_send_still_checks_live_task_scope():
    store, post = repo(), Mock()
    store.require_run.return_value['materials'] = []
    post.return_value = Mock(status_code=403, content=b'{}')
    provider = Mock()
    client = ScopedModelClient(store, AuthoritativeScopeValidator(store, post=post), lambda: provider).for_run('run')
    with pytest.raises(DeepResearchError):
        client.invoke(LLMRequest(prompt='external'))
    post.assert_called_once()
    provider.invoke.assert_not_called()


def test_reader_returns_persisted_location_and_does_not_fetch():
    store = repo()
    store.require_run.return_value["state"] = {"sources": [{"sourceId": "s", "workId": "p",
        "text": "exact original", "versionId": "v", "contentHash": "h", "accessLevel": "fulltext",
        "location": {"page": 4, "chunk": 2}}]}
    result = read_acquired_source(store, "run", "s")
    assert result["pages"] == [{"text": "exact original", "page": 4, "chunk": 2}]
    assert result["contentHash"] == "h"
    with pytest.raises(DeepResearchError, match="未保存"):
        read_acquired_source(store, "run", "missing")


def test_research_timeout_client_is_isolated_and_still_capped_by_run(monkeypatch):
    from llm.client import DeepSeekLLM
    from services.deep_research.runtime import research_model
    from core.config import settings
    base = DeepSeekLLM(api_key='fixture-key', model='fixture-model')
    monkeypatch.setattr('llm.client.get_structured_llm', lambda: base)
    monkeypatch.setattr(settings, 'deep_research_request_timeout_seconds', 180)
    client = research_model()
    assert client is not base and client.timeout_seconds == 180
    assert base.timeout_seconds is None and client.model == base.model
    store = repo()
    store.require_run.return_value['startedAt'] = (datetime.now(UTC) - timedelta(seconds=210)).isoformat()
    received = []
    monkeypatch.setattr(client, 'invoke', lambda request: received.append(request))
    ScopedModelClient(store, lambda *args: True, lambda: client).for_run('run').invoke(LLMRequest(prompt='research'))
    assert 0 < received[0].timeout_seconds <= 150
    fixture = object()
    monkeypatch.setattr('llm.client.get_structured_llm', lambda: fixture)
    assert research_model() is fixture


def test_reasoning_options_are_reserved_before_provider_send():
    from services.deep_research.runtime import research_model_options
    from services.deep_research.tools import TrackedLLMInvoker
    from llm.provider import LLMResult, LLMUsage
    store, provider = repo(), Mock()
    provider.invoke.return_value = LLMResult(content='[]', provider='fixture', model='fixture', usage=LLMUsage(8, 2, 10))
    reserve = Mock(return_value=({'callId': 'call', 'reservationToken': 'reservation'}, False))
    complete = Mock()
    client = ScopedModelClient(store, lambda *args: True, lambda: provider).for_run('run')
    invoke = TrackedLLMInvoker(client, reserve, complete, request_options=research_model_options)
    invoke('run', 'verify', 'evidence', {'max_tokens': 1000}, use_reserve=True)
    request = provider.invoke.call_args.args[0]
    assert request.extra_body['thinking'] == {'type': 'enabled'}
    assert request.extra_body['max_tokens'] == 16384
    assert request.extra_body['reasoning_effort'] == 'high'
    assert reserve.call_args.kwargs['budget_delta']['tokens'] == len(b'evidence') + 1024 + 16384
    assert research_model_options('extract', {'max_tokens': 1000}) == {'max_tokens': 1000, 'thinking': {'type': 'disabled'}, 'reasoning_effort': 'none'}
    assert research_model_options('synthesize', {})['reasoning_effort'] == 'none'
    assert research_model_options('synthesize', {})['thinking'] == {'type': 'disabled'}
    assert research_model_options('synthesize', {})['max_tokens'] == 16384
    assert research_model_options('repair_claims', {})['reasoning_effort'] == 'none'
    assert research_model_options('repair_claims', {})['thinking'] == {'type': 'disabled'}
    assert research_model_options('repair_claims', {})['max_tokens'] == 8192
    assert research_model_options('verify_repair', {})['reasoning_effort'] == 'high'
    assert research_model_options('verify_repair', {})['max_tokens'] == 8192
    assert research_model_options('verify_design_config', {})['reasoning_effort'] == 'none'
    assert research_model_options('verify_design_config', {})['thinking'] == {'type': 'disabled'}
    assert research_model_options('verify_design_config', {})['max_tokens'] == 6000
    for node in ('verify_design_science', 'verify_repair_design_science'):
        assert research_model_options(node, {})['reasoning_effort'] == 'none'
        assert research_model_options(node, {})['thinking'] == {'type': 'disabled'}
        assert research_model_options(node, {})['max_tokens'] == 6000
        invoke('run', node, 'experiment protocol', {'max_tokens': 1000}, use_reserve=True)
        assert reserve.call_args.kwargs['budget_delta']['tokens'] == len(b'experiment protocol') + 1024 + 6000
    invoke('run', 'synthesize', 'evidence', {'max_tokens': 1000}, use_reserve=True)
    assert reserve.call_args.kwargs['budget_delta']['tokens'] == len(b'evidence') + 1024 + 16384
    assert provider.invoke.call_args.args[0].extra_body['thinking'] == {'type': 'disabled'}


def test_routine_model_route_retains_scope_checks_and_complex_model():
    store, reasoning, routine = repo(), Mock(), Mock()
    validate = Mock(return_value=True)
    client = ScopedModelClient(store, validate, lambda: reasoning, lambda: routine).for_run("run")
    for node in ("resolve_brief", "extract", "assess_relevance"):
        client.for_node(node).invoke(LLMRequest(prompt="public evidence"))
    assert routine.invoke.call_count == 3
    reasoning.invoke.assert_not_called()
    client.for_node("synthesize").invoke(LLMRequest(prompt="reasoning"))
    assert reasoning.invoke.call_count == 1
    validate.return_value = False
    with pytest.raises(DeepResearchError):
        client.for_node("extract").invoke(LLMRequest(prompt="revoked"))
    assert routine.invoke.call_count == 3


def test_disabled_runtime_does_not_create_store(tmp_path, monkeypatch):
    from services.deep_research import runtime
    monkeypatch.setenv("DEEP_RESEARCH_V2_ENABLED", "false")
    target = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("DEEP_RESEARCH_DB_PATH", str(target))
    assert runtime.initialize_runtime() is None
    assert not target.exists()
