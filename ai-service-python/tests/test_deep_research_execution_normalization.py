from copy import deepcopy
import pytest

from services.deep_research.execution_materialization import normalize_execution_spec, materialize_execution_claim
from services.deep_research.execution_spec import execution_spec_errors
from test_deep_research_execution_spec_integration import data_spec
from test_deep_research_execution_materialization import analysis_claim


def test_observed_data_wrapper_and_offset_spelling_are_syntax_only():
    spec = data_spec()
    spec['split']['zero-based offset'] = spec['split'].pop('offset')
    wrapped = {'data': spec}
    before = deepcopy(wrapped)
    normalized = normalize_execution_spec('data', wrapped)
    assert normalized == data_spec()
    assert normalize_execution_spec('data', normalized) == normalized
    assert wrapped == before
    assert not execution_spec_errors('data', normalized)


def test_analysis_wrapper_reaches_visible_formula_materialization():
    claim = analysis_claim()
    original_spec = deepcopy(claim['executionSpec'])
    claim['executionSpec'] = {'analysis': original_spec}
    output = materialize_execution_claim(claim)
    assert output['executionSpec'] == original_spec
    assert '999' in output['text'] and 'L10 - L00' in output['text']
    assert 'analysis' in claim['executionSpec']


@pytest.mark.parametrize('alias', [1, False, '0'])
def test_conflicting_offsets_are_not_resolved_by_precedence(alias):
    spec = data_spec()
    spec['split']['zero-based offset'] = alias
    normalized = normalize_execution_spec('data', spec)
    assert normalized == spec
    assert 'split.ambiguous_offset' in execution_spec_errors('data', normalized)


def test_matching_offset_alias_is_removed_without_changing_value():
    spec = data_spec()
    spec['split']['zero-based offset'] = 0
    assert normalize_execution_spec('data', spec) == data_spec()


def test_mixed_wrapper_and_direct_fields_are_rejected_not_merged():
    spec = {**data_spec(), 'data': {'dataset': 'different subset'}}
    assert normalize_execution_spec('data', spec) == spec
    assert 'ambiguous_role_wrapper' in execution_spec_errors('data', spec)


def test_unknown_wrapper_and_malformed_spec_remain_invalid():
    for spec in [None, [], {'analysis': data_spec()}, {'data': None}]:
        normalized = normalize_execution_spec('data', spec)
        assert normalized == spec
        assert execution_spec_errors('data', normalized)


@pytest.mark.parametrize('mode', ['fixed_checkpoint', 'retrained_per_seed'])
def test_exact_replication_enum_materializes_without_choosing_new_settings(mode):
    spec = data_spec()
    spec['replication'] = mode
    before = deepcopy(spec)
    normalized = normalize_execution_spec('data', spec)
    assert normalized['replication'] == {'mode': mode}
    assert spec == before
    assert normalize_execution_spec('data', normalized) == normalized
    assert not execution_spec_errors('data', normalized)
    claim = {'kind': 'proposal', 'designRole': 'data', 'designContractVersion': 2,
             'text': 'Original proposed protocol.', 'executionSpec': spec}
    rendered = materialize_execution_claim(claim)
    assert rendered['text'].startswith(claim['text'])
    assert len(rendered['text']) > len(claim['text'])


@pytest.mark.parametrize('value', ['unknown', ' fixed_checkpoint', '', [], None])
def test_unknown_replication_values_are_not_guessed(value):
    spec = data_spec()
    spec['replication'] = value
    assert normalize_execution_spec('data', spec) == spec
    assert execution_spec_errors('data', normalize_execution_spec('data', spec))
