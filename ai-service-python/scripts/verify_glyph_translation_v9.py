"""Current translation path with real repaired glyph input and old cached replies.

No new generation: this proves prompt coverage and guard preservation only.
"""
import hashlib
import json
import sys
from unittest.mock import patch

from schemas.requests import PageTranslationRequest
from services import page_translation_service as service
from llm.client import DeepSeekLLM

recorded = json.load(sys.stdin)
before = hashlib.sha256(json.dumps(recorded, sort_keys=True).encode()).hexdigest()
layout = recorded['glyphs']['requestLayout']
blocks = service._normalize_layout_blocks(layout)
source = next(block for block in blocks if 'transmittance' in block['text'])
context = next(item for item in source['mathContext'] if item['variable'] == 'T')
assert context['visibleOperators'] == ['product'] and context['structureVerified'] is False
assert 'Qji' not in service._build_structured_translation_prompt(3, '', [source])
cached = [item for row in recorded['cache']['cacheRows'] if isinstance(row['response'], dict)
          for item in row['response'].get('translatedBlocks', [])]
assert cached
prompts = []
def substitute(prompt, **kwargs):
    prompts.append(prompt)
    return json.dumps({'translatedBlocks': cached}, ensure_ascii=False)
request = PageTranslationRequest(pdfId=recorded['pdfId'], pageIndex=3,
                                pageText=recorded['glyphs']['pageText'], pageLayout=layout)
with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch.object(service, '_call_translation_with_timeout', side_effect=substitute)):
    result = service.translate_page(request)
assert result['status'] == 'partial' and source['id'] in result['missingBlockIds']
assert len(result['translatedBlocks']) == 3
assert any('"product"' in prompt and '"variable": "T"' in prompt for prompt in prompts)
assert len(prompts) == len(service._chunk_layout_blocks(blocks))
after = hashlib.sha256(json.dumps(recorded, sort_keys=True).encode()).hexdigest()
assert before == after
print(json.dumps({'scope': __doc__, 'providerCalls': 0, 'taskWrites': 0, 'cacheWrites': 0,
                  'beforeHash': before, 'afterHash': after, 'modelSubstitutions': len(prompts),
                  'context': context, 'resultStatus': result['status'],
                  'acceptedBlockIds': [item['id'] for item in result['translatedBlocks']],
                  'missingBlockIds': result['missingBlockIds'], 'sourceUnchanged': True}, ensure_ascii=False))
