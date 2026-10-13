import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from schemas.requests import DeepAnalysisRequest
from services import analysis_service
from services.evidence_quotes import prepare_quote_sources
from services.grounded_critique import check_critique_payload, synthesize_critique
from services.operation_control import OperationCancelled, cancellation_scope

SOURCES = [{'sourceId':'method','pdfId':'A.pdf',
            'text':'Pruning reduces storage while co-adaptation helps recover visual quality.'}]


def payload():
    _, sources, catalog = prepare_quote_sources(SOURCES)
    value = {'findings':[{'section':'weakness','summary':'剪枝的质量代价应与恢复步骤一起评估。','kind':'inference',
              'references':[{'sourceId':'method','quoteId':next(iter(catalog['method']))}]}],
             'pendingQuestions':[{'topic':'跨场景质量和完整消融比较条件'}]}
    return value, sources, catalog


def test_critique_uses_one_synthesis_with_literal_references_and_no_score():
    value, _, _ = payload()
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)) as model:
        result = synthesize_critique('批判剪枝和恢复', SOURCES)
    assert model.call_count == 1
    assert '待核查：跨场景质量' in result['message'] and '<details>' in result['message']
    assert result['groundedClaims'][0]['references'][0]['quote'] == SOURCES[0]['text']
    assert result['groundedClaims'][0]['kind'] == 'inference'
    assert result['message'].count(result['groundedClaims'][0]['summary']) == 1
    assert 'contributionScore' not in result and '_verifiedTable' not in result['rag_sources'][0]


def test_critique_accepts_quote_only_selection_and_requests_atomic_supported_mechanisms():
    value, _, _ = payload()
    for ref in value['findings'][0]['references']:
        ref.pop('sourceId')
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)) as model:
        result = synthesize_critique('批判剪枝和蒸馏', SOURCES)
    assert result['groundedClaims'][0]['references'][0]['sourceId'] == 'method'
    prompt = model.call_args.args[0]
    assert '每项只回答一个独立判断' in prompt
    assert 'references只写quoteId' in prompt
    assert '符号定义或师生关系本身不能支持采样分布' in prompt


@pytest.mark.parametrize('text', [
    '泛化结果不完整：扩展实验未提供质量、模型大小和完整基线数据。',
    '作者缺少动态场景验证。', '论文没有给出完整证明。'])
def test_retrieval_absence_is_not_published_as_a_paper_defect(text):
    value, sources, catalog = payload()
    value['findings'][0]['summary'] = text
    with pytest.raises(ValueError,match='不能把检索缺口'):
        check_critique_payload(value, sources, catalog)


def test_pending_question_cannot_smuggle_an_absence_assertion():
    value, sources, catalog = payload()
    value['pendingQuestions'][0]['topic'] = '为何作者未提供质量数据'
    with pytest.raises(ValueError,match='不能预设'):
        check_critique_payload(value, sources, catalog)


def test_numerical_criticism_requires_the_same_experiment_checks_as_comparison():
    from test_comparison_measurements import fixture
    raw, original = fixture()
    _, sources, catalog = prepare_quote_sources(list(original.values()))
    raw['section'] = 'contribution'
    for ref in raw['references']:
        quote = ref.pop('quote')
        ref['quoteId'] = next(qid for qid, text in catalog[ref['sourceId']].items() if text == quote)
    for ref in raw['measurements'][0]['conditionReferences']:
        quote = ref.pop('quote')
        ref['quoteId'] = next(qid for qid, text in catalog[ref['sourceId']].items() if text == quote)
    value = {'findings':[raw], 'pendingQuestions':[]}
    findings, _ = check_critique_payload(value, sources, catalog)
    assert {ref['sourceId'] for ref in findings[0]['references']} == {'t','h'}
    wrong = deepcopy(value)
    wrong['findings'][0]['measurements'][0]['baseline'] = 'Baseline'
    with pytest.raises(ValueError,match='基线版本'):
        check_critique_payload(wrong, sources, catalog)
    wrong = deepcopy(value)
    wrong['findings'][0].pop('measurements')
    with pytest.raises(ValueError,match='逐项实验条件|绑定校验'):
        check_critique_payload(wrong, sources, catalog)


def test_old_unstructured_report_is_rejected_without_rewriting_history():
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps({'critical_analysis':'论文没有提供基线。'})) as model:
        with pytest.raises(ValueError,match='格式无效'):
            synthesize_critique('批判', SOURCES)
    assert model.call_count == 1


