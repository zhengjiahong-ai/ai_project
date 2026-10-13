"""Tests for services.deep_research.data_availability."""
from __future__ import annotations

import copy
import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), os.pardir)
)

from services.deep_research.data_availability import validate_data_availability


def _base_claim(**overrides: Any) -> Dict[str, Any]:
    claim: Dict[str, Any] = {
        "kind": "proposal",
        "designRole": "data",
        "designContractVersion": 2,
        "executionSpec": {
            "dataset": "clinical_trials_2024",
            "scenes": {"mode": "sorted_first", "count": 3, "order": "desc"},
        },
        "evidenceRefs": ["ev-001"],
    }
    claim.update(overrides)
    return claim


def _base_evidence(**overrides: Any) -> Dict[str, Any]:
    ev: Dict[str, Any] = {
        "evidenceId": "ev-001",
        "quote": "The study included 5 participants in total",
        "accessLevel": "fulltext",
        "workId": "w-1",
        "versionId": "v-1",
    }
    ev.update(overrides)
    return ev


def _base_verdict(**da_overrides: Any) -> Dict[str, Any]:
    da: Dict[str, Any] = {
        "evidenceId": "ev-001",
        "quote": "included 5 participants",
        "scopeQuote": "5 participants",
        "availableCount": 5,
        "countQuote": "5",
        "availableNames": [],
    }
    da.update(da_overrides)
    return {"dataAvailability": da}


# ------------------------------------------------------------------ #
# Applicability / legacy skip
# ------------------------------------------------------------------ #


class TestApplicability:
    def test_non_dict_claim_returns_empty(self):
        assert validate_data_availability("nope", {}, []) == []

    def test_wrong_kind_returns_empty(self):
        assert validate_data_availability(_base_claim(kind="conclusion"), {}, []) == []

    def test_wrong_design_role_returns_empty(self):
        assert validate_data_availability(_base_claim(designRole="methodology"), {}, []) == []

    def test_wrong_contract_version_returns_empty(self):
        assert validate_data_availability(_base_claim(designContractVersion=1), {}, []) == []

    def test_legacy_skip_version_3(self):
        claim = _base_claim(designContractVersion=3)
        assert validate_data_availability(claim, _base_verdict(), [_base_evidence()]) == []

    def test_none_claim(self):
        assert validate_data_availability(None, _base_verdict(), [_base_evidence()]) == []

    def test_list_claim(self):
        assert validate_data_availability([1, 2], _base_verdict(), [_base_evidence()]) == []


# ------------------------------------------------------------------ #
# sorted_first passing cases
# ------------------------------------------------------------------ #


class TestSortedFirstPass:
    def test_valid_basic(self):
        assert validate_data_availability(
            _base_claim(), _base_verdict(), [_base_evidence()]
        ) == []

    def test_english_number_word(self):
        ev = _base_evidence(quote="The study included five participants in total")
        da = {
            "evidenceId": "ev-001",
            "quote": "included five participants",
            "scopeQuote": "five participants",
            "availableCount": 5,
            "countQuote": "five",
            "availableNames": [],
        }
        assert validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [ev]
        ) == []

    def test_english_number_case_insensitive(self):
        ev = _base_evidence(quote="The study included Five participants in total")
        da = {
            "evidenceId": "ev-001",
            "quote": "included Five participants",
            "scopeQuote": "Five participants",
            "availableCount": 5,
            "countQuote": "Five",
            "availableNames": [],
        }
        assert validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [ev]
        ) == []

    def test_countquote_with_surrounding_spaces(self):
        ev = _base_evidence(quote="We enrolled 5 subjects overall")
        da = {
            "evidenceId": "ev-001",
            "quote": "enrolled 5 subjects",
            "scopeQuote": "5 subjects",
            "availableCount": 5,
            "countQuote": " 5",
            "availableNames": [],
        }
        assert validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [ev]
        ) == []

    def test_suggestion_kind(self):
        claim = _base_claim(kind="suggestion")
        assert validate_data_availability(
            claim, _base_verdict(), [_base_evidence()]
        ) == []

    def test_hypothesis_kind(self):
        claim = _base_claim(kind="hypothesis")
        assert validate_data_availability(
            claim, _base_verdict(), [_base_evidence()]
        ) == []


# ------------------------------------------------------------------ #
# sorted_first failure cases
# ------------------------------------------------------------------ #


