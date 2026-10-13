"""Inspect each archived atomic judgment; no Provider calls or task writes."""
import json
import sys
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation
from services.grounded_critique import _atomic_findings, check_critique_payload

archive = json.load(sys.stdin)
row = archive['cacheRows'][0]
diagnostics = []

def inspect(payload, sources, catalog, **kwargs):
    for index, finding in enumerate(_atomic_findings(payload)):
        try:
            checked, _ = check_critique_payload({'findings': [finding]}, sources, catalog)
            reason = None
        except ValueError as error:
            checked, reason = [], str(error)
        quotes = []
        for reference in finding.get('references', []):
            matches = [(sid, values[reference['quoteId']]) for sid, values in catalog.items()
                       if reference['quoteId'] in values]
            assert len(matches) == 1
            quotes.append({'sourceId': matches[0][0], 'quote': matches[0][1]})
        diagnostics.append({'index': index, 'kind': finding['kind'],
            'section': finding['section'], 'summary': finding['summary'],
            'rejection': reason, 'checked': checked, 'selectedQuotes': quotes})
    return check_critique_payload(payload, sources, catalog, **kwargs)

paper = row['inputVerification']['allowedPaperIds'][0]
request = ConversationCapabilityRequest(taskId=row['requestId'].removesuffix('-request'),
    capability='critique',
    message='重点批判LightGaussian的15倍压缩与200+FPS主张：证据适用于哪些场景、比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？',
    allowedPaperIds=[paper], primaryPaperId=paper, strictScope=True)
with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch('services.socratic_service._call_guarded_llm', return_value=row['rawResponse']) as model,
      patch('services.grounded_critique.check_critique_payload', side_effect=inspect)):
    result = execute_conversation(request)
assert model.call_count == 1
for field in ('message', 'partial', 'capability', 'materialScope'):
    assert result[field] == row['nativeReplay'][field], field
assert result['artifact']['text'] == row['nativeReplay']['artifact']['text']
print(json.dumps({'format': 'assessments' if 'assessments' in row['response'] else 'findings',
    'diagnostics': diagnostics, 'partial': result['partial'],
    'pendingQuestions': row['response'].get('pendingQuestions', []),
    'nativePublicResultMatches': True, 'providerCalls': 0, 'taskWrites': 0}, ensure_ascii=False))
