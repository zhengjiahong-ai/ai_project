"""Replay the archived comparison through local validation; no provider or writes."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / 'ai-service-python'))
from services.grounded_comparison import synthesize_comparison
from services.research_synthesis import evidence_body, _flat

data = json.loads((HERE/'stage4-reading-v4-cached-responses.json').read_text(encoding='utf-8'))
attempt = json.loads((HERE/'stage4-compose-v4-attempt.json').read_text(encoding='utf-8'))
sources = [{'sourceId':sid,'pdfId':sid.split('-chunk-')[0],
            # The real comparison allows at most 24 chunks in a 24k character
            # budget. Use the conservative 1000-character body window here.
            'text':evidence_body(body)[:1000]} for sid,body in data['validationFullSources'].items()]
raw = data['composition']['response']
with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(raw,ensure_ascii=False)) as model:
    result=synthesize_comparison(attempt['request']['input']['message'],sources,
                                attempt['request']['input']['allowedPaperIds'])
assert model.call_count == 1  # Local mock response only; no model generation.
by_id={s['sourceId']:s for s in sources}
refs=[r for claim in result['claims'] for r in claim['references']]
assert all(8<=len(r['quote'])<=300 and _flat(r['quote']) in _flat(by_id[r['sourceId']]['text']) for r in refs)
receipt={'status':'passed','scope':'Offline replay of the same v4 raw provider output; not a new successful live receipt',
         'modelCalls':0,'liveTaskWrites':0,'sourceWindowChars':1000,'referencesAfterSplit':len(refs),
         'originalReferenceCount':len(data['quoteChecks']),'claims':result['claims'],
         'comparisonTable':result['comparisonTable'],'text':result['message']}
(HERE/'stage4-compose-v4-offline-replay.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:receipt[k] for k in ['status','modelCalls','liveTaskWrites','referencesAfterSplit','originalReferenceCount']}))
