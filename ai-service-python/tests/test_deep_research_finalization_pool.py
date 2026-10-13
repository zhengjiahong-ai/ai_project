"""Tests for services.deep_research.finalization_pool.select_reservation_pool."""

from __future__ import annotations

import copy

import pytest

from services.deep_research.finalization_pool import select_reservation_pool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _budget(**overrides):
    """Return a minimal valid budget dict; override any field via kwargs."""
    base = {
        "modelCalls": 5,
        "reservedModelCalls": 10,
        "normalTokens": 100,
        "tokens": 200,
        "maxModelCalls": 30,
        "reserveModelCalls": 10,
        "maxTokens": 500,
        "reserveTokens": 100,
    }
    base.update(overrides)
    return base


def _delta(model_calls: int = 1, tokens: int = 10):
    return {"modelCalls": model_calls, "tokens": tokens}


NODE = "synthesize"

# ---------------------------------------------------------------------------
# 1. Available reserve retained – reserve has room, returns True.
# ---------------------------------------------------------------------------

class TestAvailableReserveRetained:
    def test_reserve_has_room(self):
        budget = _budget(reservedModelCalls=5)  # 5+1 <= 10
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_reserve_exactly_full_but_not_exceeded(self):
        # reservedModelCalls + delta == reserveModelCalls → still fits
        budget = _budget(reservedModelCalls=9)  # 9+1 == 10
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

# ---------------------------------------------------------------------------
# 2. Exhausted reserve uses spare normal – fallback to False.
# ---------------------------------------------------------------------------

class TestExhaustedReserveFallback:
    def test_fallback_to_normal(self):
        budget = _budget(reservedModelCalls=10)  # 10+1 > 10 → exhausted
        assert select_reservation_pool(budget, _delta(), True, NODE) is False

    @pytest.mark.parametrize(
        "node",
        [
            "synthesize",
            "verify",
            "verify_repair",
            "verify_design_config",
            "verify_design_science",
            "verify_repair_design_science",
            "verify_answer_coverage",
        ],
    )
    def test_all_finalization_nodes_eligible(self, node):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(), True, node) is False

# ---------------------------------------------------------------------------
# 3. Full normal denies fallback – normal pool has no room.
# ---------------------------------------------------------------------------

class TestFullNormalDeniesFallback:
    def test_normal_model_calls_full(self):
        # normal capacity = maxModelCalls - reserveModelCalls = 30-10 = 20
        # modelCalls=20, delta=1 → 21 > 20
        budget = _budget(reservedModelCalls=10, modelCalls=20)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

# ---------------------------------------------------------------------------
# 4. Total calls limit blocks fallback.
# ---------------------------------------------------------------------------

class TestTotalCallsLimit:
    def test_combined_exceeds_max(self):
        # modelCalls + reservedModelCalls + delta > maxModelCalls
        # 5 + 10 + 20 > 30
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(model_calls=20), True, NODE) is True

# ---------------------------------------------------------------------------
# 5. Normal tokens limit blocks fallback.
# ---------------------------------------------------------------------------

class TestNormalTokensLimit:
    def test_normal_tokens_exceeded(self):
        # normalTokens + delta.tokens > maxTokens - reserveTokens
        # 100 + 410 > 500 - 100 → 510 > 400
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(tokens=410), True, NODE) is True

# ---------------------------------------------------------------------------
# 6. Total tokens limit blocks fallback.
# ---------------------------------------------------------------------------

class TestTotalTokensLimit:
    def test_total_tokens_exceeded(self):
        # tokens + delta.tokens > maxTokens → 200 + 310 > 500
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(tokens=310), True, NODE) is True

# ---------------------------------------------------------------------------
# 7. Bad fields / non-hashable node – returns requested_reserve unchanged.
# ---------------------------------------------------------------------------

