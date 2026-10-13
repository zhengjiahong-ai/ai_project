"""Tests for metric_scope structural grounding and protocol requirements."""

import copy

import pytest

from services.deep_research.metric_scope import (
    _CANONICAL_ORDER,
    grounded_metric_domains,
    metric_protocol_requirements,
)

ALL = ["quality", "speed", "storage"]

Q = "Compare quality, speed, and storage of model X on GPU."


# ── grounded_metric_domains: happy paths ─────────────────────────────


class TestGroundedScope:
    def test_single_domain(self):
        raw = [{"domain": "quality", "requestExcerpt": "quality"}]
        assert grounded_metric_domains(raw, Q) == ["quality"]

    def test_two_domains_canonical_order(self):
        raw = [
            {"domain": "storage", "requestExcerpt": "storage"},
            {"domain": "quality", "requestExcerpt": "quality"},
        ]
        assert grounded_metric_domains(raw, Q) == ["quality", "storage"]

    def test_all_three_canonical_order(self):
        raw = [
            {"domain": "speed", "requestExcerpt": "speed"},
            {"domain": "storage", "requestExcerpt": "storage"},
            {"domain": "quality", "requestExcerpt": "quality"},
        ]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_excerpt_is_exact_substring_not_full_question(self):
        raw = [{"domain": "speed", "requestExcerpt": "speed"}]
        assert grounded_metric_domains(raw, Q) == ["speed"]


# ── grounded_metric_domains: exact-substring, no normalisation ───────


class TestExactSubstring:
    def test_case_mismatch_falls_back(self):
        raw = [{"domain": "quality", "requestExcerpt": "Quality"}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_whitespace_padded_excerpt_falls_back(self):
        raw = [{"domain": "quality", "requestExcerpt": " quality "}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_excerpt_not_in_question_falls_back(self):
        raw = [{"domain": "quality", "requestExcerpt": "latency"}]
        assert grounded_metric_domains(raw, Q) == ALL


# ── grounded_metric_domains: malformed / fallback ────────────────────


class TestGroundedFallbacks:
    def test_raw_none(self):
        assert grounded_metric_domains(None, Q) == ALL

    def test_raw_empty_list(self):
        assert grounded_metric_domains([], Q) == ALL

    def test_raw_not_a_list(self):
        assert grounded_metric_domains("quality", Q) == ALL

    def test_question_none(self):
        raw = [{"domain": "quality", "requestExcerpt": "quality"}]
        assert grounded_metric_domains(raw, None) == ALL

    def test_question_empty_string(self):
        raw = [{"domain": "quality", "requestExcerpt": "quality"}]
        assert grounded_metric_domains(raw, "") == ALL

    def test_question_not_string(self):
        raw = [{"domain": "quality", "requestExcerpt": "quality"}]
        assert grounded_metric_domains(raw, 123) == ALL

    def test_entry_not_a_dict(self):
        assert grounded_metric_domains(["quality"], Q) == ALL

    def test_unknown_domain(self):
        raw = [{"domain": "latency", "requestExcerpt": "latency"}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_duplicate_domain(self):
        raw = [
            {"domain": "quality", "requestExcerpt": "quality"},
            {"domain": "quality", "requestExcerpt": "quality"},
        ]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_missing_domain_key(self):
        raw = [{"requestExcerpt": "quality"}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_missing_excerpt_key(self):
        raw = [{"domain": "quality"}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_blank_excerpt(self):
        raw = [{"domain": "quality", "requestExcerpt": "   "}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_excerpt_not_string(self):
        raw = [{"domain": "quality", "requestExcerpt": 42}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_domain_nonhashable_list(self):
        raw = [{"domain": ["quality"], "requestExcerpt": "quality"}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_domain_nonhashable_dict(self):
        raw = [{"domain": {"a": 1}, "requestExcerpt": "quality"}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_excerpt_nonhashable_list(self):
        raw = [{"domain": "quality", "requestExcerpt": ["quality"]}]
        assert grounded_metric_domains(raw, Q) == ALL

    def test_one_bad_entry_poisons_all(self):
        raw = [
            {"domain": "quality", "requestExcerpt": "quality"},
            {"domain": "bogus", "requestExcerpt": "bogus"},
        ]
        assert grounded_metric_domains(raw, Q) == ALL


# ── no mutation ──────────────────────────────────────────────────────


class TestNoMutation:
    def test_raw_not_mutated(self):
        raw = [
            {"domain": "speed", "requestExcerpt": "speed"},
            {"domain": "quality", "requestExcerpt": "quality"},
        ]
        snapshot = copy.deepcopy(raw)
        grounded_metric_domains(raw, Q)
        assert raw == snapshot

    def test_question_not_mutated(self):
        q = "Compare quality, speed, and storage of model X on GPU."
        raw = [{"domain": "quality", "requestExcerpt": "quality"}]
        grounded_metric_domains(raw, q)
        assert q == "Compare quality, speed, and storage of model X on GPU."


# ── metric_protocol_requirements ─────────────────────────────────────


class TestProtocolRequirements:
    def test_default_all_domains(self):
        result = metric_protocol_requirements()
        assert list(result.keys()) == ALL

    def test_none_defaults_all(self):
        assert list(metric_protocol_requirements(None).keys()) == ALL

    def test_empty_list_defaults_all(self):
        assert list(metric_protocol_requirements([]).keys()) == ALL

    def test_subset_canonical_order(self):
        result = metric_protocol_requirements(["storage", "quality"])
        assert list(result.keys()) == ["quality", "storage"]

    def test_single_domain(self):
        result = metric_protocol_requirements(["speed"])
        assert list(result.keys()) == ["speed"]

    def test_unknown_domain_defaults_all(self):
        assert list(metric_protocol_requirements(["bogus"]).keys()) == ALL

    def test_duplicate_domain_defaults_all(self):
        assert list(metric_protocol_requirements(["quality", "quality"]).keys()) == ALL

    def test_nonhashable_element_defaults_all(self):
        assert list(metric_protocol_requirements([["quality"]]).keys()) == ALL

    def test_not_a_list_defaults_all(self):
        assert list(metric_protocol_requirements("quality").keys()) == ALL

    def test_quality_requirement_mentions_direction_and_aggregation(self):
        text = metric_protocol_requirements(["quality"])["quality"]
        assert "direction" in text
        assert "aggregation" in text

    def test_speed_requirement_mentions_key_fields(self):
        text = metric_protocol_requirements(["speed"])["speed"]
        for kw in ("device", "resolution", "warmup", "synchronization",
                    "timed region", "repetitions"):
            assert kw in text

    def test_storage_requirement_mentions_boundaries_and_units(self):
        text = metric_protocol_requirements(["storage"])["storage"]
        assert "boundaries" in text
        assert "units" in text
