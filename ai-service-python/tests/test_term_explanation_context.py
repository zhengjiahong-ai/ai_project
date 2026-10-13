from unittest.mock import patch
from rag.store import DummyRAG

from schemas.requests import TermExplainRequest
from services.term_explanation_service import explain_term


def test_repeated_term_does_not_crop_the_later_same_page_definition_twice():
    page = 'Figure caption: significance is discussed below. ' + 'Earlier material. ' * 174
    page += 'Global Significance Calculation. Transmittance T multiplies opacity and adjusted volume in GS_j.'
    assert 3000 < page.index('Transmittance T') < len(page) < 4500
    with patch('services.term_explanation_service.get_rag', return_value=DummyRAG()), \
         patch('services.term_explanation_service.build_retrieval_queries', return_value={}), \
         patch('services.term_explanation_service._judge_and_retry_evidence', return_value=([], 'current_paper', {})), \
         patch('services.term_explanation_service._call_guarded_llm', return_value='保存的模拟解释') as model:
        result = explain_term(TermExplainRequest(term='significance', context=page, pdfId='paper', pageNumber=4))
    assert result['explanation'] == '保存的模拟解释'
    assert model.call_count == 1
    prompt = model.call_args.args[0]
    assert 'Transmittance T multiplies opacity and adjusted volume in GS_j.' in prompt
    assert '[TRUNCATED FOR SAFETY BUDGET]' not in prompt


def test_oversized_selection_context_is_still_bounded_before_the_model():
    page = 'Selected metric. ' + 'Context. ' * 1000
    with patch('services.term_explanation_service.get_rag', return_value=DummyRAG()), \
         patch('services.term_explanation_service.build_retrieval_queries', return_value={}), \
         patch('services.term_explanation_service._judge_and_retry_evidence', return_value=([], 'current_paper', {})), \
         patch('services.term_explanation_service._call_guarded_llm', return_value='保存的模拟解释') as model:
        explain_term(TermExplainRequest(term='Selected metric', context=page, pdfId='paper'))
    prompt = model.call_args.args[0]
    assert page not in prompt
    assert 'Selected metric.' in prompt
