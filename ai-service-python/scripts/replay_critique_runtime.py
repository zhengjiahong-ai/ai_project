"""Replay exact provider cache entries with real retrieval. Never send a model request."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation
from services.llm_cache import _cache_db_path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('input')
parser.add_argument('output')
args = parser.parse_args()
packets = json.loads(Path(args.input).read_text(encoding='utf8'))
db = sqlite3.connect('file:' + _cache_db_path() + '?mode=ro', uri=True)
output = {}
for name, packet in packets.items():
    captured = {'providerCalls': 0}
    def cached(prompt, extra_system_instruction=''):
        digest = hashlib.sha256(prompt.encode('utf8')).hexdigest()
        row = db.execute('SELECT response, created_at FROM llm_cache WHERE user_prompt_hash=? ORDER BY created_at DESC LIMIT 1', (digest,)).fetchone()
        if row is None:
            raise RuntimeError('Exact saved prompt unavailable; never call provider during replay.')
        captured.update(prompt=prompt, rawResponse=row[0], originalCreatedAt=row[1])
        return row[0]
    request = {key: value for key, value in packet['payload']['input'].items() if key not in ('expectedTaskRevision', 'displayText', 'followup')}
    request['taskId'] = packet['taskId']
    try:
        with patch('services.socratic_service._call_guarded_llm', side_effect=cached):
            captured['result'] = execute_conversation(ConversationCapabilityRequest.model_validate(request))
    except Exception as error:
        captured['error'] = str(error)
    output[name] = captured
    print(json.dumps({'case': name, 'providerCalls': 0, 'error': captured.get('error'),
                      'message': (captured.get('result') or {}).get('message')}, ensure_ascii=False), flush=True)
Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf8')
