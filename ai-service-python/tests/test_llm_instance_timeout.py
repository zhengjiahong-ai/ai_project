import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm.deadline as llm_deadline
import services.operation_control as operation_control
from core.config import settings
from llm.client import DeepSeekLLM
from llm.provider import LLMProviderError, LLMRequest

GLOBAL_TIMEOUT_SECONDS = 120.0


class _FakeResponse:
    status_code = 200

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        }


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_timeout_seconds", GLOBAL_TIMEOUT_SECONDS)
    monkeypatch.setattr(operation_control, "check_cancelled", lambda: None)

    deadline_timeouts = []

    def _call_with_deadline(func, timeout):
        deadline_timeouts.append(timeout)
        return func()

    monkeypatch.setattr(llm_deadline, "call_with_deadline", _call_with_deadline)

    with patch("requests.post", return_value=_FakeResponse()) as mock_post:
        yield mock_post, deadline_timeouts


def _invoke(client, request_timeout=None):
    return client.invoke(
        LLMRequest(
            prompt="deep research",
            messages=None,
            stop=None,
            extra_body={},
            timeout_seconds=request_timeout,
        )
    )


def test_default_client_uses_global_timeout_cap(llm_env):
    mock_post, deadline_timeouts = llm_env
    client = DeepSeekLLM(api_key="test-key")

    _invoke(client)

    assert mock_post.call_count == 1
    assert mock_post.call_args.kwargs["timeout"] == GLOBAL_TIMEOUT_SECONDS
    assert deadline_timeouts == [GLOBAL_TIMEOUT_SECONDS]


def test_default_client_still_caps_long_research_request(llm_env):
    mock_post, deadline_timeouts = llm_env
    client = DeepSeekLLM(api_key="test-key")

    _invoke(client, request_timeout=GLOBAL_TIMEOUT_SECONDS + 300)

    assert mock_post.call_args.kwargs["timeout"] == GLOBAL_TIMEOUT_SECONDS


def test_research_client_can_use_timeout_above_global_cap(llm_env):
    mock_post, deadline_timeouts = llm_env
    client = DeepSeekLLM(api_key="test-key", timeout_seconds=180)

    _invoke(client, request_timeout=150)

    assert mock_post.call_args.kwargs["timeout"] == 150.0
    assert deadline_timeouts == [150.0]
    assert "timeout_seconds" not in mock_post.call_args.kwargs["json"]


def test_shorter_request_timeout_wins_over_instance_cap(llm_env):
    mock_post, deadline_timeouts = llm_env
    client = DeepSeekLLM(api_key="test-key", timeout_seconds=180)

    _invoke(client, request_timeout=90)

    assert mock_post.call_args.kwargs["timeout"] == 90.0


def test_instance_cap_still_bounds_longer_request_timeout(llm_env):
    mock_post, deadline_timeouts = llm_env
    client = DeepSeekLLM(api_key="test-key", timeout_seconds=60)

    _invoke(client, request_timeout=300)

    assert mock_post.call_args.kwargs["timeout"] == 60.0


@pytest.mark.parametrize("bad_timeout", [0, -5, float("inf"), float("nan")])
def test_invalid_constructor_timeout_is_rejected_before_network(llm_env, bad_timeout):
    mock_post, deadline_timeouts = llm_env

    with pytest.raises(ValueError):
        DeepSeekLLM(api_key="test-key", timeout_seconds=bad_timeout)

    mock_post.assert_not_called()


@pytest.mark.parametrize("bad_timeout", [0, -1.5, float("inf"), float("nan")])
def test_invalid_request_timeout_is_rejected_before_network(llm_env, bad_timeout):
    mock_post, deadline_timeouts = llm_env
    client = DeepSeekLLM(api_key="test-key")

    with pytest.raises(ValueError):
        _invoke(client, request_timeout=bad_timeout)

    mock_post.assert_not_called()


def test_provider_timeout_is_single_call_and_llm_provider_error(llm_env):
    mock_post, deadline_timeouts = llm_env
    mock_post.side_effect = requests.Timeout("provider timed out")
    client = DeepSeekLLM(api_key="test-key")

    with pytest.raises(LLMProviderError):
        _invoke(client)

    assert mock_post.call_count == 1
    assert deadline_timeouts == [GLOBAL_TIMEOUT_SECONDS]


def test_instance_override_does_not_mutate_default_or_leak_local_options(llm_env):
    mock_post, _ = llm_env
    _invoke(DeepSeekLLM(api_key="test-key", timeout_seconds=180), request_timeout=150)
    default = DeepSeekLLM(api_key="test-key")
    default.invoke(LLMRequest(prompt="ordinary", timeout_seconds=150,
                              extra_body={"timeout_seconds": 999, "max_tokens": 16}))
    assert mock_post.call_args.kwargs['timeout'] == GLOBAL_TIMEOUT_SECONDS
    assert 'timeout_seconds' not in mock_post.call_args.kwargs['json']
    assert mock_post.call_args.kwargs['json']['max_tokens'] == 16
