"""Replay the exact v19 response to verify only its chat summary changes."""
import hashlib
import json
import sys
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation
from services.safety_service import build_guarded_messages

row = json.load(sys.stdin)['cacheRows'][0]
papers = row['inputVerification']['allowedPaperIds']
request = ConversationCapabilityRequest(taskId='stage4-3dgs-critique-20261010-v19',
    capability='critique',
    message='重点批判LightGaussian的15倍压缩与200+FPS主张：证据适用于哪些场景、比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？',
    allowedPaperIds=papers, primaryPaperId=papers[0], strictScope=True)

def original_response(prompt, extra_system_instruction=''):
    system = build_guarded_messages(prompt, extra_system_instruction=extra_system_instruction)[0]['content']
    assert hashlib.sha256(prompt.encode()).hexdigest() == row['userPromptHash']
    assert hashlib.sha256(system.encode()).hexdigest() == row['systemPromptHash']
    return row['rawResponse']

with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch('services.socratic_service._call_guarded_llm', side_effect=original_response) as model):
    result = execute_conversation(request)
old = row['nativeReplay']
assert model.call_count == 1
assert result['artifact'] == old['artifact']
for field in ('partial', 'capability', 'materialScope', 'sources'):
    assert result[field] == old[field], field
assert '17.38' not in old['message'] and '17.38' in result['message']
assert '237' in result['message'] and '质量代价' in result['message']
assert result['message'].startswith('部分结果：') and len(result['message']) <= 600
assert '原文依据' not in result['message']
print(json.dumps({'oldMessage': old['message'], 'newMessage': result['message'],
    'oldMessageChars': len(old['message']), 'newMessageChars': len(result['message']),
    'artifactUnchanged': True, 'sourcesAndScopeUnchanged': True,
    'partial': result['partial'], 'exactPromptMatched': True,
    'providerCalls': 0, 'taskWrites': 0}, ensure_ascii=False))
