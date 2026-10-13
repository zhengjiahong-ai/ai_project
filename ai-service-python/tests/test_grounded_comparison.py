import copy
import json
from unittest.mock import patch

import pytest

from services.grounded_comparison import synthesize_comparison, grounded_source_map
from services.operation_control import OperationCancelled, cancellation_scope

SOURCES = [{'sourceId': 'a-1', 'pdfId': 'A', 'text': 'We maximize the radar SINR subject to communication constraints.'},
           {'sourceId': 'b-1', 'pdfId': 'B', 'text': 'We maximize the mutual information under a minimum communication rate.'}]


def payload():
    cells = [{'paperId': paper, 'summary': text, 'kind': 'reported',
              'references': [{'sourceId': source['sourceId'], 'quote': source['text']}]}
             for paper, text, source in zip(['A', 'B'], ['雷达SINR', '互信息'], SOURCES)]
    return {'claims': [{'summary': '优化目标分别为雷达SINR与互信息。', 'kind': 'reported', 'paperIds': ['A', 'B'],
                        'references': [cell['references'][0] for cell in cells]}],
            'dimensions': [{'label': '优化目标', 'cells': cells}], 'limitations': ['实验条件不同，不能直接排名。']}


def call(value):
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        return synthesize_comparison('比较优化目标', SOURCES, ['A', 'B'])


def test_each_paper_and_cross_paper_claim_have_literal_quotes():
    result = call(payload())
    assert '| 优化目标 |' in result['message']
    assert '[1]' in result['message'] and '[2]' in result['message']
    assert '<details>' in result['message']
    assert {x['pdfId'] for x in result['rag_sources']} == {'A', 'B'}
    refs = grounded_source_map(result['claims'], result['message'])
    assert refs[0]['sourceIds'] == ['a-1', 'b-1']
    assert all(x['method'] == 'literal_quote' and 'confidence' not in x for x in refs)


@pytest.mark.parametrize('case', ['wrong_paper', 'missing_paper', 'invented_quote', 'omitted_cell', 'duplicate_cell'])
def test_invalid_evidence_cannot_become_a_comparison_result(case):
    value = payload()
    if case == 'wrong_paper':
        value['dimensions'][0]['cells'][0]['references'] = value['dimensions'][0]['cells'][1]['references']
    elif case == 'missing_paper':
        value['claims'][0]['references'] = value['claims'][0]['references'][:1]
    elif case == 'invented_quote':
        value['claims'][0]['references'][0]['quote'] = 'This invented quote does not occur in the paper.'
    elif case == 'omitted_cell':
        value['dimensions'][0]['cells'].pop()
    else:
        value['dimensions'][0]['cells'][1] = copy.deepcopy(value['dimensions'][0]['cells'][0])
    with pytest.raises(ValueError):
        call(value)


def test_unknown_cell_has_no_fake_claim_or_source():
    value = payload()
    value['claims'] = []
    value['dimensions'][0]['cells'][1].update(kind='not_covered', summary='原论文没有提供', references=[])
    result = call(value)
    assert '原论文没有提供' not in result['message']
    assert '当前正文片段未覆盖' in result['message']
    assert [x['pdfId'] for x in result['rag_sources']] == ['A']


def test_one_paper_may_report_a_baseline_comparison_without_other_paper_evidence():
    value = payload()
    value['claims'] = [{'summary': '该论文报告了与另一基线的对照。',
                       'kind': 'reported', 'paperIds': ['B'],
                       'references': value['dimensions'][0]['cells'][1]['references']}]
    result = call(value)
    assert result['claims'][0]['summary'] == value['claims'][0]['summary']
    value['claims'][0]['paperIds'] = ['A', 'B']
    with pytest.raises(ValueError, match='每篇论文提供原文依据'):
        call(value)


def test_uncited_scope_numbers_remain_rejected_including_table_identifiers():
    value = payload()
    value['limitations'] = ['表1还有其他结果。']
    with pytest.raises(ValueError, match='数字也需要逐项依据'):
        call(value)


def test_elliptical_quote_is_rejected_while_separate_literal_refs_are_accepted():
    sources = copy.deepcopy(SOURCES)
    sources[0]['text'] += ' Our second stage prunes redundant Gaussians after recovery.'
    value = payload()
    value['dimensions'][0]['cells'][0]['references'] = [{'sourceId':'a-1',
        'quote':'We maximize the radar SINR... Our second stage prunes redundant Gaussians'}]
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        with pytest.raises(ValueError, match='摘录无法在正文中找到'):
            synthesize_comparison('比较', sources, ['A', 'B'])
    value['dimensions'][0]['cells'][0]['references'] = [
        {'sourceId':'a-1', 'quote':'We maximize the radar SINR'},
        {'sourceId':'a-1', 'quote':'Our second stage prunes redundant Gaussians'},
    ]
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        result = synthesize_comparison('比较', sources, ['A', 'B'])
    assert len(result['comparisonTable'][0]['cells'][0]['references']) == 2


