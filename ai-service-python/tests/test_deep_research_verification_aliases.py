from copy import deepcopy
import json
import pytest
from services.deep_research.verification_aliases import (
    encode_verification_inputs, restore_visible_evidence, restore_verdict_evidence)
from services.deep_research.tools import BudgetedSemanticChecker


def test_roundtrip_preserves_quotes_and_source_identity_without_mutation():
    full = 'ev_' + 'a' * 64
    claims = [{'claimId': 'c', 'text': full, 'evidenceRefs': [full],
               'tableBindings': [{'evidenceId': full, 'value': '2'}]}]
    evidence = [{'evidenceId': full, 'quote': 'Literal E1 quotation', 'sourceContext': full,
                 'sourceWorkId': 'paper', 'sourceVersionId': 'version'}]
    before = deepcopy((claims, evidence))
    wire, rows, reverse = encode_verification_inputs(claims, evidence)
    assert wire[0]['claimId'] == 'c' and wire[0]['text'] == full
    assert wire[0]['evidenceRefs'] == [rows[0]['evidenceId']]
    assert wire[0]['tableBindings'][0]['evidenceId'] == rows[0]['evidenceId']
    assert rows[0]['quote'] == evidence[0]['quote']
    assert restore_visible_evidence(rows, reverse) == evidence
    assert (claims, evidence) == before
    verdict = {'claimId': 'c', 'reason': 'E1', 'dataAvailability': {'evidenceId': rows[0]['evidenceId']}}
    decoded = restore_verdict_evidence(verdict, reverse)
    assert decoded['dataAvailability']['evidenceId'] == full
    assert decoded['reason'] == 'E1' and verdict != decoded


def test_aliases_cannot_collide_with_real_or_unresolved_ids():
    claims = [{'evidenceRefs': ['long-id', 'E1']}]
    evidence = [{'evidenceId': 'long-id'}, {'evidenceId': 'E_1'}]
    wire, rows, reverse = encode_verification_inputs(claims, evidence)
    assert rows[0]['evidenceId'] not in {'long-id', 'E1', 'E_1'}
    assert wire[0]['evidenceRefs'][1] == 'E1'
    assert len(rows) == 1
    assert restore_verdict_evidence({'dataAvailability': {'evidenceId': 'unknown'}}, reverse)['dataAvailability']['evidenceId'] == 'unknown'


def test_duplicate_identity_is_not_silently_overwritten():
    with pytest.raises(ValueError, match='Duplicate'):
        encode_verification_inputs([{'evidenceRefs': ['same']}], [{'evidenceId': 'same'}] * 2)


def test_capacity_omitted_evidence_still_cannot_support_passed_verdict():
    full = 'ev_' + 'b' * 64
    claim = {'claimId': 'c', 'kind': 'reported', 'text': 'Reported finding', 'evidenceRefs': [full]}
    evidence = [{'evidenceId': full, 'quote': 'x' * 30000}]
    def invoke(**kwargs):
        assert full not in kwargs['prompt']
        return {'content': json.dumps([{'claimId': 'c', 'status': 'passed'}])}
    result = BudgetedSemanticChecker(invoke, 'r')([claim], evidence)
    assert result[0]['status'] == 'failed'
    assert '容量' in result[0]['reason']


def test_visible_alias_restores_permissions_for_regular_claim():
    full = 'ev_' + 'c' * 64
    def invoke(**kwargs):
        assert full not in kwargs['prompt']
        assert 'Literal quotation' in kwargs['prompt']
        return {'content': json.dumps([{'claimId': 'c', 'status': 'passed'}])}
    result = BudgetedSemanticChecker(invoke, 'r')(
        [{'claimId': 'c', 'kind': 'reported', 'text': 'Finding', 'evidenceRefs': [full]}],
        [{'evidenceId': full, 'quote': 'Literal quotation'}])
    assert result[0]['status'] == 'passed'


def test_data_availability_alias_is_restored_before_source_bound_checks():
    from test_deep_research_data_availability_integration import run_case, bound_capacity
    valid = {**bound_capacity(), 'evidenceId': 'E1'}
    assert run_case(2, valid)['accepted'][0]['verification'] == 'proposal'
    invalid = {**valid, 'evidenceId': 'E99'}
    assert not run_case(2, invalid)['accepted']
