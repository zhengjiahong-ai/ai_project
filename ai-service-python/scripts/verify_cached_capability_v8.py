"""Replay unchanged v7 JSON in current native retrieval/validation; no Provider.

This is offline compatibility and partial-result verification, not a new live
generation or a change to the original failed operation receipts.
"""
import hashlib
import json
import sys
from unittest.mock import patch

from llm.client import DeepSeekLLM
from rag.store import get_rag, is_rag_available
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import _compare, _critique

recorded = json.load(sys.stdin)
rag = get_rag()
assert is_rag_available(rag)

def snapshot():
    saved = rag.collection.get(include=['documents', 'metadatas'])
    rows = sorted(zip(saved['ids'], saved['documents'], saved['metadatas']))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

before = snapshot()
cached = [row['response'] for row in recorded['cache']['cacheRows'] if isinstance(row['response'], dict)]
results = {}
for kind, marker in [('critique', 'findings'), ('compose', 'dimensions')]:
    raw = next(item for item in cached if marker in item)
    case = next(item for item in recorded['plan']['cases'] if item['id'] == f'stage4-{kind}-v7')
    papers = [item['pdfId'] for item in recorded['plan']['materials']]
    request = ConversationCapabilityRequest(taskId='offline-v8-no-publish', capability=kind, message=case['prompt'],
                                             allowedPaperIds=[papers[1]] if kind == 'critique' else papers,
                                             primaryPaperId=papers[1] if kind == 'critique' else papers[0],
                                             steps=[] if kind == 'critique' else ['chat', 'compare'])
    raw_before = json.dumps(raw, sort_keys=True)
    with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider invocation forbidden')),
          patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(raw)) as substitute):
        result = _critique(request, papers[1]) if kind == 'critique' else _compare(request, [])
    assert substitute.call_count == 1 and result['partial']
    assert json.dumps(raw, sort_keys=True) == raw_before
    assert '未验证合成目标级数据集' not in result['message'] and '3.8MB' not in result['message']
    results[kind] = result
after = snapshot()
assert before == after
print(json.dumps({'scope': __doc__, 'providerCalls': 0, 'taskWrites': 0, 'indexWrites': 0,
                  'beforeHash': before, 'afterHash': after, 'results': results}, ensure_ascii=False))
