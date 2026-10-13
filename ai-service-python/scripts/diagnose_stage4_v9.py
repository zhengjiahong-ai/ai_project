"""Replay unchanged v9 critique JSON on actual current retrieval, no generation."""
import json
import sys
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import _critique
from services import grounded_critique

data = json.load(sys.stdin)
raw = next(row['response'] for row in data['cache']['cacheRows']
           if isinstance(row['response'], dict) and 'findings' in row['response'])
case = data['plan']['cases'][0]
paper = data['plan']['materials'][1]['pdfId']
request = ConversationCapabilityRequest(taskId='offline-v9-diagnosis-no-publish', capability='critique',
    message=case['prompt'], allowedPaperIds=[paper], primaryPaperId=paper, strictScope=True)
original = grounded_critique.check_critique_payload
reasons = []
def inspect(*args, **kwargs):
    result = original(*args, **kwargs)
    reasons.extend(kwargs.get('rejected') or [])
    return result
before = json.dumps(raw, sort_keys=True)
with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(raw)) as substitute,
      patch.object(grounded_critique, 'check_critique_payload', side_effect=inspect)):
    result = _critique(request, paper)
assert substitute.call_count == 1 and result['partial']
assert before == json.dumps(raw, sort_keys=True)
print(json.dumps({'providerCalls': 0, 'taskWrites': 0, 'originalResponseUnchanged': True,
                  'rejectedReasons': reasons, 'resultStillPartial': True}, ensure_ascii=False))
