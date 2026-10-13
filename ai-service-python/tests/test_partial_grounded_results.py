import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from services.evidence_quotes import prepare_quote_sources
from services.grounded_critique import synthesize_critique
from services.grounded_comparison import synthesize_comparison

SOURCES = [{'sourceId': 'a', 'pdfId': 'A', 'text': 'Pruning reduces storage with a quality tradeoff.'},
           {'sourceId': 'b', 'pdfId': 'B', 'text': 'The original method optimizes anisotropic Gaussians.'}]


def refs():
    _, _, catalog = prepare_quote_sources(SOURCES)
    return {sid: [{'sourceId': sid, 'quoteId': next(iter(catalog[sid]))}] for sid in catalog}


def test_partial_critique_keeps_valid_claim_and_never_rewords_invalid_absence_into_fact():
    references = refs()
    valid = {'section': 'weakness', 'kind': 'inference', 'summary': '剪枝需要评估质量代价。', 'references': references['a']}
    invalid = {**valid, 'summary': '论文未验证动态场景。'}
    value = {'findings': [invalid, valid]}
    before = deepcopy(value)
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)) as provider:
        result = synthesize_critique('剪枝局限', [SOURCES[0]], allow_partial=True)
    assert provider.call_count == 1 and value == before
    assert result['partial'] and '部分分析' in result['summary']
    assert [claim['summary'] for claim in result['groundedClaims']] == [valid['summary']]
    assert '未验证动态场景' not in result['message']
    assert '另有1项判断暂未确认' in result['message'] and '<details>' in result['message']


def comparison_payload():
    references = refs()
    cells = [{'paperId': 'A', 'kind': 'reported', 'summary': '剪枝压缩表示。', 'references': references['a']},
             {'paperId': 'B', 'kind': 'reported', 'summary': '原始方法优化各向异性高斯。', 'references': references['b']}]
    return {'claims': [], 'dimensions': [{'label': '方法', 'cells': cells}]}


def test_partial_comparison_preserves_both_papers_and_marks_bad_cell_without_fake_citation():
    value = comparison_payload()
    value['dimensions'][0]['cells'][0]['summary'] = '达到999FPS。'
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)) as provider:
        result = synthesize_comparison('比较', SOURCES, ['A', 'B'], allow_partial=True)
    cells = result['comparisonTable'][0]['cells']
    assert provider.call_count == 1 and result['partial']
    assert [cell['paperId'] for cell in cells] == ['A', 'B']
    assert cells[0]['summary'] == '该项暂无法核验。' and cells[0]['references'] == []
    assert cells[0]['verificationStatus'] == 'rejected'
    assert result['claims'] == [cells[1]]
    assert '999' not in result['message'] and '部分比较' in result['message']
    assert [source['pdfId'] for source in result['rag_sources']] == ['B']


def test_all_invalid_cells_do_not_publish_an_empty_success():
    value = comparison_payload()
    for cell in value['dimensions'][0]['cells']:
        cell['summary'] = '达到999FPS。'
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        with pytest.raises(ValueError, match='尚未形成可核验'):
            synthesize_comparison('比较', SOURCES, ['A', 'B'], allow_partial=True)


def test_all_invalid_critique_does_not_become_only_a_pending_question_success():
    value = {'findings': [{'section': 'weakness', 'kind': 'reported', 'summary': '论文未验证动态场景。', 'references': refs()['a']}],
             'pendingQuestions': [{'topic': '动态场景表现'}]}
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        with pytest.raises(ValueError, match='尚未形成可核验'):
            synthesize_critique('批判', [SOURCES[0]], allow_partial=True)


def test_partial_mode_does_not_accept_malformed_material_layout():
    value = comparison_payload()
    value['dimensions'][0]['cells'].pop()
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        with pytest.raises(ValueError, match='遗漏或重复'):
            synthesize_comparison('比较', SOURCES, ['A', 'B'], allow_partial=True)


def test_uncited_numeric_limitation_does_not_bypass_claim_validation():
    value = comparison_payload()
    value['limitations'] = ['模型压缩到999MB。', '比较需考虑训练设置。']
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        result = synthesize_comparison('比较', SOURCES, ['A', 'B'], allow_partial=True)
    assert result['partial'] and '999MB' not in result['message']
    assert '<summary>比较范围</summary>' in result['message'] and '比较需考虑训练设置' in result['message']


def test_conversation_keeps_partial_label_after_short_summary_and_artifact_creation():
    from schemas.conversation import ConversationCapabilityRequest
    from services.conversation_capability_service import execute_conversation
    request = ConversationCapabilityRequest(taskId='task', capability='compare', message='比较', allowedPaperIds=['A', 'B'])
    partial_result = {'status': 'success', 'partial': True, 'message': '**部分比较**\n\n核验结论。',
                      'summary': '**部分比较**\n\n核验结论。', 'rag_sources': []}
    with patch('services.conversation_capability_service._run_step', return_value=[partial_result]):
        result = execute_conversation(request)
    assert result['partial'] and result['message'].startswith('部分结果：')
    assert result['artifact']['partial'] and '部分比较' in result['artifact']['text']
