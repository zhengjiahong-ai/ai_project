"""Tests for services/research_planner.py (pure-logic functions only)."""
from services.research_planner import (
    build_follow_up_plan_item,
    build_initial_plan_items,
    build_initial_plan_items_for_replan,
    clean_text,
    fallback_plan,
    normalize_missing_aspects,
    normalize_sub_questions,
    should_create_follow_up,
)


def test_build_initial_plan_items_empty():
    assert build_initial_plan_items([]) == []


def test_build_initial_plan_items_structured():
    items = build_initial_plan_items([{"question": "Q1", "searchKeywords": ["k"]}])
    assert len(items) == 1


def test_fallback_plan_returns_tuple():
    brief, sub_qs = fallback_plan("test question")
    assert isinstance(brief, str)
    assert len(brief) > 0
    assert isinstance(sub_qs, list)


def test_normalize_sub_questions_falls_back():
    result = normalize_sub_questions(None, fallback=["x", "y"])
    assert isinstance(result, list)


def test_normalize_missing_aspects():
    assert normalize_missing_aspects(None) == []
    assert normalize_missing_aspects(["need more data"]) == ["need more data"]


def test_should_create_follow_up_with_missing_aspects():
    finding = {"verdict": "INCORRECT", "missingAspects": ["gap 1"]}
    assert should_create_follow_up(finding) is True


def test_should_create_follow_up_correct_no_gap():
    finding = {"verdict": "CORRECT", "missingAspects": []}
    assert should_create_follow_up(finding) is False


def test_build_follow_up_plan_item():
    finding = {"missingAspects": ["x"], "subQuestion": "orig"}
    item = build_follow_up_plan_item(finding, 3)
    assert "kind" in item or "question" in item or "index" in item


def test_clean_text():
    assert clean_text("  hello  ") == "hello"
    assert clean_text(None) == ""
    assert clean_text(123) == "123"


def test_build_initial_plan_items_for_replan():
    items = build_initial_plan_items_for_replan([{"question": "a"}, {"question": "b"}], 5)
    assert len(items) == 2
