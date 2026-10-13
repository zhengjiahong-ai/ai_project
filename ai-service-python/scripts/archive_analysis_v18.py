"""Read the bounded plan's cached response and replay exact prompts, Provider disabled."""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.agent_grounded_answer import _extract_json_object
from services.conversation_capability_service import execute_conversation
from services.llm_cache import _build_cache_key, _cache_db_path
from services.safety_service import build_guarded_messages

plan = json.load(sys.stdin)
start = datetime.fromisoformat(plan['authorizedAt']).timestamp()
end = datetime.now(timezone.utc).timestamp()
db = sqlite3.connect('file:' + _cache_db_path() + '?mode=ro', uri=True)
rows = db.execute('SELECT key,model,temperature,system_prompt_hash,user_prompt_hash,response,created_at '
                  'FROM llm_cache WHERE created_at>=? AND created_at<? ORDER BY created_at', (start, end)).fetchall()
candidates = []
for key, model, temperature, system_hash, user_hash, response, created in rows:
    try:
        payload = _extract_json_object(response)
    except (ValueError, TypeError):
        continue
    if isinstance(payload, dict) and any(key in payload for key in ('findings', 'assessments', 'dimensions')):
        candidates.append({'cacheKey': key, 'model': model, 'temperature': temperature,
                           'systemPromptHash': system_hash, 'userPromptHash': user_hash,
                           'rawResponse': response, 'response': payload, 'createdAt': created})
assert len(candidates) == 1, 'Expected exactly one structured candidate; inspect before exporting'
papers = [item['pdfId'] for item in plan['materials']]
records = []
for case in plan['cases']:
    kind = case['capability']
    selected = [row for row in candidates if (
        any(key in row['response'] for key in ('findings', 'assessments'))
        if kind == 'critique' else 'dimensions' in row['response'])]
    assert len(selected) == 1
    row = selected[0]
    expected_papers = [papers[0]] if kind == 'critique' else papers
    captured = {}

    def cached_response(prompt, extra_system_instruction=''):
        packet = json.loads(prompt.split('资料JSON：\n', 1)[1])
        assert {source['pdfId'] for source in packet['evidence']} == set(expected_papers)
        system = build_guarded_messages(prompt, extra_system_instruction=extra_system_instruction)[0]['content']
        assert hashlib.sha256(prompt.encode()).hexdigest() == row['userPromptHash'], 'Prompt changed'
        assert hashlib.sha256(system.encode()).hexdigest() == row['systemPromptHash'], 'System changed'
        assert _build_cache_key(row['model'], row['temperature'], system, prompt) == row['cacheKey']
        captured.update(promptMatchesCache=True, allowedPaperIds=expected_papers,
                        sourceIds=[source['sourceId'] for source in packet['evidence']],
                        experimentFactOptions=sum(len(source.get('experimentFacts', [])) for source in packet['evidence']))
        return row['rawResponse']

    request = ConversationCapabilityRequest(taskId=case['taskId'], capability=kind, message=case['prompt'],
        allowedPaperIds=expected_papers, primaryPaperId=papers[0] if kind == 'critique' else papers[0],
        strictScope=kind == 'critique')
    with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
          patch('services.socratic_service._call_guarded_llm', side_effect=cached_response) as stub):
        try:
            result = execute_conversation(request)
        except ValueError as error:
            result = {'validationError': str(error)}
    assert stub.call_count == 1 and captured.get('promptMatchesCache')
    records.append({**row, 'capability': kind, 'requestId': case['requestId'],
                    'inputVerification': captured, 'nativeReplay': result})
print(json.dumps({'startUtc': datetime.fromtimestamp(start, timezone.utc).isoformat(),
                  'endUtc': datetime.fromtimestamp(end, timezone.utc).isoformat(),
                  'cacheRowsInWindow': len(rows), 'structuredRowsArchived': 1,
                  'ownership': 'Exact user/system prompt hashes and cache keys matched native approved-paper inputs',
                  'providerCalls': 0, 'taskWrites': 0, 'cacheRows': records}, ensure_ascii=False))