class TestBadFieldsAndNonHashableNode:
    def test_budget_not_dict(self):
        assert select_reservation_pool("bad", _delta(), True, NODE) is True

    def test_delta_not_dict(self):
        assert select_reservation_pool(_budget(reservedModelCalls=10), [1], True, NODE) is True

    def test_missing_limit_field(self):
        budget = _budget(reservedModelCalls=10)
        del budget["maxModelCalls"]
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_bool_limit_field(self):
        budget = _budget(reservedModelCalls=10, maxModelCalls=True)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_negative_limit_field(self):
        budget = _budget(reservedModelCalls=10, maxTokens=-1)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_bool_used_counter(self):
        budget = _budget(reservedModelCalls=10, modelCalls=True)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_negative_used_counter(self):
        budget = _budget(reservedModelCalls=10, normalTokens=-5)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_bool_delta_model_calls(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, {"modelCalls": True, "tokens": 1}, True, NODE) is True

    def test_bool_delta_tokens(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, {"modelCalls": 1, "tokens": False}, True, NODE) is True

    def test_nonhashable_node_list(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(), True, ["synthesize"]) is True

    def test_nonhashable_node_dict(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(), True, {"n": "verify"}) is True

    def test_zero_max_model_calls(self):
        budget = _budget(reservedModelCalls=10, maxModelCalls=0, reserveModelCalls=0)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_zero_max_tokens(self):
        budget = _budget(reservedModelCalls=10, maxTokens=0, reserveTokens=0)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_reserve_exceeds_max_model_calls(self):
        budget = _budget(reservedModelCalls=10, reserveModelCalls=35, maxModelCalls=30)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

    def test_reserve_exceeds_max_tokens(self):
        budget = _budget(reservedModelCalls=10, reserveTokens=600, maxTokens=500)
        assert select_reservation_pool(budget, _delta(), True, NODE) is True

# ---------------------------------------------------------------------------
# 8. Zero delta – delta.modelCalls must be positive; 0 is invalid.
# ---------------------------------------------------------------------------

class TestZeroDelta:
    def test_zero_model_calls_returns_unchanged(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(model_calls=0), True, NODE) is True

    def test_negative_model_calls_returns_unchanged(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(model_calls=-1), True, NODE) is True

# ---------------------------------------------------------------------------
# 9. Exploration node – not in finalization set, returns unchanged.
# ---------------------------------------------------------------------------

class TestExplorationNode:
    @pytest.mark.parametrize("node", ["explore", "plan", "retrieve", "outline", ""])
    def test_non_finalization_node(self, node):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(), True, node) is True

    def test_none_node(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(), True, None) is True

# ---------------------------------------------------------------------------
# 10. Normal requests (requested_reserve is False) – returned unchanged.
# ---------------------------------------------------------------------------

class TestNormalRequests:
    def test_false_returned_unchanged(self):
        budget = _budget(reservedModelCalls=10)
        assert select_reservation_pool(budget, _delta(), False, NODE) is False

    def test_none_returned_unchanged(self):
        budget = _budget(reservedModelCalls=10)
        result = select_reservation_pool(budget, _delta(), None, NODE)
        assert result is None

# ---------------------------------------------------------------------------
# 11. No mutation – budget and delta are never modified.
# ---------------------------------------------------------------------------

class TestNoMutation:
    def test_budget_and_delta_unchanged_on_fallback(self):
        budget = _budget(reservedModelCalls=10)
        delta = _delta()
        budget_snapshot = copy.deepcopy(budget)
        delta_snapshot = copy.deepcopy(delta)
        result = select_reservation_pool(budget, delta, True, NODE)
        assert result is False
        assert budget == budget_snapshot
        assert delta == delta_snapshot

    def test_budget_and_delta_unchanged_on_no_fallback(self):
        budget = _budget(reservedModelCalls=5)
        delta = _delta()
        budget_snapshot = copy.deepcopy(budget)
        delta_snapshot = copy.deepcopy(delta)
        result = select_reservation_pool(budget, delta, True, NODE)
        assert result is True
        assert budget == budget_snapshot
        assert delta == delta_snapshot

# ---------------------------------------------------------------------------
# 12. Missing optional keys default to 0.
# ---------------------------------------------------------------------------

class TestMissingDefaults:
    def test_missing_used_counters_default_zero(self):
        budget = {
            "maxModelCalls": 30,
            "reserveModelCalls": 10,
            "maxTokens": 500,
            "reserveTokens": 100,
            "reservedModelCalls": 10,  # exhausted
        }
        # modelCalls, normalTokens, tokens all default to 0
        assert select_reservation_pool(budget, _delta(), True, NODE) is False

    def test_missing_delta_tokens_defaults_zero(self):
        budget = _budget(reservedModelCalls=10)
        delta = {"modelCalls": 1}  # no "tokens" key
        assert select_reservation_pool(budget, delta, True, NODE) is False
