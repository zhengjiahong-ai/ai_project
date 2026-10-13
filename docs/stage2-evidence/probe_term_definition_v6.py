"""Read current index and capture the native explanation prompt; no real answers."""
import json
from unittest.mock import patch

from llm.client import DeepSeekLLM
from rag.store import get_rag
from schemas.requests import TermExplainRequest
from services.evidence_service import normalize_evidence_items, format_evidence_context
from services.term_explanation_service import explain_term

PDF = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
rag = get_rag()
before = rag.collection.count()
documents = rag.get_documents_by_metadata({'id': PDF}, limit=400)
retrieved = normalize_evidence_items([d for d in documents if d['metadata']['chunk_index'] in (13,14,15)],
                                     pdf_id=PDF, source_type='current_paper')
old_input = format_evidence_context(retrieved, max_items=5, max_text_chars=600)
with (patch.object(DeepSeekLLM, '_call', side_effect=AssertionError('Provider boundary blocked')),
      patch('services.term_explanation_service.build_retrieval_queries', return_value={'source':'offline_fixture'}),
      patch('services.term_explanation_service._judge_and_retry_evidence', return_value=(retrieved,'current_paper',{})),
      patch('services.term_explanation_service._call_guarded_llm', return_value='离线夹具，不作回答质量验收。') as model):
    result = explain_term(TermExplainRequest(term='significance', context='Global Significance Calculation.',
                                           pdfId=PDF, pageNumber=4))
prompt = model.call_args.args[0]
checks = {'oldInputDropsVolumeEquations':'Equation: γ' not in old_input,
          'transmittanceDefinitionVisible':'transmittance T' in prompt,
          'volumeAdjustmentEquationsVisible':'Equation: γ' in prompt and 'Equation: V norm' in prompt,
          'normalizationClippingAndExponentVisible':all(s in prompt for s in ('normalized','90%','clipping','β')),
          'noSafetyBudgetTruncation':'[TRUNCATED FOR SAFETY BUDGET]' not in prompt,
          'samePaperSources':all(s['pdfId']==PDF for s in result['rag_sources']),
          'boundedSources':len(result['rag_sources'])<=5 and sum(len(s['text']) for s in result['rag_sources'])<=4500,
          'savedSourceHasSameEquations':any('Equation: γ' in s['text'] and 'Equation: V norm' in s['text'] for s in result['rag_sources']),
          'oneSynthesisCall':model.call_count==1,
          'indexUnchanged':rag.collection.count()==before}
record={'scope':'Current index, controlled retrieval and synthetic explanation; not model content acceptance',
        'checks':checks,'indexCount':before,'providerCalls':0,'taskWrites':0,'indexWrites':0,
        'oldInput':old_input,'finalPrompt':prompt,'result':result}
print('TERM_DEFINITION_V6_JSON='+json.dumps(record,ensure_ascii=False))
assert all(checks.values()), checks
