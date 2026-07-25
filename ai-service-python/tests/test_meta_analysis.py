"""Tests for services/meta_analysis.py"""
from services.meta_analysis import (
    _eggers_test,
    _error,
    _grade_assessment,
    _parse_studies,
    _safe_float,
    meta_analyze,
)

STUDY = {"n": 100, "effect_size": 0.5, "se": 0.2, "variance": 0.04}


def test_safe_float_valid_and_invalid():
    assert _safe_float(3.14) == 3.14
    assert _safe_float("2.5") == 2.5
    assert _safe_float("abc") is None
    assert _safe_float(None) is None


def test_parse_studies_keeps_valid():
    parsed = _parse_studies([STUDY])
    assert len(parsed) == 1
    assert parsed[0]["effectSize"] == 0.5


def test_meta_analyze_empty_returns_error():
    result = meta_analyze([])
    assert result["status"] == "error"
    assert result["studyCount"] == 0


def test_meta_analyze_single_study_returns_error():
    result = meta_analyze([STUDY])
    assert result["status"] == "error"  # single study → error
    assert "summary" in result
    assert "heterogeneity" in result


def test_meta_analyze_multiple_studies():
    studies = [
        {"n": 100, "effect_size": 0.2, "se": 0.1, "variance": 0.01},
        {"n": 80, "effect_size": 0.4, "se": 0.15, "variance": 0.0225},
        {"n": 120, "effect_size": 0.3, "se": 0.12, "variance": 0.0144},
    ]
    result = meta_analyze(studies)
    assert result["status"] == "success"
    assert result["studyCount"] == 3
    assert "forestPlot" in result


def test_eggers_test_returns_intercept():
    s = {"effectSize": 0.5, "n": 100, "se": 0.2, "variance": 0.04, "weight": 25.0, "label": "S1", "yi": 0.5}
    result = _eggers_test([s, s, s, s, s])
    assert "intercept" in result
    assert "pValue" in result


def test_grade_assessment():
    result = _grade_assessment([STUDY], i_squared=30.0, n=1)
    assert "grade" in result


def test_error_returns_structured():
    result = _error("something went wrong")
    assert result["status"] == "error"
    assert result["error"] == "something went wrong"