class TestSortedFirstFailures:
    def test_insufficient_count(self):
        claim = _base_claim()
        claim["executionSpec"]["scenes"]["count"] = 10
        errors = validate_data_availability(claim, _base_verdict(), [_base_evidence()])
        assert "DA_INSUFFICIENT_COUNT" in errors

    def test_count_mismatch(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "included 5 participants",
            "scopeQuote": "5 participants",
            "availableCount": 3,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert "DA_COUNT_MISMATCH" in errors

    def test_substring_digit_boundary_rejects_2_in_12(self):
        ev = _base_evidence(quote="There were 12 items recorded")
        claim = _base_claim()
        claim["executionSpec"]["scenes"]["count"] = 2
        da = {
            "evidenceId": "ev-001",
            "quote": "12 items",
            "scopeQuote": "12 items",
            "availableCount": 2,
            "countQuote": "2",
            "availableNames": [],
        }
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert "DA_COUNTQUOTE_NO_BOUNDARY" in errors

    def test_substring_word_boundary_rejects_one_in_someone(self):
        ev = _base_evidence(quote="someone reported the result")
        claim = _base_claim()
        claim["executionSpec"]["scenes"]["count"] = 1
        da = {
            "evidenceId": "ev-001",
            "quote": "someone reported",
            "scopeQuote": "someone reported",
            "availableCount": 1,
            "countQuote": "one",
            "availableNames": [],
        }
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert "DA_COUNTQUOTE_NO_BOUNDARY" in errors

    def test_scope_is_countquote_rejected(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "included 5 participants",
            "scopeQuote": "5",
            "availableCount": 5,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert "DA_SCOPE_IS_COUNTQUOTE" in errors

    def test_unparseable_countquote(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "included several participants",
            "scopeQuote": "several participants",
            "availableCount": 5,
            "countQuote": "several",
            "availableNames": [],
        }
        ev = _base_evidence(quote="The study included several participants in total")
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [ev]
        )
        assert "DA_COUNTQUOTE_UNPARSEABLE" in errors

    def test_negative_sign_rejected(self):
        ev = _base_evidence(quote="value was -5 units")
        da = {
            "evidenceId": "ev-001",
            "quote": "-5 units",
            "scopeQuote": "-5 units",
            "availableCount": 5,
            "countQuote": "-5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [ev]
        )
        assert "DA_COUNTQUOTE_UNPARSEABLE" in errors

    def test_decimal_rejected(self):
        ev = _base_evidence(quote="approximately 2.5 units measured")
        da = {
            "evidenceId": "ev-001",
            "quote": "2.5 units",
            "scopeQuote": "2.5 units",
            "availableCount": 2,
            "countQuote": "2.5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [ev]
        )
        assert "DA_COUNTQUOTE_UNPARSEABLE" in errors

    def test_zero_rejected(self):
        ev = _base_evidence(quote="found 0 results")
        da = {
            "evidenceId": "ev-001",
            "quote": "found 0 results",
            "scopeQuote": "found 0 results",
            "availableCount": 0,
            "countQuote": "0",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [ev]
        )
        assert "DA_AVAILABLE_COUNT_INVALID" in errors

    def test_bool_available_count_rejected(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "included 5 participants",
            "scopeQuote": "5 participants",
            "availableCount": True,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert "DA_AVAILABLE_COUNT_INVALID" in errors


# ------------------------------------------------------------------ #
# Evidence resolution
# ------------------------------------------------------------------ #


class TestEvidenceResolution:
    def test_evidence_not_found(self):
        errors = validate_data_availability(_base_claim(), _base_verdict(), [])
        assert errors == ["DA_EVIDENCE_NOT_FOUND"]

    def test_unrelated_evidence_id(self):
        ev = _base_evidence(evidenceId="ev-999")
        errors = validate_data_availability(_base_claim(), _base_verdict(), [ev])
        assert errors == ["DA_EVIDENCE_NOT_FOUND"]

    def test_abstract_access_rejected(self):
        ev = _base_evidence(accessLevel="abstract")
        errors = validate_data_availability(_base_claim(), _base_verdict(), [ev])
        assert errors == ["DA_NOT_FULLTEXT"]

    def test_user_note_access_rejected(self):
        ev = _base_evidence(accessLevel="user_note")
        errors = validate_data_availability(_base_claim(), _base_verdict(), [ev])
        assert errors == ["DA_NOT_FULLTEXT"]

    def test_duplicate_evidence_id(self):
        ev1 = _base_evidence()
        ev2 = _base_evidence()
        errors = validate_data_availability(_base_claim(), _base_verdict(), [ev1, ev2])
        assert errors == ["DA_DUPLICATE_IDENTITY"]

    def test_not_in_evidence_refs(self):
        claim = _base_claim(evidenceRefs=["ev-other"])
        errors = validate_data_availability(claim, _base_verdict(), [_base_evidence()])
        assert errors == ["DA_NOT_IN_EVIDENCE_REFS"]

    def test_forged_context_only_support(self):
        """sourceContext must never be used; quote must come from evidence.quote."""
        ev = _base_evidence(
            quote="Completely unrelated text here",
            sourceContext="included 5 participants",
        )
        errors = validate_data_availability(_base_claim(), _base_verdict(), [ev])
        assert errors == ["DA_QUOTE_NOT_IN_SOURCE"]

    def test_quote_not_in_evidence(self):
        ev = _base_evidence(quote="Nothing about participants at all")
        errors = validate_data_availability(_base_claim(), _base_verdict(), [ev])
        assert errors == ["DA_QUOTE_NOT_IN_SOURCE"]


# ------------------------------------------------------------------ #
# Named mode
# ------------------------------------------------------------------ #


class TestNamedMode:
    def _named_claim(self, names: List[str]) -> Dict[str, Any]:
        claim = _base_claim()
        claim["executionSpec"]["scenes"] = {"mode": "named", "names": names}
        return claim

    def test_named_pass(self):
        ev = _base_evidence(
            quote="Datasets Alpha and Beta were included in the analysis"
        )
        da = {
            "evidenceId": "ev-001",
            "quote": "Alpha and Beta were included",
            "scopeQuote": "Alpha and Beta",
            "availableNames": ["Alpha", "Beta"],
        }
        claim = self._named_claim(["Alpha", "Beta"])
        assert validate_data_availability(claim, {"dataAvailability": da}, [ev]) == []

    def test_requested_name_not_available(self):
        ev = _base_evidence(
            quote="Datasets Alpha and Beta were included in the analysis"
        )
        da = {
            "evidenceId": "ev-001",
            "quote": "Alpha and Beta were included",
            "scopeQuote": "Alpha and Beta",
            "availableNames": ["Alpha", "Beta"],
        }
        claim = self._named_claim(["Alpha", "Gamma"])
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert "DA_NAME_NOT_AVAILABLE" in errors

    def test_available_name_not_in_quote(self):
        ev = _base_evidence(
            quote="Datasets Alpha and Beta were included in the analysis"
        )
        da = {
            "evidenceId": "ev-001",
            "quote": "Alpha and Beta were included",
            "scopeQuote": "Alpha and Beta",
            "availableNames": ["Alpha", "Gamma"],
        }
        claim = self._named_claim(["Alpha"])
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert "DA_NAME_NOT_IN_QUOTE" in errors

    def test_case_sensitive_match_required(self):
        ev = _base_evidence(
            quote="Datasets alpha and Beta were included in the analysis"
        )
        da = {
            "evidenceId": "ev-001",
            "quote": "alpha and Beta were included",
            "scopeQuote": "alpha and Beta",
            "availableNames": ["Alpha"],
        }
        claim = self._named_claim(["Alpha"])
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert "DA_NAME_NOT_IN_QUOTE" in errors

    def test_name_as_substring_of_word_rejected(self):
        ev = _base_evidence(
            quote="The Alphabet dataset was used for training"
        )
        da = {
            "evidenceId": "ev-001",
            "quote": "Alphabet dataset",
            "scopeQuote": "Alphabet dataset",
            "availableNames": ["Alpha"],
        }
        claim = self._named_claim(["Alpha"])
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert "DA_NAME_NOT_IN_QUOTE" in errors

    def test_empty_available_names(self):
        ev = _base_evidence(quote="Alpha and Beta were included")
        da = {
            "evidenceId": "ev-001",
            "quote": "Alpha and Beta",
            "scopeQuote": "Alpha and Beta",
            "availableNames": [],
        }
        claim = self._named_claim(["Alpha"])
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert errors == ["DA_NAMES_EMPTY"]

    def test_duplicate_available_names(self):
        ev = _base_evidence(quote="Alpha and Beta were included")
        da = {
            "evidenceId": "ev-001",
            "quote": "Alpha and Beta",
            "scopeQuote": "Alpha and Beta",
            "availableNames": ["Alpha", "Alpha"],
        }
        claim = self._named_claim(["Alpha"])
        errors = validate_data_availability(claim, {"dataAvailability": da}, [ev])
        assert errors == ["DA_NAMES_NOT_UNIQUE"]


# ------------------------------------------------------------------ #
# Malformed types
# ------------------------------------------------------------------ #


class TestMalformedTypes:
    def test_missing_data_availability(self):
        errors = validate_data_availability(_base_claim(), {}, [_base_evidence()])
        assert errors == ["DA_MISSING"]

    def test_verdict_not_dict(self):
        errors = validate_data_availability(_base_claim(), "bad", [_base_evidence()])
        assert errors == ["DA_MALFORMED_VERDICT"]

    def test_da_not_dict(self):
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": [1]}, [_base_evidence()]
        )
        assert errors == ["DA_MALFORMED_DATA_AVAILABILITY"]

    def test_visible_evidence_not_list(self):
        errors = validate_data_availability(_base_claim(), _base_verdict(), "bad")
        assert errors == ["DA_EVIDENCE_LIST_INVALID"]

    def test_unknown_mode(self):
        claim = _base_claim()
        claim["executionSpec"]["scenes"]["mode"] = "random_mode"
        errors = validate_data_availability(claim, _base_verdict(), [_base_evidence()])
        assert errors == ["DA_MODE_UNKNOWN"]

    def test_unhashable_evidence_id(self):
        da = {
            "evidenceId": ["un", "hashable"],
            "quote": "included 5 participants",
            "scopeQuote": "5 participants",
            "availableCount": 5,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert errors == ["DA_EVIDENCE_ID_INVALID"]

    def test_malformed_execution_spec(self):
        claim = _base_claim(executionSpec="not_a_dict")
        errors = validate_data_availability(claim, _base_verdict(), [_base_evidence()])
        assert errors == ["DA_MALFORMED_EXECUTION_SPEC"]

    def test_bool_requested_count_rejected(self):
        claim = _base_claim()
        claim["executionSpec"]["scenes"]["count"] = True
        errors = validate_data_availability(claim, _base_verdict(), [_base_evidence()])
        assert errors == ["DA_MALFORMED_REQUESTED_COUNT"]

    def test_scope_blank(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "included 5 participants",
            "scopeQuote": "   ",
            "availableCount": 5,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert errors == ["DA_SCOPE_BLANK"]

    def test_quote_blank(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "   ",
            "scopeQuote": "x",
            "availableCount": 5,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert errors == ["DA_QUOTE_BLANK"]

    def test_da_quote_not_substring_of_evidence_quote(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "this text is not in the evidence",
            "scopeQuote": "not in the evidence",
            "availableCount": 5,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert errors == ["DA_QUOTE_NOT_IN_SOURCE"]

    def test_scope_not_in_da_quote(self):
        da = {
            "evidenceId": "ev-001",
            "quote": "included 5 participants",
            "scopeQuote": "completely absent",
            "availableCount": 5,
            "countQuote": "5",
            "availableNames": [],
        }
        errors = validate_data_availability(
            _base_claim(), {"dataAvailability": da}, [_base_evidence()]
        )
        assert errors == ["DA_SCOPE_NOT_IN_QUOTE"]


# ------------------------------------------------------------------ #
# Input non-mutation
# ------------------------------------------------------------------ #


class TestNonMutation:
    def test_inputs_not_mutated(self):
        claim = _base_claim()
        verdict = _base_verdict()
        evidence_list: List[Dict[str, Any]] = [_base_evidence()]

        claim_before = copy.deepcopy(claim)
        verdict_before = copy.deepcopy(verdict)
        evidence_before = copy.deepcopy(evidence_list)

        validate_data_availability(claim, verdict, evidence_list)

        assert claim == claim_before
        assert verdict == verdict_before
        assert evidence_list == evidence_before

    def test_inputs_not_mutated_on_error_path(self):
        claim = _base_claim()
        verdict = _base_verdict(countQuote="99", availableCount=99)
        evidence_list: List[Dict[str, Any]] = [_base_evidence()]

        claim_before = copy.deepcopy(claim)
        verdict_before = copy.deepcopy(verdict)
        evidence_before = copy.deepcopy(evidence_list)

        validate_data_availability(claim, verdict, evidence_list)

        assert claim == claim_before
        assert verdict == verdict_before
        assert evidence_list == evidence_before