def test_cancelled_provider_response_is_not_published():
    cancelled = [False]
    def model(*args):
        cancelled[0] = True
        return json.dumps(payload())
    with patch('services.socratic_service._call_guarded_llm', side_effect=model):
        with pytest.raises(OperationCancelled), cancellation_scope(lambda: cancelled[0]):
            synthesize_comparison('比较', SOURCES, ['A', 'B'])


def test_comparison_prompt_retains_table_mapping_uncertainty():
    sources = copy.deepcopy(SOURCES)
    sources[0]['metadata'] = {'evidence_kind': 'table', 'table_column_mapping_unverified': True}
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(payload())) as llm:
        synthesize_comparison('比较', sources, ['A', 'B'])
    prompt = llm.call_args.args[0]
    packet = json.loads(prompt.split('资料JSON：\n', 1)[1])
    assert packet['evidence'][0]['evidenceKind'] == 'table'
    assert packet['evidence'][0]['tableColumnMappingUnverified'] is True
    assert '不能自行拆开合并单元格' in prompt
    assert '不否定verifiedTable白名单中的行' in prompt


def test_duplicate_source_ids_are_rejected_before_spending_a_model_call():
    sources = copy.deepcopy(SOURCES)
    sources[1]['sourceId'] = sources[0]['sourceId']
    with patch('services.socratic_service._call_guarded_llm') as provider:
        with pytest.raises(ValueError, match='标识重复'):
            synthesize_comparison('比较', sources, ['A', 'B'])
    provider.assert_not_called()


def test_comparison_can_select_excerpts_instead_of_regenerating_quotes():
    from services.evidence_quotes import prepare_quote_sources
    _, _, catalog = prepare_quote_sources(SOURCES)
    value = payload()
    for claim in [*value['claims'], *value['dimensions'][0]['cells']]:
        for ref in claim['references']:
            if 'quoteId' in ref:
                continue
            quote = ref.pop('quote')
            ref['quoteId'] = next(qid for qid, original in catalog[ref['sourceId']].items() if original == quote)
    result = call(value)
    assert result['claims'][0]['references'][0]['quote'] == SOURCES[0]['text']
    assert '[1]' in result['message'] and 'quoteId' not in result['message']


def test_quote_only_selection_still_enforces_per_paper_evidence_coverage():
    from services.evidence_quotes import prepare_quote_sources
    _, _, catalog = prepare_quote_sources(SOURCES)
    value = payload()
    for claim in [*value['claims'], *value['dimensions'][0]['cells']]:
        claim['references'] = [{'quoteId': next(qid for qid, original in catalog[ref['sourceId']].items()
                                                if original == ref['quote'])} for ref in claim['references']]
    assert {ref['sourceId'] for ref in call(value)['claims'][0]['references']} == {'a-1', 'b-1'}
    value['dimensions'][0]['cells'][0]['references'] = value['dimensions'][0]['cells'][1]['references']
    with pytest.raises(ValueError, match='其他论文'):
        call(value)


def test_comparison_scope_uses_plain_language_without_changing_raw_response():
    value = payload()
    value['limitations'] = ['主表的 tableColumnMappingUnverified 为 true，不能据此排序。',
                            '实验条件不同，不能直接排名。']
    before = copy.deepcopy(value)
    result = call(value)
    assert '主表的 表格列归属尚未核对，不能据此排序；实验条件不同，不能直接排名。' in result['message']
    assert 'tableColumnMappingUnverified' not in result['message'] and '。；' not in result['message']
    assert value == before


def test_scope_wording_does_not_rewrite_a_verified_mapping_flag():
    value = payload()
    value['limitations'] = ['tableColumnMappingUnverified=false']
    text = call(value)['message']
    assert '未标记原始表格列归属问题' in text
    assert 'tableColumnMappingUnverified' not in text and '表格列归属尚未核对' not in text


def test_bare_internal_scope_flag_is_not_published_even_inside_parentheses():
    value = payload()
    value['limitations'] = ['原始表格仍有未核对部分（tableColumnMappingUnverified）。',
                            'tableColumnMappingUnverified 只描述原始片段。']
    text = call(value)['message']
    assert 'tableColumnMappingUnverified' not in text
    assert '原始表格仍有未核对部分' in text


def test_summary_does_not_point_at_numbers_rejected_from_the_final_table():
    value = payload()
    value['claims'][0]['summary'] += '；具体数字见比较表。'
    value['dimensions'][0]['cells'][1]['summary'] = '质量达到99 PSNR。'
    before = copy.deepcopy(value)
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        result = synthesize_comparison('比较', SOURCES, ['A', 'B'], allow_partial=True)
    assert result['partial'] is True and '该项暂无法核验' in result['message']
    assert '具体数字见比较表' not in result['summary'] + result['message']
    assert '优化目标分别为雷达SINR与互信息' in result['summary']
    assert value == before


def test_summary_uses_valid_cells_when_all_top_level_claims_are_rejected():
    value = payload()
    value['claims'][0]['summary'] = '具体数字见比较表。'
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value)):
        result = synthesize_comparison('比较', SOURCES, ['A', 'B'], allow_partial=True)
    assert result['partial'] is True
    assert '雷达SINR' in result['summary'] and '互信息' in result['summary']
    assert '比较表' not in result['summary']
