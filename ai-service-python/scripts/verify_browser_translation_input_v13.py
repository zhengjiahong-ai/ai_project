"""Validate captured browser input and native prompt construction, no generation."""
import hashlib
import json
import re
import sys
from unittest.mock import patch
from llm.client import DeepSeekLLM
from schemas.requests import PageTranslationRequest
from services import page_translation_service as service

packet = json.load(sys.stdin)
original = json.dumps(packet, ensure_ascii=False, sort_keys=True)
capture, proxy = packet['capture'], packet['proxy']
request = PageTranslationRequest(**capture['request'])
assert request.pageIndex == 3
assert capture['method'] == 'POST' and capture['origin'] == 'http://127.0.0.1:5174'
assert proxy['capturedTranslationInputs'] == 1 and proxy['forwardedWrites'] == proxy['providerRequests'] == 0
assert proxy['blockedWrites'] == [{'method':'POST','path':'/api/translate-page'}]
file = next(row for row in proxy['getRequests'] if row['path'].endswith('/file'))
assert file['status'] == 200 and file['sha256'] + '.pdf' == request.pdfId
assert file['path'].startswith('/api/task-workspaces/stage6-paper-tools-20261008/materials/')
sources = [source for block in request.pageLayout['blocks'] for source in block.get('mathSources', [])]
tokens = [source['token'] for source in sources]
assert tokens == [f'⟦原式{i}⟧' for i in range(1,9)]
for source in sources:
    assert all(0 <= source['bbox'][axis] <= 1 for axis in ('left','top','width','height'))
    assert source['bbox']['width'] > 0 and source['bbox']['height'] > 0
with (patch.object(DeepSeekLLM,'invoke',side_effect=AssertionError('Provider forbidden')),
      patch.object(service,'_call_translation_with_timeout',side_effect=AssertionError('Generation forbidden'))):
    blocks = service._normalize_layout_blocks(request.pageLayout)
    batches = service._chunk_layout_blocks(blocks)
    prompts = [service._build_structured_translation_prompt(3,'',batch) for batch in batches]
assert len(blocks) == 4
normalized_tokens = re.findall(r'⟦原式\d+⟧','\n'.join(block['text'] for block in blocks))
assert normalized_tokens == tokens
transmittance = next(block for block in blocks if 'transmittance' in block['text'])
context = next(item for item in transmittance['mathContext'] if item['variable'] == 'T')
assert context['visibleOperators'] == ['product'] and context['structureVerified'] is False
assert any('"product"' in prompt and '"variable": "T"' in prompt and '"structureVerified": false' in prompt for prompt in prompts)
assert original == json.dumps(packet,ensure_ascii=False,sort_keys=True)
print(json.dumps({'scope':__doc__,'pdfId':request.pdfId,'pageIndex':3,'blocks':len(blocks),
 'markers':tokens,'mathContext':context,'promptBatchesPrepared':len(prompts),
 'sourcePdfBytes':file['bytes'],'browserInputCapturedOnce':True,'providerCalls':0,
 'taskWrites':0,'inputUnchanged':True,'inputDataSha256':hashlib.sha256(original.encode()).hexdigest()},ensure_ascii=False))
