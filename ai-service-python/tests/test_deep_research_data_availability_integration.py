"""A prospective parameter cannot establish existing dataset capacity."""
import json
import pytest

from services.deep_research.tools import BudgetedSemanticChecker
from services.deep_research.execution_materialization import materialize_execution_claim
from services.deep_research.verification import verify_claims


def run_case(count, availability):
    claim = materialize_execution_claim({
        'claimId': 'data', 'kind': 'proposal', 'designRole': 'data',
        'designContractVersion': 2, 'text': 'Proposed evaluation on the published subset.',
        'evidenceRefs': ['e'], 'executionSpec': {
            'dataset': 'Benchmark published subset',
            'scenes': {'mode': 'sorted_first', 'count': count, 'order': 'alphabetical'},
            'split': {'mode': 'every_nth', 'order': 'filename', 'stride': 8, 'offset': 0},
            'seeds': [0, 1, 2], 'independentUnit': 'scene',
            'replication': {'mode': 'retrained_per_seed'}}})
    evidence = [{'evidenceId': 'e', 'quote': 'The published subset has two scenes.',
                 'verification': {'literal': 'passed'},
                 'accessLevel': 'fulltext', 'sourceWorkId': 'paper', 'sourceVersionId': 'v'}]
    def invoke(**kwargs):
        assert 'dataAvailability' in kwargs['prompt']
        assert 'inherited subset' in kwargs['prompt']
        verdict = {'claimId': 'data', 'status': 'passed', 'designAudit': {
            slot: {'claimId': 'data', 'quote': claim['text']}
            for slot in ('scenes', 'split', 'seeds', 'sampling_unit')}}
        if availability is not None:
            verdict['dataAvailability'] = availability
        return {'content': json.dumps([verdict])}
    return verify_claims([claim], evidence, BudgetedSemanticChecker(invoke, 'r'))


def bound_capacity():
    return {'evidenceId': 'e', 'quote': 'The published subset has two scenes.',
            'scopeQuote': 'published subset', 'availableCount': 2, 'countQuote': 'two'}


def test_concrete_configuration_and_model_pass_do_not_override_missing_availability():
    result = run_case(5, None)
    assert not result['accepted']
    assert 'DA_MISSING' in result['rejected'][0]['detail']


def test_cited_capacity_rejects_five_selected_from_two_without_silently_repairing():
    result = run_case(5, bound_capacity())
    assert not result['accepted']
    assert 'DA_INSUFFICIENT_COUNT' in result['rejected'][0]['detail']


def test_valid_bounded_selection_keeps_proposal_status():
    result = run_case(2, bound_capacity())
    assert len(result['accepted']) == 1
    assert result['accepted'][0]['verification'] == 'proposal'


def test_model_cannot_invent_larger_capacity_in_its_audit():
    audit = {**bound_capacity(), 'availableCount': 5}
    result = run_case(5, audit)
    assert not result['accepted']
    assert 'DA_COUNT_MISMATCH' in result['rejected'][0]['detail']


@pytest.mark.parametrize('source', ['12 scenes', '2.5 scenes', '-2 scenes', '2,000 scenes',
                                  'x2 scenes', '2e3 scenes', '2% scenes', '2_scenes'])
def test_capacity_token_cannot_be_cut_from_larger_numeric_expression(source):
    from services.deep_research.data_availability import validate_data_availability
    claim = {'kind': 'proposal', 'designRole': 'data', 'designContractVersion': 2,
             'executionSpec': {'scenes': {'mode': 'sorted_first', 'count': 2}}, 'evidenceRefs': ['e']}
    verdict = {'dataAvailability': {'evidenceId': 'e', 'quote': source,
                                   'scopeQuote': 'scenes', 'availableCount': 2, 'countQuote': '2'}}
    assert validate_data_availability(claim, verdict,
        [{'evidenceId': 'e', 'accessLevel': 'fulltext', 'quote': source}])


def test_audit_quote_cannot_hide_surrounding_digits():
    from services.deep_research.data_availability import validate_data_availability
    claim = {'kind': 'proposal', 'designRole': 'data', 'designContractVersion': 2,
             'executionSpec': {'scenes': {'mode': 'sorted_first', 'count': 2}}, 'evidenceRefs': ['e']}
    verdict = {'dataAvailability': {'evidenceId': 'e', 'quote': '2 scenes',
                                   'scopeQuote': 'scenes', 'availableCount': 2, 'countQuote': '2'}}
    assert validate_data_availability(claim, verdict,
        [{'evidenceId': 'e', 'accessLevel': 'fulltext', 'quote': '12 scenes'}])
