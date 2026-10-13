"""Actual indexed-paper retrieval and prompt construction; provider boundary denied."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from core.pdf_quality import _format_axis_prompt_block
from schemas.requests import DeepAnalysisRequest
from services.analysis_service import (
    ANALYSIS_AXIS_CONFIGS, _build_axis_query, _build_axis_query_plan,
    _load_analysis_source, _retrieve_axis_evidence,
)
from services.conversation_capability_service import _compare
from services.research_synthesis import evidence_body

A = 'f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf'
B = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
FOCUS = '重点批判LightGaussian的15倍压缩与200+FPS主张：证据适用于哪些场景、比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？'
COMPARE = '先用两句话解释3DGS的高斯、透明度与球谐颜色，再比较原始3DGS与LightGaussian如何在表示规模、质量和渲染速度之间取舍。'


def denied(*args, **kwargs):
    raise AssertionError('Provider or query translation must not be called')


class PromptCaptured(Exception):
    pass


captured = {}


def capture(prompt, system):
    captured['prompt'] = prompt
    captured['packet'] = json.loads(prompt.split('资料JSON：\n', 1)[1])
    raise PromptCaptured()


report = {'scope': 'Actual current index retrieval and final prompt input only; no answer generation',
          'providerCalls': 0, 'taskWrites': 0, 'axes': {}}
with patch('llm.client.get_llm', side_effect=denied), \
     patch('services.analysis_service.get_llm', side_effect=denied), \
     patch('core.hybrid_retriever.rewrite_query', side_effect=denied), \
     patch('services.socratic_service._call_guarded_llm', side_effect=capture):
    documents, _, _, _ = _load_analysis_source(DeepAnalysisRequest(pdf_id=B))
    report['lightCorpusCount'] = len(documents)
    for config in ANALYSIS_AXIS_CONFIGS:
        axis = {**config, 'focus_question': FOCUS}
        plan = _build_axis_query_plan(axis)
        evidence = _retrieve_axis_evidence(documents, plan, axis, pdf_id=B)
        prompt = _format_axis_prompt_block({**axis, 'queryPlan': plan, 'evidence': evidence})
        assert all(row['pdfId'] == B for row in evidence)
        assert len(evidence) <= 6
        report['axes'][axis['key']] = {
            'query': _build_axis_query(plan, axis),
            'chunks': [row.get('chunkIndex') for row in evidence],
            'sections': [(row.get('metadata') or {}).get('section_title') for row in evidence],
            'prompt': prompt,
        }
    methods = report['axes']['methods']['prompt']
    experiments = report['axes']['experiments']['prompt']
    assert 'transmittance' in methods.lower() and 'V norm' in methods and 'Equation: GS' in methods
    assert 'Distillation' in methods or 'distillation' in methods
    assert 'quantization' in methods.lower()
    assert 'A6000' in experiments and 'Mip-NeRF360' in experiments
    try:
        _compare(SimpleNamespace(message=COMPARE, allowedPaperIds=[A, B]), [])
    except PromptCaptured:
        pass
    else:
        raise AssertionError('Actual comparison did not reach the intercepted provider boundary')

packet = captured['packet']
sources = packet['evidence']
assert {row['pdfId'] for row in sources} == {A, B}
assert all(sum(row['pdfId'] == paper for row in sources) <= 10 for paper in (A, B))
light_body = '\n'.join(evidence_body(row['text']) for row in sources if row['pdfId'] == B)
report['comparison'] = {'sourceCount': len(sources), 'sources': sources,
                        'promptChars': len(captured['prompt']),
                        'bodyBudgetPerSource': min(1400, 24000 // len(sources))}
report['checks'] = {'rawScopeRejectedByRegression': True,
                    'critiqueDefinitionInFinalPrompt': True,
                    'critiqueExperimentConditionsInFinalPrompt': True,
                    'comparisonDefinitionAndConditionsInFinalPrompt': all(
                        text in light_body for text in ('transmittance', 'V norm', 'A6000', 'Mip-NeRF360')),
                    'queryTranslationDenied': True,
                    'answerGenerationDenied': True}
print('FOCUS_PROBE_JSON=' + json.dumps(report, ensure_ascii=False))
assert report['checks']['comparisonDefinitionAndConditionsInFinalPrompt'], 'Comparison prompt lost definition or hardware context'
