"""Inspect actual selected excerpts and original v13 IDs, without a Provider."""
import hashlib
import json
import re
import sys
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import _critique
from services import grounded_critique

data = json.load(sys.stdin)
before = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
paper = data['plan']['materials'][1]['pdfId']
case = next(case for case in data['plan']['cases'] if case['capability'] == 'critique')
raw = next(row['response'] for row in data['cache']['cacheRows'] if 'findings' in row['response'])
captured = {}
original_prepare = grounded_critique.prepare_quote_sources


def prepare(sources):
    result = original_prepare(sources)
    captured['catalog'] = result[2]
    return result


request = ConversationCapabilityRequest(taskId='offline-v15-no-publish', capability='critique',
    message=case['prompt'], allowedPaperIds=[paper], primaryPaperId=paper, strictScope=True)
with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(raw)) as stub,
      patch.object(grounded_critique, 'prepare_quote_sources', side_effect=prepare)):
    result = _critique(request, paper)
assert stub.call_count == 1 and result['partial'] is True
catalog = captured['catalog']
invalid = []
for index, finding in enumerate(raw['findings']):
    for ref in finding['references']:
        qid, sid = ref.get('quoteId'), ref.get('sourceId')
        owners = [owner for owner, quotes in catalog.items() if qid in quotes]
        if sid not in owners:
            invalid.append({'findingIndex': index, 'reference': ref, 'actualOwners': owners,
                            'quote': catalog[owners[0]][qid] if len(owners) == 1 else None})
mechanisms = [{'sourceId': sid, 'quoteId': qid, 'quote': quote}
              for sid, quotes in catalog.items() for qid, quote in quotes.items()
              if re.search(r'Equation:|normalized|clipping|transmittance|pseudo|intensity|'
                           r'co-adaptation|quantization|float16|Gaussian distribution', quote, re.I)]
assert before == hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
print(json.dumps({'providerCalls': 0, 'taskWrites': 0, 'rawResponseUnchanged': True,
                  'originalResponseStillPartial': True, 'invalidSelections': invalid,
                  'mechanismExcerptsActuallyShown': mechanisms}, ensure_ascii=False))
