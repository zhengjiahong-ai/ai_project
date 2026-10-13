import copy
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.deep_research.design_audit import validate_design_audit

CLAIM_TEXT = "scenes: A1/B2; split: 50/50; seeds: 7, 8, 9; sampling_unit: user"


def make_data_claim(**overrides):
    claim = {
        "claimId": "claim-data-1",
        "designRole": "data",
        "kind": "proposal",
        "text": CLAIM_TEXT,
        "conditions": {"note": "固定种子 7, 8, 9"},
    }
    claim.update(overrides)
    return claim


def entry(quote, claim_id="claim-data-1"):
    return {"claimId": claim_id, "quote": quote}


def audit_for(**slots):
    return {"designAudit": slots}


def full_audit():
    return audit_for(
        scenes=entry("scenes: A1/B2"),
        split=entry("split: 50/50"),
        seeds=entry("seeds: 7, 8, 9"),
        sampling_unit=entry("sampling_unit: user"),
    )


def test_missing_audit_reports_every_required_slot():
    claim = make_data_claim()
    expected = ["scenes", "split", "seeds", "sampling_unit"]
    assert validate_design_audit(claim, {}, []) == expected
    assert validate_design_audit(claim, {"designAudit": []}, []) == expected


def test_steps_cannot_pass_with_only_an_unsubstantiated_model_verdict():
    claim = {'claimId': 'steps', 'kind': 'proposal', 'designRole': 'steps',
             'text': 'Train until convergence, then save the checkpoint hash.'}
    assert validate_design_audit(claim, {'status': 'passed'}, []) == [
        'baseline_acquisition', 'group_pairing', 'saved_artifacts']


def test_steps_can_bind_concrete_shared_budget_without_repeating_it():
    claim = {'claimId': 'steps', 'kind': 'proposal', 'designRole': 'steps',
             'text': 'Copy the baseline into four groups within each scene. Save the split and raw measurements.'}
    context = [{'claimId': 'budget', 'kind': 'proposal', 'designRole': 'budget',
                'text': 'Train the baseline for 1000 steps with seed 42.'}]
    verdict = audit_for(
        baseline_acquisition=entry(context[0]['text'], 'budget'),
        group_pairing=entry('Copy the baseline into four groups within each scene.', 'steps'),
        saved_artifacts=entry('Save the split and raw measurements.', 'steps'))
    assert validate_design_audit(claim, verdict, context) == []
    verdict['designAudit']['baseline_acquisition'] = entry('Train for 2000 steps.', 'budget')
    assert validate_design_audit(claim, verdict, context) == ['baseline_acquisition']


def test_partial_audit_reports_only_missing_slots():
    verdict = audit_for(scenes=entry("scenes: A1/B2"), split=entry("split: 50/50"))
    assert validate_design_audit(make_data_claim(), verdict, []) == [
        "seeds",
        "sampling_unit",
    ]


def test_forged_quote_fails_its_slot():
    verdict = full_audit()
    verdict["designAudit"]["seeds"] = entry("seeds: 42")
    assert validate_design_audit(make_data_claim(), verdict, []) == ["seeds"]


def test_fact_reference_cannot_support_quotes():
    context = [{
        "claimId": "ctx-fact",
        "kind": "fact",
        "text": CLAIM_TEXT,
    }]
    verdict = {
        "designAudit": {
            "scenes": entry("scenes: A1/B2", "ctx-fact"),
            "split": entry("split: 50/50", "ctx-fact"),
            "seeds": entry("seeds: 7, 8, 9", "ctx-fact"),
            "sampling_unit": entry("sampling_unit: user", "ctx-fact"),
        }
    }
    claim = make_data_claim(text="decide data design only")
    assert validate_design_audit(claim, verdict, context) == [
        "scenes",
        "split",
        "seeds",
        "sampling_unit",
    ]


def test_shared_proposal_context_supports_quotes():
    context = [{
        "claimId": "ctx-proposal",
        "kind": "proposal",
        "text": CLAIM_TEXT,
    }]
    verdict = {
        "designAudit": {
            "scenes": entry("scenes: A1/B2", "ctx-proposal"),
            "split": entry("split: 50/50", "ctx-proposal"),
            "seeds": entry("seeds: 7, 8, 9", "ctx-proposal"),
            "sampling_unit": entry("sampling_unit: user", "ctx-proposal"),
        }
    }
    claim = make_data_claim(text="see shared proposal", conditions=None)
    assert validate_design_audit(claim, verdict, context) == []


def test_quotes_found_in_json_serialized_conditions():
    claim = make_data_claim(
        text="design draft",
        conditions={
            "scenes": "A1/B2",
            "split": "50/50",
            "seeds": [7, 8, 9],
            "sampling_unit": "user",
        },
    )
    verdict = audit_for(
        scenes=entry('"scenes": "A1/B2"'),
        split=entry('"split": "50/50"'),
        seeds=entry('"seeds": [7, 8, 9]'),
        sampling_unit=entry('"sampling_unit": "user"'),
    )
    assert validate_design_audit(claim, verdict, []) == []


