from copy import deepcopy
import pytest

from services.deep_research.design_audit import validate_design_audit
from services.deep_research.tools import BudgetedSemanticChecker
from test_deep_research_group_spec_integration import group_claim


PATH = ['executionSpec', 'factors', 0, 'treatment', 'parameters', 0, 'value']


def verdict(value=0.01, path=None):
    return {'claimId': 'g', 'status': 'passed', 'designAudit': {
        'group_construction': {'claimId': 'g', 'quote': 'Proposed paired threshold experiment.'},
        'intervention_levels': {'fields': [{'claimId': 'g', 'path': PATH if path is None else path,
                                           'value': value}]}}}


def test_exact_typed_field_binding_preserves_input():
    claim, audit = group_claim(), verdict()
    before = deepcopy((claim, audit))
    assert validate_design_audit(claim, audit, []) == []
    assert (claim, audit) == before


@pytest.mark.parametrize('value,path', [(True, PATH), ('0.01', PATH), (0.02, PATH),
    (0.01, PATH[:-1] + ['missing']), (0.01, ['text']),
    (0.01, ['executionSpec', 'factors', -1]), (0.01, ['executionSpec', 'factors', True]),
    ([], ['executionSpec', 'factors', 0, 'control', 'parameters'])])
def test_wrong_type_value_path_or_empty_field_rejected(value, path):
    assert validate_design_audit(group_claim(), verdict(value, path), []) == ['intervention_levels']


def test_foreign_claim_wrong_role_and_invalid_spec_cannot_supply_binding():
    claim = group_claim()
    audit = verdict()
    audit['designAudit']['intervention_levels']['fields'][0]['claimId'] = 'foreign'
    assert validate_design_audit(claim, audit, []) == ['intervention_levels']
    for kind in ('reported', 'inference'):
        foreign = {**claim, 'claimId': 'foreign', 'kind': kind}
        assert validate_design_audit(claim, audit, [foreign]) == ['intervention_levels']
    invalid = group_claim('epsilon')
    assert validate_design_audit(invalid, verdict('epsilon'), []) == ['intervention_levels']
    audit = verdict()
    audit['designAudit']['group_construction'] = audit['designAudit']['intervention_levels']
    assert validate_design_audit(claim, audit, []) == ['group_construction']


def test_fields_cannot_hide_invalid_segments_or_mix_forms():
    audit = verdict()
    fields = audit['designAudit']['intervention_levels']['fields']
    fields.append({**fields[0], 'value': 99})
    assert validate_design_audit(group_claim(), audit, []) == ['intervention_levels']
    audit = verdict()
    audit['designAudit']['intervention_levels']['quote'] = 'not allowed'
    assert validate_design_audit(group_claim(), audit, []) == ['intervention_levels']


def test_exact_field_does_not_override_semantic_rejection():
    import json
    def invoke(**kwargs):
        audit = verdict()
        audit.update(status='failed', reason='Intervention does not answer the question')
        return {'content': json.dumps([audit])}
    result = BudgetedSemanticChecker(invoke, 'r')([group_claim()], [])
    assert result[0]['status'] == 'failed'


def test_verification_view_only_removes_exact_generated_suffix():
    from services.deep_research.execution_materialization import materialize_execution_claim, verification_claim_view
    original = group_claim()
    original['text'] = 'Contradictory original says threshold 99; preserve for review.'
    materialized = materialize_execution_claim(original)
    before = deepcopy(materialized)
    view = verification_claim_view(materialized)
    assert view['text'] == original['text']
    assert view['executionSpec'] == original['executionSpec']
    assert materialized == before
    changed = {**materialized, 'text': materialized['text'] + ' conflicting appended instruction'}
    assert verification_claim_view(changed) == changed
    assert verification_claim_view(original) == original
