import json
from copy import deepcopy
from unittest.mock import Mock

from services.deep_research.graph import make_synthesize_node
from services.deep_research.repair import repair_rejected
from services.deep_research.tools import BudgetedSemanticChecker
from services.deep_research.verification import verify_claims
from services.deep_research.reporting import render_report


def data_spec():
    return {'dataset': 'proposed dataset', 'scenes': {'mode': 'named', 'names': ['scene-a', 'scene-b']},
            'split': {'mode': 'every_nth', 'order': 'lexicographic image id', 'stride': 8, 'offset': 0},
            'seeds': [0, 1, 2], 'independentUnit': 'scene', 'replication': {'mode': 'fixed_checkpoint'}}


def claim(spec=None):
    return {'claimId': 'd', 'kind': 'proposal', 'text': 'Two named scenes use every eighth view.',
            'designRole': 'data', 'designContractVersion': 2, 'executionSpec': spec, 'evidenceRefs': []}


def test_vague_execution_spec_never_reaches_semantic_pass():
    checker = Mock(return_value=[{'claimId': 'd', 'status': 'passed'}])
    result = verify_claims([claim()], [], checker)
    assert not result['accepted']
    assert result['rejected'][0]['reason'] == 'incomplete_execution_spec'
    checker.assert_not_called()


def test_structural_configuration_does_not_bypass_semantic_rejection():
    target = claim(data_spec())
    result = verify_claims([target], [], lambda *_: [{'claimId': 'd', 'status': 'failed',
                                                   'reason': 'Text omits named scenes and seed protocol.'}])
    assert not result['accepted']
    assert result['rejected'][0]['reason'] == 'semantic_unresolved'


def test_checker_receives_spec_and_checks_prose_consistency():
    target = claim(data_spec())
    def invoke(**kwargs):
        assert 'executionSpec' in kwargs['prompt'] and 'scene-a' in kwargs['prompt']
        assert 'not contradict fields' in kwargs['prompt']
        assert 'concrete meaning and consistency' in kwargs['prompt']
        return {'content': json.dumps([{'claimId': 'd', 'status': 'failed', 'reason': 'inconsistent prose'}])}
    assert not verify_claims([target], [], BudgetedSemanticChecker(invoke, 'r'))['accepted']


def test_repair_cannot_drop_server_owned_contract():
    target = claim(data_spec())
    changed = {key: value for key, value in target.items() if key not in {'executionSpec', 'designContractVersion'}}
    revised = repair_rejected({'claims': [target]}, {'rejected': [{'claimId': 'd'}]}, [], '设计实验',
        lambda _: {'content': json.dumps([changed])}, json.loads)
    assert revised[0]['designContractVersion'] == 2
    checker = Mock()
    result = verify_claims(revised, [], checker)
    assert result['rejected'][0]['reason'] == 'incomplete_execution_spec'
    checker.assert_not_called()


def test_synthesis_stamps_contract_even_if_model_omits_it():
    record = {'question': '设计实验', 'state': {'outputKind': 'experiment_design', 'evidence': []}}
    target = {key: value for key, value in claim().items() if key != 'designContractVersion'}
    def update(_run, mutate, **kwargs):
        nonlocal record
        record = mutate(record)
        return deepcopy(record)
    result = make_synthesize_node(lambda *a, **kw: {'content': json.dumps({'claims': [target]})}, update)({'run_id': 'r'})
    assert result['report_version_id']
    assert record['state']['reportBody']['claims'][0]['designContractVersion'] == 2


def test_internal_spec_is_not_dumped_into_user_report():
    target = claim(data_spec())
    text = render_report({'claims': [target], 'outputKind': 'experiment_design'})
    assert target['text'] in text
    assert 'executionSpec' not in text and 'lexicographic image id' not in text


def test_complete_spec_can_pass_with_semantic_verdict_and_exact_prose_audit():
    target = claim(data_spec())
    target['evidenceRefs'] = ['dataset-source']
    evidence = [{'evidenceId': 'dataset-source', 'accessLevel': 'fulltext',
                 'verification': {'literal': 'passed'},
                 'quote': 'Dataset scenes: scene-a and scene-b.'}]
    target['text'] = ('拟使用 proposed dataset 的 scene-a、scene-b；按 image id 字典序，'
                      '零起始每8张的第0张为评估，其余为训练；种子0、1、2用于固定索引，'
                      '保持同一检查点，不将种子视为独立训练；独立单位为场景。')
    def invoke(**kwargs):
        return {'content': json.dumps([{'claimId': 'd', 'status': 'passed',
            'dataAvailability': {'evidenceId': 'dataset-source',
                'quote': 'Dataset scenes: scene-a and scene-b.', 'scopeQuote': 'Dataset scenes',
                'availableNames': ['scene-a', 'scene-b']},
            'designAudit': {slot: {'claimId': 'd', 'quote': target['text']}
                            for slot in ('scenes', 'split', 'seeds', 'sampling_unit')}}])}
    result = verify_claims([target], evidence, BudgetedSemanticChecker(invoke, 'r'))
    assert [x['claimId'] for x in result['accepted']] == ['d']
    assert result['accepted'][0]['executionSpec'] == data_spec()
    assert result['accepted'][0]['verification'] == 'proposal'
