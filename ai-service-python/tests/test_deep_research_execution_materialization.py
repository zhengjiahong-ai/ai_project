from copy import deepcopy
import json
from unittest.mock import Mock

from services.deep_research.execution_materialization import materialize_execution_claim
from services.deep_research.repair import repair_rejected
from services.deep_research.tools import BudgetedSemanticChecker
from services.deep_research.verification import verify_claims


def analysis_claim():
    return {'claimId': 'a', 'kind': 'proposal', 'designRole': 'analysis',
            'designContractVersion': 2, 'text': '拟估计条件效应与交互，尚未执行。', 'evidenceRefs': [],
            'executionSpec': {'effects': {'A_cond_B0': 'L10 - L00', 'I': 'L11 - L10 - L01 + L00'},
                'uncertainty': {'mode': 'paired_cluster_bootstrap', 'unit': '场景',
                                'repetitions': 999, 'confidence': 0.95, 'seed': 7},
                'decision': {'mode': 'interval_excludes_zero'}}}


def test_materialization_is_idempotent_and_retains_all_original_prose():
    original = analysis_claim()
    before = deepcopy(original)
    result = materialize_execution_claim(original)
    assert result['text'].startswith(original['text'])
    for value in ['L10 - L00', 'L11 - L10 - L01 + L00', '999', '95%', '7']:
        assert value in result['text']
    assert materialize_execution_claim(result) == result
    assert original == before


def test_compiled_formulas_are_available_as_fields_and_remain_in_published_text():
    target = materialize_execution_claim(analysis_claim())
    def invoke(**kwargs):
        supplied = json.JSONDecoder().raw_decode(kwargs['prompt'].split('Claims:\n', 1)[1])[0][0]
        assert supplied['text'] == analysis_claim()['text']
        assert supplied['executionSpec'] == target['executionSpec']
        return {'content': json.dumps([{'claimId': 'a', 'status': 'passed', 'designAudit': {
            slot: {'fields': [{'claimId': 'a', 'path': ['executionSpec', key],
                               'value': supplied['executionSpec'][key]}]}
            for slot, key in [('effects', 'effects'), ('uncertainty', 'uncertainty'),
                              ('decision_rule', 'decision')]}}])}
    accepted = verify_claims([target], [], BudgetedSemanticChecker(invoke, 'r'))['accepted']
    assert len(accepted) == 1 and accepted[0]['text'] == target['text']


def test_compilation_does_not_hide_conflicting_prose_or_force_semantic_pass():
    original = analysis_claim()
    original['text'] = '拟只重采样5次。'
    target = materialize_execution_claim(original)
    assert '重采样5次' in target['text'] and '999' in target['text']
    result = verify_claims([target], [], lambda *args: [{'claimId': 'a', 'status': 'failed',
                                                       'reason': 'Conflicting repetition counts.'}])
    assert not result['accepted']


def test_invalid_spec_and_legacy_claims_are_not_silently_rewritten():
    for update in [{'executionSpec': {}}, {'designContractVersion': 1}, {'kind': 'reported'}]:
        original = analysis_claim()
        original.update(update)
        assert materialize_execution_claim(original) == original


def test_repair_includes_protocol_before_reverification_and_length_check():
    original = analysis_claim()
    output = {key: value for key, value in original.items() if key != 'designContractVersion'}
    invoke = lambda prompt: {'content': json.dumps([output])}
    repaired = repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'a'}]}, [],
        '给出可执行分析方法', invoke, json.loads)
    assert len(repaired) == 1 and '999' in repaired[0]['text']
    assert repaired[0]['designContractVersion'] == 2
    short = repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'a'}]}, [],
        '20字以内', invoke, json.loads)
    assert short == []