def test_malformed_entries_fail_slots_without_raising():
    verdict = {
        "designAudit": {
            "scenes": "scenes: A1/B2",
            "split": ["split: 50/50"],
            "seeds": {"claimId": "claim-data-1", "quote": ""},
            "sampling_unit": {"claimId": 7, "quote": "sampling_unit: user"},
        }
    }
    assert validate_design_audit(make_data_claim(), verdict, []) == [
        "scenes",
        "split",
        "seeds",
        "sampling_unit",
    ]


def test_valid_audit_returns_empty_list():
    assert validate_design_audit(make_data_claim(), full_audit(), []) == []


def test_role_wrapper_still_requires_every_exact_configuration_quote():
    verdict = {'designAudit': {'data': full_audit()['designAudit']}}
    assert validate_design_audit(make_data_claim(), verdict, []) == []
    verdict['designAudit']['data']['split']['quote'] = 'invented split'
    assert validate_design_audit(make_data_claim(), verdict, []) == ['split']


def test_whitespace_and_reported_self_cannot_supply_proposed_configuration():
    verdict = full_audit()
    verdict['designAudit']['split']['quote'] = ' '
    assert validate_design_audit(make_data_claim(), verdict, []) == ['split']
    assert validate_design_audit(make_data_claim(kind='reported'), full_audit(), []) == [
        'scenes', 'split', 'seeds', 'sampling_unit']
    assert validate_design_audit(make_data_claim(kind=[]), full_audit(), []) == [
        'scenes', 'split', 'seeds', 'sampling_unit']


def test_inputs_are_not_mutated():
    claim = make_data_claim()
    context = [{"claimId": "ctx-proposal", "kind": "proposal", "text": CLAIM_TEXT}]
    verdict = full_audit()
    snapshots = (copy.deepcopy(claim), copy.deepcopy(verdict), copy.deepcopy(context))
    validate_design_audit(claim, verdict, context)
    assert (claim, verdict, context) == snapshots


def test_unrelated_or_nonstring_role_is_noop():
    assert validate_design_audit({"claimId": "x", "designRole": "ethics", "text": "n/a"}, {}, []) == []
    assert validate_design_audit({"claimId": "x", "designRole": 5, "text": "n/a"}, {}, []) == []
    assert validate_design_audit(None, {"designAudit": full_audit()["designAudit"]}, []) == []


def test_discontinuous_effects_bind_each_exact_segment_without_rewriting():
    claim = {'claimId': 'a', 'kind': 'proposal', 'designRole': 'analysis',
             'text': '- A: L10-L00\n- B: L01-L00\npaired scenes; descriptive only'}
    verdict = audit_for(effects={'quotes': [entry('A: L10-L00', 'a'), entry('B: L01-L00', 'a')]},
                        uncertainty=entry('paired scenes', 'a'), decision_rule=entry('descriptive only', 'a'))
    assert validate_design_audit(claim, verdict, []) == []
    verdict['designAudit']['effects'] = entry('A: L10-L00; B: L01-L00', 'a')
    assert validate_design_audit(claim, verdict, []) == ['effects']


@pytest.mark.parametrize('segments', [[], [None], [{'quotes': []}],
    [entry('seeds: 7'), entry('fabricated')], [entry('seeds: 7', 'wrong')],
    [entry('seeds: 7')] * 33])
def test_invalid_or_partially_forged_segments_fail_closed(segments):
    verdict = full_audit()
    verdict['designAudit']['seeds'] = {'quotes': segments}
    assert validate_design_audit(make_data_claim(), verdict, []) == ['seeds']


def test_segmented_quotes_reject_ambiguous_forms_and_fact_sources():
    verdict = full_audit()
    verdict['designAudit']['seeds'] = {'quotes': [entry('seeds: 7')], **entry('seeds: 7')}
    assert validate_design_audit(make_data_claim(), verdict, []) == ['seeds']
    verdict['designAudit']['seeds'] = {'quotes': [entry('seeds: 7', 'fact')]}
    context = [{'claimId': 'fact', 'kind': 'reported', 'text': 'seeds: 7'}]
    assert validate_design_audit(make_data_claim(), verdict, context) == ['seeds']


def test_segments_can_bind_separate_proposals_without_mutation():
    verdict = full_audit()
    verdict['designAudit']['seeds'] = {'quotes': [entry('seeds: 7'), entry('extra seed: 8', 'p')]}
    context = [{'claimId': 'p', 'kind': 'proposal', 'text': 'extra seed: 8'}]
    snapshot = copy.deepcopy(verdict)
    assert validate_design_audit(make_data_claim(), verdict, context) == []
    assert verdict == snapshot
