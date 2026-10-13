"""Two explicit operation checks reusing already generated, exact-match cached answers.

Run after replay_critique_runtime proved the exact prompts are still available.
Each request is recorded before submission and is never submitted twice.
"""
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/critique-evidence-20261011'
BASE = 'http://localhost:8081/api/task-workspaces/critique-final-20261011'


def finish(request_id, destination):
    for _ in range(80):
        response = requests.get(BASE + '/operations/' + request_id, timeout=20)
        response.raise_for_status()
        operation = response.json()
        if operation['status'] not in ('queued', 'running', 'cancelling'):
            destination.write_text(json.dumps(operation, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps({'requestId': request_id, 'status': operation['status'],
                              'error': operation.get('error'), 'result': {key: operation.get('result', {}).get(key)
                              for key in ('message', 'partial', 'trace')}}, ensure_ascii=False), flush=True)
            return operation
        time.sleep(3)
    raise RuntimeError('Polling deadline; resume this recorded operation only.')


for name in ('regenerated', 'retried'):
    result = OUT / f'runtime-{name}.json'
    attempt = OUT / f'runtime-{name}-attempt.json'
    if result.exists():
        print(name, 'saved; no submission', flush=True)
        continue
    if attempt.exists():
        request_id = json.loads(attempt.read_text(encoding='utf8'))['requestId']
    elif name == 'regenerated':
        task = requests.get(BASE, timeout=20).json()
        artifact = next(item for item in task['artifacts'] if item['id'] == 'critique-final-focused:artifact')
        packet = json.loads((OUT / 'runtime-focused-attempt.json').read_text(encoding='utf8'))['payload']
        packet['requestId'] = 'critique-final-focused-regenerated'
        packet['input']['expectedTaskRevision'] = task['revision']
        packet['input']['followup'] = {'artifactId': artifact['id'], 'version': artifact.get('updatedAt') or artifact['createdAt'], 'regenerate': True}
        attempt.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding='utf8')
        response = requests.post(BASE + '/operations', json=packet, timeout=30)
        response.raise_for_status()
        request_id = packet['requestId']
    else:
        response = requests.post(BASE + '/operations/critique-final-review/retry', timeout=30)
        response.raise_for_status()
        request_id = response.json()['requestId']
        attempt.write_text(json.dumps({'requestId': request_id, 'retryOf': 'critique-final-review'}, indent=2), encoding='utf8')
    finish(request_id, result)

task = requests.get(BASE, timeout=20).json()
artifact = next(item for item in task['artifacts'] if item['id'] == 'critique-final-focused:artifact')
assert len([item for item in task['artifacts'] if item['id'] == artifact['id']]) == 1
assert artifact['versions'] and artifact['versions'][0]['critique']['schemaVersion'] == 2
(OUT / 'runtime-final-task.json').write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf8')
print('One focused artifact; previous generated version archived.', flush=True)
