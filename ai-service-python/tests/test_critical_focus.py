from unittest.mock import patch

from services.analysis_service import _build_axis_query_plan
from services.critical_reading import _generate_structured_critical_report
from core.pdf_quality import _format_axis_prompt_block


def test_focus_changes_retrieval_question_without_mutating_shared_axis():
    axis = {'question': '贡献是否有证据？', 'retrieval_question': 'method contribution evidence',
            'seed_terms': ['method'], 'focus_question': '全局最优性证明'}
    plan = _build_axis_query_plan(axis)
    assert '全局最优性证明' in plan['rewritten']
    assert 'method contribution evidence' in plan['rewritten']
    assert axis['retrieval_question'] == 'method contribution evidence'


def test_report_prompt_carries_focus_and_distinguishes_retrieval_gaps():
    with patch('services.critical_reading.get_structured_llm') as model:
        model.return_value._call.return_value = '{}'
        _generate_structured_critical_report([], 'body evidence', 'rag', focus_question='全局最优性证明')
    prompt = model.return_value._call.call_args.args[0]
    assert '全局最优性证明' in prompt
    assert '未检索到推导、曲线或实验不等于论文没有提供' in prompt
    assert 'User analysis focus' in prompt
    assert '不能把扩展到另一表示方法的压缩率' in prompt
    assert '求和范围' in prompt
    assert '三条以内结论' in prompt


def test_final_prompt_preserves_late_method_and_experimental_context():
    evidence = [{'sourceId': f's{i}', 'text': 'Intro context. ' * 40 +
        f'Hardware A6000; dataset Mip-NeRF360; baseline retrained; experiment {i}.',
        'sourceType': 'current_paper'} for i in range(6)]
    prompt = _format_axis_prompt_block({'label': '实验', 'evidence': evidence})
    assert 'Hardware A6000' in prompt
    assert 'experiment 5' in prompt
