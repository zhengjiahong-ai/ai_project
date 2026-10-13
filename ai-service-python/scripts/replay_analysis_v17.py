"""Replay unchanged v16 payloads after precision changes; never publish or invoke Provider."""
import hashlib
import json
import sys
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation

data = json.load(sys.stdin)
before = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
papers = [item['pdfId'] for item in data['plan']['materials']]
records = {}
for case in data['plan']['cases']:
    kind = case['capability']
    row = next(row for row in data['cache']['cacheRows'] if row['capability'] == kind)
    captured = {}

    def response(prompt, *_args):
        packet = json.loads(prompt.split('资料JSON：\n', 1)[1])
        captured['mechanismContext'] = [line for source in packet['evidence']
            for line in source['text'].splitlines() if 'transmittance' in line.lower()]
        return row['rawResponse']

    request = ConversationCapabilityRequest(taskId=case['taskId'], capability=kind, message=case['prompt'],
        allowedPaperIds=[papers[1]] if kind == 'critique' else papers,
        primaryPaperId=papers[1] if kind == 'critique' else papers[0], strictScope=kind == 'critique')
    with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
          patch('services.socratic_service._call_guarded_llm', side_effect=response) as stub):
        result = execute_conversation(request)
    assert stub.call_count == 1
    if kind == 'compare':
        assert result['artifact']['text'] == row['nativeReplay']['artifact']['text']
    else:
        assert 'Size为基线的0.1倍' not in result['artifact']['text']
        assert result['artifact']['text'].count('Size为基线的0.058倍') == 2
        assert captured['mechanismContext'], 'T definition must actually be available to generation'
    records[kind] = {'partial': result['partial'], 'message': result['message'],
                     'artifactText': result['artifact']['text'], **captured}
assert before == hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
print(json.dumps({'providerCalls': 0, 'taskWrites': 0, 'rawResponsesUnchanged': True,
                  'notNewModelAcceptance': True, 'critiqueStillRequiresSemanticRetest': True,
                  'checks': records}, ensure_ascii=False))
