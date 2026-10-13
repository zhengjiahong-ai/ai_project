"""Replay v19 verbatim; a separate handcrafted parameter example is not model output."""
import hashlib
import json
import sys
from copy import deepcopy
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation
from services.grounded_critique import check_critique_payload

row = json.load(sys.stdin)['cacheRows'][0]
papers = row['inputVerification']['allowedPaperIds']
captured = {}

def raw_response(prompt, extra_system_instruction=''):
    packet = json.loads(prompt.split('资料JSON：\n', 1)[1])
    assert {source['pdfId'] for source in packet['evidence']} == set(papers)
    assert [source['sourceId'] for source in packet['evidence']] == row['inputVerification']['sourceIds']
    captured['promptHash'] = hashlib.sha256(prompt.encode()).hexdigest()
    return row['rawResponse']

def inspect(payload, sources, catalog, **kwargs):
    captured.update(payload=deepcopy(payload), sources=sources, catalog=catalog)
    return check_critique_payload(payload, sources, catalog, **kwargs)

request = ConversationCapabilityRequest(taskId='stage4-3dgs-critique-20261010-v19',
    capability='critique',
    message='重点批判LightGaussian的15倍压缩与200+FPS主张：证据适用于哪些场景、比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？',
    allowedPaperIds=papers, primaryPaperId=papers[0], strictScope=True)
with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch('services.socratic_service._call_guarded_llm', side_effect=raw_response) as model,
      patch('services.grounded_critique.check_critique_payload', side_effect=inspect)):
    result = execute_conversation(request)
assert model.call_count == 1 and result['partial'] is True
assert captured['payload'] == row['response']
old = row['nativeReplay']
for field in ('sources', 'materialScope', 'capability'):
    assert result[field] == old[field], field
claims = result['steps'][0]['results'][0]['groundedClaims']
old_claims = old['steps'][0]['results'][0]['groundedClaims']
assert len(claims) == len(old_claims) == 7
for claim, original in zip(claims, old_claims):
    for key in ('kind', 'section', 'references'):
        assert claim[key] == original[key], key
assert '存储压缩17.38倍' in result['message'] and 'FPS 237' in result['message']
assert 'Datasets：' not in result['message'] and 'Size压缩' not in result['message']
assert len(result['message']) <= 600

# This explicit manual alteration exercises the original rejection boundary;
# it is never used to replace the real receipt, artifact or original response.
controlled = deepcopy(row['response'])
claim = controlled['assessments'][1]['inference']
qid = next(ref['quoteId'] for ref in claim['references'] if any(
    'normalized' in quotes.get(ref['quoteId'], '') and '90%' in quotes.get(ref['quoteId'], '')
    for quotes in captured['catalog'].values()))
claim['summary'] = claim['summary'].replace('90%', '⟦数值1⟧')
claim['numericBindings'] = [{'id': 1, 'kind': 'method_parameter', 'quoteId': qid,
                             'label': 'normalized', 'literal': '90%'}]
controlled_claims, _ = check_critique_payload(controlled, captured['sources'], captured['catalog'])
assert len(controlled_claims) == 8 and '90%' in controlled_claims[3]['summary']
rejected_mutations = []
for literal in ('95%', '90'):
    invalid = deepcopy(controlled)
    invalid['assessments'][1]['inference']['numericBindings'][0]['literal'] = literal
    try:
        check_critique_payload(invalid, captured['sources'], captured['catalog'])
    except ValueError as error:
        rejected_mutations.append({'literal': literal, 'reason': str(error)})
    else:
        raise AssertionError('Invalid parameter accepted')
assert row['response'] == captured['payload']
print(json.dumps({'originalResponseUnchanged': True, 'originalPartial': result['partial'],
    'originalPublishedClaims': len(claims), 'originalRejectedClaims': 1,
    'sourcesScopeRolesAndReferencesUnchanged': True, 'message': result['message'],
    'newPromptHash': captured['promptHash'], 'archivedPromptHash': row['userPromptHash'],
    'promptNote': 'New parameter example changes prompt; no exact-match or fresh model compliance claim.',
    'controlledExample': {'manualNotModelOutput': True, 'acceptedClaims': len(controlled_claims),
                          'rejectedMutations': rejected_mutations},
    'providerCalls': 0, 'taskWrites': 0}, ensure_ascii=False))
