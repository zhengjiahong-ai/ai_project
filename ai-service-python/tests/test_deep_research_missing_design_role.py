import json
from unittest.mock import Mock
import pytest
from services.deep_research.verification import verify_claims
from services.deep_research.repair import repair_rejected


@pytest.mark.parametrize('role', [None, '', [], 'unsupported'])
def test_v2_proposal_cannot_bypass_design_checks_by_omitting_or_corrupting_role(role):
    claim = {'claimId': 'c', 'kind': 'proposal', 'text': 'Proposed controlled experiment',
             'designContractVersion': 2, 'evidenceRefs': []}
    if role is not None:
        claim['designRole'] = role
    checker = Mock(return_value=[{'claimId': 'c', 'status': 'passed'}])
    result = verify_claims([claim], [], checker)
    assert result['rejected'][0]['reason'] == 'invalid_design_role'
    checker.assert_not_called()


def test_missing_role_can_be_added_by_repair_and_is_checked_again():
    original = {'claimId': 'c', 'kind': 'proposal', 'text': 'Use equal checkpoints.',
                'designContractVersion': 2, 'evidenceRefs': []}
    def invoke(prompt):
        assert 'requires one designRole' in prompt and 'controls' in prompt
        assert 'structural rejection is not a content approval' in prompt
        assert 'image/view aggregation' in prompt
        assert 'Report the device, resolution, warmup' not in prompt
        assert 'per-group budgets' in prompt
        return {'content': json.dumps([{**original, 'designRole': 'controls'}])}
    revised = repair_rejected({'claims': [original]},
        {'rejected': [{'claimId': 'c', 'reason': 'invalid_design_role'}]}, [],
        'Design an experiment', invoke, json.loads, metric_domains=['quality'])
    assert revised[0]['designRole'] == 'controls'
    assert not verify_claims(revised, [])['accepted']
    checked = Mock(return_value=[{'claimId': 'c', 'status': 'passed'}])
    assert verify_claims(revised, [], checked)['accepted']
    checked.assert_called_once()


def test_legacy_proposal_is_not_retroactively_assigned_experiment_contract():
    claim = {'claimId': 'c', 'kind': 'proposal', 'text': 'Read the limitations.', 'evidenceRefs': []}
    assert verify_claims([claim], [], lambda *a: [{'claimId': 'c', 'status': 'passed'}])['accepted']
