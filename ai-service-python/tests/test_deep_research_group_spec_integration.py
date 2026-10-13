from copy import deepcopy
from unittest.mock import Mock
import pytest

from services.deep_research.execution_materialization import materialize_execution_claim
from services.deep_research.verification import verify_claims


def group_claim(value=0.01):
    return {'claimId': 'g', 'kind': 'proposal', 'designRole': 'groups',
            'designContractVersion': 2, 'text': 'Proposed paired threshold experiment.',
            'evidenceRefs': [], 'executionSpec': {'factors': [{'name': 'filtering',
                'control': {'action': 'keep all', 'parameters': []},
                'treatment': {'action': 'remove items below cutoff', 'parameters': [
                    {'name': 'cutoff', 'type': 'number', 'value': value}]}}]}}


@pytest.mark.parametrize('value', ['epsilon', True, float('nan'), float('inf')])
def test_nonconcrete_numeric_parameter_cannot_reach_semantic_acceptance(value):
    checker = Mock(return_value=[{'claimId': 'g', 'status': 'passed'}])
    result = verify_claims([group_claim(value)], [], checker)
    assert result['rejected'][0]['reason'] == 'incomplete_execution_spec'
    checker.assert_not_called()


def test_missing_group_spec_cannot_use_an_unassigned_symbol_as_concrete_level():
    claim = group_claim()
    del claim['executionSpec']
    claim['text'] = 'Proposed removal when x < cutoff; cutoff unspecified.'
    assert verify_claims([claim], [], Mock())['rejected'][0]['reason'] == 'incomplete_execution_spec'


def test_concrete_values_are_visible_but_do_not_replace_independent_verification():
    claim = group_claim()
    before = deepcopy(claim)
    rendered = materialize_execution_claim(claim)
    assert '0.01' in rendered['text'] and 'cutoff' in rendered['text']
    assert rendered['text'].startswith(claim['text'])
    assert claim == before
    checker = Mock(return_value=[{'claimId': 'g', 'status': 'failed', 'reason': 'wrong operation'}])
    result = verify_claims([rendered], [], checker)
    assert result['rejected'][0]['reason'] == 'semantic_unresolved'
    checker.assert_called_once()
