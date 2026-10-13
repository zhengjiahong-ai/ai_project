from unittest.mock import Mock, patch

import pytest

from schemas.requests import TermExplainRequest
from services.term_explanation_service import _definition_evidence, explain_term


def document(index, text, pdf='paper', section='Gaussian Pruning'):
    return {'text': text, 'metadata': {'id': pdf, 'chunk_index': index, 'section_title': section}}


def test_adjacent_definition_keeps_late_factors_and_saved_source_matches_input():
    anchor = document(8, 'Global significance uses transmittance T and opacity.\nEquation: GS = opacity T gamma.')
    neighbour = document(9, 'Context. ' * 75 + 'The volume is normalized by the 90% reference, clipping to 0 and 1.\n'
                         'Equation: gamma = V_norm beta.\nEquation: V_norm = min(volume/reference, 1).')
    rag = Mock()
    rag.get_documents_by_metadata.return_value = [anchor, neighbour]
    with patch('services.term_explanation_service.get_rag', return_value=rag), \
         patch('services.term_explanation_service.build_retrieval_queries', return_value={}), \
         patch('services.term_explanation_service._judge_and_retry_evidence', return_value=([], '', {})) as retrieval, \
         patch('services.term_explanation_service._call_guarded_llm', return_value='模拟解释') as model:
        result = explain_term(TermExplainRequest(term='significance', context='Current page.', pdfId='paper'))
    prompt = model.call_args.args[0]
    assert model.call_count == 1
    assert 'clipping to 0 and 1' in prompt and 'gamma = V_norm beta' in prompt
    assert 'transmittance T' in prompt
    assert '[TRUNCATED FOR SAFETY BUDGET]' not in prompt
    assert any('V_norm = min' in source['text'] for source in result['rag_sources'])
    assert retrieval.call_args.kwargs['material_scope'].allowed_ids == ('paper',)
    assert len(result['rag_sources']) <= 5
    assert sum(len(source['text']) for source in result['rag_sources']) <= 4500


@pytest.mark.parametrize('bad', [document(2, 'significance', pdf='other'),
    {'pdfId': 'paper', 'text': 'significance', 'metadata': {'id': 'other'}}])
def test_foreign_or_conflicting_original_identity_is_rejected_before_explanation(bad):
    rag = Mock()
    rag.get_documents_by_metadata.return_value = [bad]
    with patch('services.term_explanation_service.get_rag', return_value=rag), \
         patch('services.term_explanation_service.build_retrieval_queries', return_value={}), \
         patch('services.term_explanation_service._judge_and_retry_evidence', return_value=([], '', {})), \
         patch('services.term_explanation_service._call_guarded_llm') as model:
        with pytest.raises(ValueError, match='当前论文'):
            explain_term(TermExplainRequest(term='significance', pdfId='paper'))
    model.assert_not_called()


def test_corpus_failure_keeps_in_scope_retrieval_and_does_not_request_another_paper():
    rag = Mock()
    rag.get_documents_by_metadata.side_effect = RuntimeError('Unavailable')
    retrieved = [{'sourceId':'paper:2', 'pdfId':'paper', 'text':'Definition of significance.'}]
    with patch('services.term_explanation_service.get_rag', return_value=rag):
        result = _definition_evidence(retrieved, 'paper', 'significance')
    assert result[0]['sourceId'] == 'paper:2'
    rag.get_documents_by_metadata.assert_called_once_with({'id':'paper'}, limit=400)


def test_current_paper_is_not_filled_with_unknown_or_foreign_retrieved_evidence():
    rag = Mock()
    rag.get_documents_by_metadata.return_value = []
    with patch('services.term_explanation_service.get_rag', return_value=rag):
        with pytest.raises(ValueError, match='当前论文'):
            _definition_evidence([{'text':'Foreign definition.', 'pdfId':'other'}], 'paper', 'definition')


def test_neighbours_in_other_sections_are_not_promoted_as_the_term_definition():
    rag = Mock()
    rag.get_documents_by_metadata.return_value = [document(1, 'significance\nEquation: score = T opacity.'),
        document(2, 'Unrelated background concept.', section='Related Work')]
    with patch('services.term_explanation_service.get_rag', return_value=rag):
        result = _definition_evidence([], 'paper', 'significance')
    assert len(result) == 1 and result[0]['chunkIndex'] == 1
