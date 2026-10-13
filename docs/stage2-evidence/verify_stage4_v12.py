"""Bounded analysis cases; start is disabled until explicit plan authorization."""
import json
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
version = sys.argv[3] if len(sys.argv) == 4 else 'v12'
assert len(sys.argv) in {3, 4} and version in {'v12', 'v13', 'v16', 'v18', 'v19', 'v22', 'v24', 'v25', 'v26'}
plan = json.loads((HERE / f'stage4-analysis-{version}-case-plan.json').read_text(encoding='utf-8-sig'))
case, action = sys.argv[1:3]
assert case in {'critique', 'compare'} and action in {'start', 'query'}
assert plan['provider'] == 'https://api.deepseek.com' and plan['maxCases'] == (1 if version in {'v18', 'v19', 'v22', 'v24', 'v25', 'v26'} else 2)
assert len(plan['cases']) == plan['maxCases']
assert any(item['capability'] == case for item in plan['cases']), 'Case outside fixed plan'
if action == 'start':
    assert plan['status'] in {'authorized', 'execution_started'} and plan.get('authorization'), 'Explicit new authorization required'
    if version in {'v22', 'v24', 'v25', 'v26'}:
        assert plan.get('providerOriginVerified') is True, 'Fresh runtime verification required'
        verified = plan.get('providerVerification', {})
        assert verified.get('origin') == plan['provider'], 'Verified Provider does not match plan'
        assert verified.get('model') and verified.get('runningSince'), 'Incomplete runtime verification'
        expected_hashes = verified.get('sourceHashes', {})
        service_root = HERE.parent.parent / 'ai-service-python/services'
        for name in ('conversation_capability_service.py', 'grounded_numeric_rendering.py', 'grounded_critique.py'):
            assert expected_hashes.get(name) == hashlib.sha256((service_root / name).read_bytes()).hexdigest(), 'Verified source changed'
        runtime = json.loads(subprocess.check_output(['docker', 'inspect', '--format',
            '{{json .State}}', 'ai_service_python'], text=True, encoding='utf-8'))
        assert runtime['Running'] and runtime['StartedAt'] == verified['runningSince'], 'Verified runtime changed'
        actual = json.loads(subprocess.check_output(['docker', 'exec', 'ai_service_python', 'python', '-c',
            'import json; from urllib.parse import urlsplit; from core.config import settings; '
            'u=urlsplit(settings.deepseek_base_url); '
            'print(json.dumps({"scheme":u.scheme,"hostname":u.hostname,"port":u.port,"model":settings.deepseek_model}))'
        ], text=True, encoding='utf-8'))
        assert actual['scheme'] == 'https' and actual['hostname'] == 'api.deepseek.com' and actual['port'] in (None, 443), 'Actual Provider changed'
        assert actual['model'] == verified['model'], 'Actual model changed'
materials = [material['pdfId'] for material in plan['materials']]
A, B = materials[0], materials[-1]
papers = [B] if case == 'critique' else [A, B]
fixed = next(item for item in plan['cases'] if item['capability'] == case)
task_id, request_id = fixed['taskId'], fixed['requestId']
base = 'http://127.0.0.1:8081/api/task-workspaces'
attempt = HERE / f'stage4-{case}-{version}-attempt.json'


def http(path, body=None):
    request = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


try:
    receipt = http(f'/{task_id}/operations/{request_id}')
except HTTPError as missing:
    if missing.code != 404 or action != 'start':
        raise
    if attempt.exists():
        raise RuntimeError('Submit attempt exists; query the original identity, do not resubmit')
    try:
        task = http('/' + task_id)
    except HTTPError as absent:
        if absent.code != 404:
            raise
        task = http('', {'id': task_id, 'title': f'阶段4：{case}表格范围修复核验-{version}', 'paperIds': papers})
    for paper in papers:
        assert http(f'/{task_id}/materials/{paper}/processing')['questionReady']
    body = {'requestId': request_id, 'kind': 'conversation.execute', 'input': {
        'message': fixed['prompt'], 'capability': case, 'steps': [], 'allowedPaperIds': papers,
        'strictScope': case == 'critique', 'primaryPaperId': B if case == 'critique' else A,
        'expectedTaskRevision': task['revision'], 'allowExternalSearch': False}}
    with attempt.open('x', encoding='utf-8') as stream:
        json.dump({'authorization': plan['authorization'], 'provider': plan['provider'],
                   'createdAt': datetime.now(timezone.utc).isoformat(), 'request': body,
                   'taskId': task_id, 'requestId': request_id, 'submitAttempts': 1,
                   'automaticRetryAllowed': False}, stream, ensure_ascii=False, indent=2)
    receipt = http(f'/{task_id}/operations', body)
(HERE / f'stage4-{case}-{version}-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
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
