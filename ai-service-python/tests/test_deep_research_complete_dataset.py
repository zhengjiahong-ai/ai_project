from copy import deepcopy
import pytest
from services.deep_research.execution_spec import execution_spec_errors
from services.deep_research.protocol_text import render_execution_spec
from services.deep_research.data_availability import validate_data_availability
from test_deep_research_execution_spec_integration import data_spec


def setup_case(count=9):
    spec = data_spec()
    spec['scenes'] = {'mode': 'all', 'count': count}
    claim = {'kind': 'proposal', 'designRole': 'data', 'designContractVersion': 2,
             'executionSpec': spec, 'evidenceRefs': ['e']}
    quote = 'The complete benchmark contains nine scenes.'
    evidence = [{'evidenceId': 'e', 'quote': quote, 'accessLevel': 'fulltext'}]
    verdict = {'dataAvailability': {'evidenceId': 'e', 'quote': quote, 'scopeQuote': 'complete benchmark',
                                   'availableCount': 9, 'countQuote': 'nine'}}
    return claim, verdict, evidence


def test_full_benchmark_needs_no_arbitrary_order_or_name_list():
    claim, verdict, evidence = setup_case()
    before = deepcopy(claim)
    assert not execution_spec_errors('data', claim['executionSpec'])
    assert not validate_data_availability(claim, verdict, evidence)
    assert '全部9个场景' in render_execution_spec('data', claim['executionSpec'])
    assert claim == before


@pytest.mark.parametrize('count', [2, 8, 10])
def test_all_requires_equality_not_merely_sufficient_capacity(count):
    claim, verdict, evidence = setup_case(count)
    assert 'DA_COMPLETE_COUNT_MISMATCH' in validate_data_availability(claim, verdict, evidence)


def test_all_cannot_hide_a_second_selection_rule():
    claim, verdict, evidence = setup_case()
    claim['executionSpec']['scenes']['order'] = 'pick the first two'
    assert execution_spec_errors('data', claim['executionSpec'])
    assert validate_data_availability(claim, verdict, evidence)


def test_all_still_requires_own_fulltext_count_binding():
    claim, verdict, evidence = setup_case()
    assert validate_data_availability(claim, {}, evidence)
    evidence[0]['accessLevel'] = 'abstract'
    assert validate_data_availability(claim, verdict, evidence)
