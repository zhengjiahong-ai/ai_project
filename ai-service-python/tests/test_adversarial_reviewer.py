"""Tests for services/adversarial_reviewer.py."""
from unittest.mock import patch

from services.adversarial_reviewer import (
    _calculate_adjustment,
    _error,
    adversarial_review,
)


def test_error_returns_structured_dict():
    result = _error("test failure")
    assert result["status"] == "error"
    assert result["error"] == "test failure"


def test_calculate_adjustment_with_mixed_counters():
    counters = [
        {"severity": "high", "verdict": "valid"},
        {"severity": "low", "verdict": "invalid"},
        {"verdict": "valid"},
    ]
    adj = _calculate_adjustment(counters, "reviewed")
    assert isinstance(adj, float)
    assert -1.0 <= adj <= 1.0


def test_calculate_adjustment_no_valid_counters():
    assert _calculate_adjustment([], "reviewed") == 0.0


def test_adversarial_review_rule_based_path():
    with patch("services.adversarial_reviewer._llm_review", return_value=[]):
        result = adversarial_review(
            question="test",
            findings=[
                {
                    "summary": "finding A",
                    "confidence": 0.85,
                    "sourceId": "s1",
                    "evidence": "sample",
                }
            ],
        )
    assert result["status"] == "success"
    assert "counterArguments" in result
    assert "adjusted_confidence" in result or "overallConfidence" in result


def test_adversarial_review_with_findings_produces_output():
    with patch("services.adversarial_reviewer._llm_review", return_value=[]):
        result = adversarial_review(
            question="q",
            findings=[{"summary": "test", "confidence": 0.5, "sourceId": "s1"}],
        )
    assert "status" in result
