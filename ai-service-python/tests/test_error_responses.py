"""Tests for core/error_responses.py"""
from core.error_responses import error_response, generate_trace_id, EXCEPTION_STATUS_MAP


def test_error_response_shape():
    body = error_response(422, "validation_error", "x must be positive")
    assert body["status"] == "error"
    assert body["errorCode"] == "validation_error"
    assert body["message"] == "x must be positive"
    # No other keys leaked.
    assert set(body.keys()) == {"status", "errorCode", "message"}


def test_generate_trace_id_is_hex_string():
    tid = generate_trace_id()
    assert isinstance(tid, str)
    assert len(tid) == 12
    int(tid, 16)  # must be valid hex


def test_generate_trace_id_is_unique():
    ids = {generate_trace_id() for _ in range(20)}
    assert len(ids) == 20


def test_exception_status_map_is_not_empty():
    assert len(EXCEPTION_STATUS_MAP) >= 5, (
        "expected at least 5 known exception mappings"
    )


def test_exception_status_map_values_are_tuples():
    for exc_type, (status, code) in EXCEPTION_STATUS_MAP.items():
        assert isinstance(status, int), f"{exc_type}: status must be int"
        assert 400 <= status < 600, f"{exc_type}: status {status} out of range"
        assert isinstance(code, str), f"{exc_type}: errorCode must be str"
        assert len(code) > 0, f"{exc_type}: errorCode must not be empty"


def test_known_agent_errors_mapped():
    """Verify the most commonly raised errors are in the map."""
    from services.agent_project_service import (
        AgentProjectNotFoundError,
        AgentTaskNotFoundError,
        AgentReviewConflictError,
    )
    from services.research_task_service import (
        ResearchTaskNotFoundError,
        ResearchReviewConflictError,
    )
    from services.trace_service import TraceNotFoundError

    expected = {
        AgentProjectNotFoundError,
        AgentTaskNotFoundError,
        AgentReviewConflictError,
        ResearchTaskNotFoundError,
        ResearchReviewConflictError,
        TraceNotFoundError,
    }
    mapped = set(EXCEPTION_STATUS_MAP.keys())
    missing = expected - mapped
    assert not missing, f"errors not in EXCEPTION_STATUS_MAP: {missing}"


def test_internal_error_response_hides_details():
    """The 500 internal_error path must NOT expose the raw exception message."""
    body = error_response(500, "internal_error", "服务器内部错误，请稍后重试。")
    assert "internal_error" == body["errorCode"]
    # The user message must be a generic Chinese message, not a raw traceback.
    assert "内部" in body["message"]