def test_cancellation_after_model_return_does_not_publish():
    stopped = [False]
    value, _, _ = payload()
    def model(*args):
        stopped[0] = True
        return json.dumps(value)
    with pytest.raises(OperationCancelled), cancellation_scope(lambda:stopped[0]):
        with patch('services.socratic_service._call_guarded_llm',side_effect=model):
            synthesize_critique('批判', SOURCES)


def test_grounded_task_analysis_skips_legacy_report_and_second_claim_model():
    value, _, _ = payload()
    axis = {'key':'methods','evidence':SOURCES,'judge':{'verdict':'CORRECT'}}
    with (patch.object(analysis_service,'_load_analysis_source',return_value=([], 'rag', 'a.pdf','body')),
         patch.object(analysis_service,'_analyze_axis',return_value=axis),
         patch.object(analysis_service,'_generate_structured_critical_report') as legacy,
         patch.object(analysis_service,'_build_claim_support_items') as second,
         patch('services.socratic_service._call_guarded_llm',return_value=json.dumps(value)) as model):
        result = analysis_service.deep_analysis(DeepAnalysisRequest(pdf_id='A.pdf',focus_question='剪枝代价'),grounded=True)
    assert result['groundedClaims'] and model.call_count == 1
    legacy.assert_not_called()
    second.assert_not_called()


def test_foreign_critique_evidence_fails_before_provider():
    axis = {'key':'methods','evidence':[{**SOURCES[0],'pdfId':'B.pdf'}],'judge':{'verdict':'CORRECT'}}
    with (patch.object(analysis_service,'_load_analysis_source',return_value=([], 'rag', 'a.pdf','body')),
         patch.object(analysis_service,'_analyze_axis',return_value=axis),
         patch('services.socratic_service._call_guarded_llm') as model):
        with pytest.raises(ValueError,match='不属于指定论文'):
            analysis_service.deep_analysis(DeepAnalysisRequest(pdf_id='A.pdf'),grounded=True)
    model.assert_not_called()


@pytest.mark.parametrize('summary', ['最大体积归一化可避免漂浮高斯。',
                                     'maximum volume normalization is used.',
                                     '归一化参考是最大体积。',
                                     '按排序截断的最大值归一化即全局最大值归一化。'])
def test_sorting_reference_is_not_published_as_global_maximum(summary):
    original = [{'sourceId': 'parameter', 'pdfId': 'A.pdf',
                 'text': 'The volume is normalized by the 90% largest of all sorted Gaussians.'}]
    _, sources, catalog = prepare_quote_sources(original)
    value = {'findings': [{'section': 'weakness', 'summary': summary, 'kind': 'reported',
             'references': [{'quoteId': next(iter(catalog['parameter']))}]}]}
    with pytest.raises(ValueError, match='归一化参考'):
        check_critique_payload(value, sources, catalog)


@pytest.mark.parametrize('quote,summary', [
    ('The volume is normalized by the 90% largest of all sorted Gaussians.', '归一化采用按体积排序的参考值。'),
    ('The volume is normalized by the 90% largest of all sorted Gaussians.', '采用排序参考，而非最大体积归一化。'),
    ('The volume is normalized by the 90% largest of all sorted Gaussians.', '按排序截断的最大值归一化体积。'),
    ('The maximum volume is used for normalization.', '最大体积归一化。'),
])
def test_parameter_type_is_preserved_without_requiring_unrequested_percentages(quote, summary):
    _, sources, catalog = prepare_quote_sources([{'sourceId': 'p', 'pdfId': 'A.pdf', 'text': quote}])
    value = {'findings': [{'section': 'weakness', 'summary': summary, 'kind': 'reported',
             'references': [{'quoteId': next(iter(catalog['p']))}]}]}
    findings, _ = check_critique_payload(value, sources, catalog)
    assert findings[0]['summary'] == summary


@pytest.mark.parametrize('summary,reject', [
    ('高斯采样在训练位置附近，因此远离训练分布视角下的重建误差不由该损失直接约束。', True),
    ('高斯采样以训练位置为中心，训练分布与目标视角关系需要结合实际采样评估。', False),
])
def test_gaussian_sampling_does_not_establish_zero_loss_constraint(summary, reject):
    _, sources, catalog = prepare_quote_sources([{'sourceId': 'p', 'pdfId': 'A.pdf',
        'text': 'Camera positions are sampled around each training view according to a Gaussian distribution.'}])
    value = {'findings': [{'section': 'weakness', 'summary': summary, 'kind': 'inference',
             'references': [{'quoteId': next(iter(catalog['p']))}]}]}
    if reject:
        with pytest.raises(ValueError, match='高斯采样'):
            check_critique_payload(value, sources, catalog)
    else:
        findings, _ = check_critique_payload(value, sources, catalog)
        assert findings[0]['summary'] == summary
