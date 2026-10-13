"""Replay the archived single critique with Provider disabled; explain rejection."""
import json
import sys
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation
from services.grounded_critique import check_critique_payload

archive = json.load(sys.stdin)
row = archive['cacheRows'][0]
diagnostics = []


def inspect(payload, sources, catalog, **kwargs):
    for index, finding in enumerate(payload['findings']):
        try:
            check_critique_payload({'findings': [finding], 'pendingQuestions': []}, sources, catalog)
            reason = None
        except ValueError as error:
            reason = str(error)
        quotes = []
        for reference in finding.get('references', []):
            matches = [(source_id, values[reference['quoteId']]) for source_id, values in catalog.items()
                       if reference['quoteId'] in values]
            assert len(matches) == 1
            quotes.append({'sourceId': matches[0][0], 'quote': matches[0][1]})
        diagnostics.append({'findingIndex': index, 'summary': finding['summary'],
                            'kind': finding['kind'], 'rejection': reason, 'selectedQuotes': quotes})
    return check_critique_payload(payload, sources, catalog, **kwargs)


paper = row['inputVerification']['allowedPaperIds'][0]
request = ConversationCapabilityRequest(taskId='stage4-3dgs-critique-20261010-v18', capability='critique',
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
assert len(diagnostics) == 7
print(json.dumps({'providerCalls': 0, 'taskWrites': 0, 'originalResponseUnchanged': True,
                  'publicContentReplayMatches': True, 'findings': diagnostics}, ensure_ascii=False))
