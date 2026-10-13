"""Authorized v6 conversation cases: one POST attempt each, then GET only."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
plan = json.loads((HERE / 'stage4-reading-v6-case-plan.json').read_text(encoding='utf-8-sig'))
case, action = sys.argv[1:3]
assert case in {'critique', 'compose'} and action in {'start', 'query'}
assert plan.get('authorization') == '用户2026-10-09明确回复：批准复测'
A, B = [material['pdfId'] for material in plan['materials']]
papers = [B] if case == 'critique' else [A, B]
fixed = next(item for item in plan['cases'] if item['id'] == f'stage4-{case}-v6')
task_id = f'stage4-3dgs-{case}-20261009-v6'
request_id = task_id + '-request'
base = 'http://127.0.0.1:8081/api/task-workspaces'
attempt = HERE / f'stage4-{case}-v6-attempt.json'

def http(path, body=None):
    request = Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)

try:
    receipt = http(f'/{task_id}/operations/{request_id}')
except HTTPError as missing:
    if missing.code != 404 or action != 'start':
        raise
    if attempt.exists():
        raise RuntimeError('Submit attempt already recorded; query the original identity, do not resubmit.')
    try:
        task = http('/' + task_id)
    except HTTPError as absent:
        if absent.code != 404:
            raise
        task = http('', {'id': task_id, 'title': f'阶段4：{case}修复核验-v6', 'paperIds': papers})
    for paper in papers:
        assert http(f'/{task_id}/materials/{paper}/processing')['questionReady']
    body = {'requestId': request_id, 'kind': 'conversation.execute', 'input': {
        'message': fixed['prompt'], 'capability': case, 'steps': [] if case == 'critique' else ['chat', 'compare'],
        'allowedPaperIds': papers, 'strictScope': case == 'critique',
        'primaryPaperId': B if case == 'critique' else A,
        'expectedTaskRevision': task['revision'], 'allowExternalSearch': False}}
    with attempt.open('x', encoding='utf-8') as stream:
        json.dump({'authorization': plan['authorization'], 'provider': plan['provider'],
                   'createdAt': datetime.now(timezone.utc).isoformat(), 'request': body,
                   'taskId': task_id, 'requestId': request_id, 'submitAttempts': 1,
                   'automaticRetryAllowed': False}, stream, ensure_ascii=False, indent=2)
    receipt = http(f'/{task_id}/operations', body)

(HERE / f'stage4-{case}-v6-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
if receipt['status'] == 'succeeded':
    result = receipt['result']
    assert result['capability'] == case and result['materialScope']['allowedPaperIds'] == papers
    assert result['artifact']['text'] and len(result['message']) <= 600
    assert all(source['pdfId'] in papers for source in result['sources'])
    current = http('/' + task_id)
    assert len(current['artifacts']) == 1
    assert sum(bool(item.get('artifactId') == current['artifacts'][0]['id']) for item in current['messages']) == 1
print(json.dumps({'case': case, 'taskId': task_id, 'requestId': request_id,
                  'status': receipt['status'], 'error': receipt.get('error')}, ensure_ascii=True))
