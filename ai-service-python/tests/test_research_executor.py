"""Tests for services/research_executor.py (pure-logic functions only)."""
from services.research_executor import (
    build_finding_summary,
    build_retry_query,
    coerce_float,
    coerce_int,
    merge_evidence_lists,
    normalize_judge_score,
    should_retry,
    should_try_library,
    slugify,
)


def test_merge_evidence_lists_combines():
    a = [{"sourceId": "s1", "text": "x"}]
    b = [{"sourceId": "s2", "text": "y"}]
    merged = merge_evidence_lists(a, b)
    assert len(merged) == 2


def test_merge_evidence_lists_respects_limit():
    groups = [{"sourceId": f"s{i}", "text": "t"} for i in range(10)]
    result = merge_evidence_lists(groups, limit=3)
    assert len(result) == 3


def test_build_retry_query_includes_missing_aspects():
    q = build_retry_query("Q?", {}, {"missingAspects": ["gap"], "verdict": "INCORRECT"})
    assert "gap" in q


def test_build_finding_summary():
    evidence = [{"sourceId": "s1", "text": "important result"}]
    judge = {"verdict": "CORRECT", "confidence": 0.9}
    summary = build_finding_summary("test Q", evidence, judge)
    assert "test Q" in summary


def test_should_try_library_when_suggested():
    assert should_try_library({"missingAspects": ["need more"], "verdict": "INCORRECT"}) is True


def test_should_retry():
    assert should_retry({"verdict": "INCORRECT", "shouldRetry": True}) is True
    assert should_retry({"verdict": "CORRECT", "shouldRetry": False}) is False


def test_normalize_judge_score():
    assert normalize_judge_score(50) == 50
    assert normalize_judge_score(None) == 0


def test_coerce_int_and_float():
    assert coerce_int(5) == 5
    assert coerce_int(None) == 0
    assert coerce_int("x", -1) == -1
    assert coerce_float(3.5) == 3.5
    assert coerce_float("abc") == 0.0


def test_slugify():
    assert slugify("Hello World") == "hello-world"
    assert slugify(None) == "source"
