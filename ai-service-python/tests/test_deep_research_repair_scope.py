"""Tests for repair_evidence_scope."""

import copy

from services.deep_research.repair_scope import repair_evidence_scope


def _ev(eid, literal="passed", access="fulltext",
        quote="q", swid="w1", svid="v1", obligations=None):
    return {
        "evidenceId": eid,
        "verification": {"literal": literal},
        "accessLevel": access,
        "quote": quote,
        "sourceWorkId": swid,
        "sourceVersionId": svid,
        "obligationIds": ["ob1"] if obligations is None else obligations,
    }


def _claim(cid, refs=None, obligations=None, kind="reported"):
    return {
        "claimId": cid,
        "kind": kind,
        "evidenceRefs": refs or [],
        "obligationIds": ["ob1"] if obligations is None else obligations,
    }


# --- basic preservation -------------------------------------------------------

def test_preserves_existing_refs_in_order():
    claims = [_claim("c1", refs=["e1", "e2"])]
    evidence = [_ev("e1"), _ev("e2")]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1", "e2"]


def test_deduplicates_refs_preserving_first():
    claims = [_claim("c1", refs=["e1", "e2", "e1"])]
    evidence = [_ev("e1"), _ev("e2")]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1", "e2"]


# --- expansion -----------------------------------------------------------------

def test_adds_candidate_matching_anchor_and_obligation():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        _ev("e1"),
        _ev("e2", swid="w1", svid="v1", obligations=["ob1"]),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1", "e2"]


def test_same_source_passage_can_come_from_another_retrieval_obligation():
    claims = [_claim("c1", refs=["e1"], obligations=["ob1"])]
    evidence = [
        _ev("e1"),
        _ev("e2", obligations=["obX"]),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1", "e2"]


def test_no_expansion_without_anchor_pair():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        _ev("e1"),
        _ev("e2", swid="w9", svid="v9"),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


def test_proposal_cannot_expand_factual_sources():
    claims = [_claim("c1", refs=["e1"], kind="proposal")]
    evidence = [
        _ev("e1"),
        _ev("e2"),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


def test_kind_inference_allowed():
    claims = [_claim("c1", refs=["e1"], kind="inference")]
    evidence = [
        _ev("e1"),
        _ev("e2"),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1", "e2"]


def test_verification_literal_must_be_passed():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        _ev("e1"),
        _ev("e2", literal="failed"),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


def test_empty_quote_rejected():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        _ev("e1"),
        _ev("e2", quote=""),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


def test_access_level_must_be_fulltext():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        _ev("e1"),
        _ev("e2", access="abstract"),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


# --- anchor constraints --------------------------------------------------------

def test_anchor_must_be_passed_fulltext():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        _ev("e1", literal="failed"),
        _ev("e2"),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


def test_no_expansion_when_obligations_absent():
    claims = [_claim("c1", refs=["e1"], obligations=[])]
    evidence = [_ev("e1"), _ev("e2")]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


# --- duplicate handling --------------------------------------------------------

def test_duplicate_claim_id_omitted():
    claims = [_claim("c1"), _claim("c1")]
    evidence = [_ev("e1")]
    out = repair_evidence_scope(claims, evidence)
    assert "c1" not in out


def test_duplicate_evidence_id_not_used_as_anchor_or_candidate():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        _ev("e1"),
        _ev("e1"),  # duplicate
        _ev("e2"),
    ]
    out = repair_evidence_scope(claims, evidence)
    # e1 is ambiguous so cannot anchor; e2 cannot be added
    assert out["c1"] == ["e1"]


def test_duplicate_evidence_preserved_in_original_refs():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [_ev("e1"), _ev("e1")]
    out = repair_evidence_scope(claims, evidence)
    # Original ref preserved for downstream verifier
    assert out["c1"] == ["e1"]


# --- max_additions clamping ----------------------------------------------------

def test_max_additions_default_twelve():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [_ev("e1")] + [_ev(f"x{i}") for i in range(30)]
    out = repair_evidence_scope(claims, evidence)
    assert len(out["c1"]) == 1 + 12


def test_max_additions_clamped_to_zero():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [_ev("e1"), _ev("e2")]
    out = repair_evidence_scope(claims, evidence, max_additions=-3)
    assert out["c1"] == ["e1"]


def test_max_additions_clamped_to_twenty_four():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [_ev("e1")] + [_ev(f"x{i}") for i in range(30)]
    out = repair_evidence_scope(claims, evidence, max_additions=99)
    assert len(out["c1"]) == 1 + 24


# --- defensive / malformed input -----------------------------------------------

def test_empty_inputs():
    assert repair_evidence_scope([], []) == {}


def test_non_list_inputs():
    assert repair_evidence_scope(None, "bad") == {}


def test_non_dict_rows_ignored():
    claims = [_claim("c1", refs=["e1"]), "junk", 42]
    evidence = [_ev("e1"), None, "str"]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


def test_non_string_claim_id_skipped():
    claims = [{"claimId": 123, "evidenceRefs": [], "obligationIds": []}]
    out = repair_evidence_scope(claims, [])
    assert out == {}


def test_non_list_evidence_refs_treated_as_empty():
    claims = [{"claimId": "c1", "evidenceRefs": "nope", "obligationIds": ["ob1"]}]
    evidence = [_ev("e1")]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == []


def test_non_dict_verification_skipped():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        {"evidenceId": "e1", "kind": "reported", "verification": "bad",
         "accessLevel": "fulltext", "quote": "q",
         "sourceWorkId": "w1", "sourceVersionId": "v1"},
        _ev("e2"),
    ]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


def test_non_string_ids_in_refs_skipped():
    claims = [_claim("c1", refs=[None, 5, "e1"])]
    evidence = [_ev("e1")]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1"]


# --- no mutation -----------------------------------------------------------------

def test_does_not_mutate_inputs():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [_ev("e1"), _ev("e2")]
    claims_copy = copy.deepcopy(claims)
    evidence_copy = copy.deepcopy(evidence)
    repair_evidence_scope(claims, evidence)
    assert claims == claims_copy
    assert evidence == evidence_copy


# --- stable ordering -------------------------------------------------------------

def test_candidate_order_follows_evidence_list_order():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [_ev("e1"), _ev("b"), _ev("a")]
    out = repair_evidence_scope(claims, evidence)
    assert out["c1"] == ["e1", "b", "a"]


# --- never infer from titles -----------------------------------------------------

def test_title_not_used_for_identity():
    claims = [_claim("c1", refs=["e1"])]
    evidence = [
        {**_ev("e1"), "title": "Same Paper"},
        {**_ev("e2", swid="wX", svid="vX"), "title": "Same Paper"},
    ]
    out = repair_evidence_scope(claims, evidence)
    # e2 has different source identity despite same title
    assert out["c1"] == ["e1"]


def test_candidate_cap_balances_later_obligations_instead_of_first_chunk_only():
    claims = [_claim('c', refs=['anchor'])]
    evidence = [_ev('anchor')] + [_ev(f'early{i}') for i in range(20)] + [
        _ev('later', obligations=['another'])]
    result = repair_evidence_scope(claims, evidence, max_additions=2)
    assert result['c'] == ['anchor', 'early0', 'later']
