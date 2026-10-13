from unittest.mock import patch
from types import SimpleNamespace
import pytest

from services.focused_evidence import select_focused_evidence, bounded_evidence_body
from services.analysis_service import _build_axis_query_plan, _build_axis_query, _retrieve_axis_evidence, _load_analysis_source
from schemas.requests import DeepAnalysisRequest
from rag.store import retrieve_fused_evidence


def item(index, section, text):
    return {'sourceId': f'A:{index}', 'pdfId': 'A', 'chunkIndex': index, 'text': text,
            'metadata': {'section_title': section}}


def test_method_context_keeps_adjacent_definitions_and_distinct_requested_modules():
    corpus = [item(1, 'Introduction', 'Pruning, spherical harmonics and quantization achieve compression.'),
        item(10, 'Pruning', 'The significance score is defined using the hit count.'),
        item(11, 'Pruning', 'Transmittance and adjusted volume are calculated for pruning.'),
        item(12, 'Pruning', 'Pruning Equation: S = count * T * volume. Equation: normalized volume.'),
        item(20, 'SH Distillation', 'Spherical harmonics distillation recovers the reduced coefficients.'),
        item(30, 'Vector Quantization', 'Quantization uses a feature codebook.')]
    selected = select_focused_evidence(corpus[:1], corpus, '剪枝、球谐蒸馏和量化', 'methods', limit=6)
    assert {10, 11, 12, 20, 30} <= {row['chunkIndex'] for row in selected}
    assert len(selected) <= 6
    assert all(row in corpus for row in selected)


def test_experiment_context_keeps_hardware_dataset_and_results_in_separate_originals():
    corpus = [item(1, 'Introduction', 'We achieve 200 FPS.'),
        item(10, 'Experimental Settings', 'Implementation details: all runs use GPU A.'),
        item(11, 'Experimental Settings', 'The dataset is benchmark B; the baseline is retrained.'),
        item(20, 'Experimental Results', 'Table 1: measured PSNR and FPS on dataset B.'),
        item(21, 'Ablation Studies', 'Ablation tests remove individual modules.')]
    selected = select_focused_evidence(corpus[:1], corpus, '比较实验速度和数据集', 'experiments', limit=6)
    assert {10, 11, 20, 21} <= {row['chunkIndex'] for row in selected}


def test_broad_comparison_keeps_method_definitions_beyond_the_one_named_concept():
    corpus = [item(10, 'Pruning', 'The significance score uses the hit count.'),
        item(11, 'Pruning', 'Transmittance and normalized volume are defined here.'),
        item(12, 'Pruning', 'Equation: significance = count * T. Equation: normalized volume. Equation: pruning.'),
        item(20, 'SH Distillation', 'Spherical harmonics distillation reduces coefficients.'),
        item(30, 'Vector Quantization', 'Quantization uses a feature codebook.'),
        item(40, 'Experimental Settings', 'GPU A; dataset B; baseline C.'),
        item(50, 'Experimental Results', 'PSNR and FPS measured on dataset B.'),
        item(60, 'Ablation Studies', 'Ablation compares the individual modules.')]
    selected = select_focused_evidence([corpus[3], corpus[-1]], corpus,
                                      '比较球谐颜色、质量和渲染速度', 'compare', limit=10)
    assert {10, 11, 12, 20, 30, 40, 50, 60} <= {row['chunkIndex'] for row in selected}
    assert len(selected) <= 10


def test_generic_axes_retain_section_diversity():
    corpus = [item(i, 'Intro' if i < 3 else 'Results', 'Original text') for i in range(4)]
    selected = select_focused_evidence(corpus, [], '', 'methods', limit=6)
    assert [row['chunkIndex'] for row in selected] == [0, 3]


def test_main_comparison_table_method_rows_win_over_repeated_headers_and_ablation():
    setup = item(1, 'Experimental Settings', 'Implementation details: GPU A; dataset B; baseline retrained.')
    header = item(10, 'Table 1 Quantitative Comparisons', 'Method | FPS | PSNR | dataset B; unrelated methods only.')
    result = item(11, 'Table 1 Quantitative Comparisons', 'Method | FPS | PSNR; Baseline * | 100 | 25; Ours | 200 | 26')
    ablation = item(12, 'Table 2 Ablation', 'Ablation: FPS PSNR dataset baseline quantization significance.')
    for row in [header, result, ablation]:
        row['metadata']['evidence_kind'] = 'table'
    selected = select_focused_evidence([ablation, header], [setup, header, result, ablation],
                                       '比较质量和速度', 'compare', limit=4)
    assert {1, 11, 12} <= {row['chunkIndex'] for row in selected}
    assert len(selected) <= 4


def test_window_keeps_late_conditions_as_one_literal_excerpt_with_the_old_budget():
    source = 'Paper: title\n\nSection: Results\n\nContent:\n' + 'Background only. ' * 150 + '\nEquation: score definition. GPU A; dataset B; baseline C; 100 FPS.'
    body = bounded_evidence_body(source, 300)
    assert 'GPU A' in body and 'Equation:' in body
    assert len(body) <= 300 and body in source
    assert '...' not in body


def test_critique_uses_deterministic_focus_terms_without_translating_the_query():
    axis = {'key': 'methods', 'question': '方法是什么', 'retrieval_question': 'method definition evidence',
            'focus_question': '剪枝重要性', 'seed_terms': []}
    plan = _build_axis_query_plan(axis)
    query = _build_axis_query(plan, axis)
    assert 'pruning' in query and 'significance' in query and '剪枝' not in query
    with patch('services.analysis_service.retrieve_fused_evidence', return_value=[]) as retrieve:
        _retrieve_axis_evidence([], plan, axis, pdf_id='A')
    assert retrieve.call_args.kwargs['allow_query_rewrite'] is False


@pytest.mark.parametrize('identity', [{'pdfId': 'B'}, {'metadata': {'id': 'B'}},
                                    {'pdfId': 'A', 'metadata': {'pdf_id': 'B'}}])
def test_scoped_critique_rejects_foreign_retrieval_before_using_it(identity):
    with patch('services.analysis_service.retrieve_fused_evidence', return_value=[
        {'text': 'Foreign definition', **identity}]):
        with pytest.raises(ValueError, match='之外'):
            _retrieve_axis_evidence([], {'rewritten': 'method'}, {'key': 'methods'}, pdf_id='A')


def test_scoped_critique_rejects_foreign_corpus_before_normalization():
    rag = SimpleNamespace(get_documents_by_metadata=lambda *a, **kw: [
        {'text': 'Foreign definition', 'metadata': {'id': 'B'}}])
    with patch('services.analysis_service.get_rag', return_value=rag):
        with pytest.raises(ValueError, match='之外'):
            _load_analysis_source(DeepAnalysisRequest(pdf_id='A'))


def test_store_passes_no_rewrite_through_to_hybrid_without_changing_other_defaults():
    calls = []
    hybrid = SimpleNamespace(retrieve=lambda *args, **kwargs: calls.append(kwargs) or {'fused': [{'text': 'body'}]})
    with patch('rag.store.get_hybrid', return_value=hybrid):
        retrieve_fused_evidence('剪枝', filter_metadata={'id': 'A'}, allow_query_rewrite=False)
        retrieve_fused_evidence('other query', filter_metadata={'id': 'A'})
    assert calls[0]['allow_query_rewrite'] is False
    assert 'allow_query_rewrite' not in calls[1]
