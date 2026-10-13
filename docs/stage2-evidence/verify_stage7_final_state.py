"""Read-only final preservation/runtime audit; no Provider requests or task writes."""
import contextlib
import hashlib
import io
import json
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
baseline = json.loads((HERE / 'stage4-parameter-v21-preservation-after.json').read_text(encoding='utf-8'))
with contextlib.redirect_stdout(io.StringIO()):
    sys.argv = [str(HERE / 'verify_analysis_preservation_v19.py'), 'inspect']
    audit = runpy.run_path(sys.argv[0], run_name='__main__')
report = audit['report']
task_id = 'stage4-3dgs-critique-20261010-v19'
task = audit['get']('/' + task_id)
receipt = audit['get'](f'/{task_id}/operations/{task_id}-request')
report['taskHashes']['v19-critique'] = audit['digest'](task)
report['receiptHashes']['v19-critique'] = audit['digest'](receipt)
assert report['taskHashes'] == baseline['taskHashes'], 'Task data changed; inspect differences'
assert report['receiptHashes'] == baseline['receiptHashes'], 'Receipt changed; inspect differences'
assert receipt['status'] == 'succeeded' and receipt['result']['partial'] is True

runtime = json.loads(subprocess.check_output(['docker', 'inspect', '--format',
    '{{json .State}}', 'ai_service_python'], text=True, encoding='utf-8'))
assert runtime['Running'] and runtime['StartedAt'] == baseline['runningSince']
configuration = json.loads(subprocess.check_output(['docker', 'exec', 'ai_service_python',
    'python', '-c',
    'import json; from urllib.parse import urlsplit; from core.config import settings; '
    'u=urlsplit(settings.deepseek_base_url); '
    'print(json.dumps({"scheme":u.scheme,"hostname":u.hostname,"port":u.port,"model":settings.deepseek_model}))'
], text=True, encoding='utf-8'))
assert configuration['scheme'] == 'https' and configuration['hostname'] == 'api.deepseek.com'
assert configuration['port'] in (None, 443)
configuration['origin'] = 'https://api.deepseek.com'
hashes = {}
for name, expected_field in [('conversation_capability_service.py', 'sourceSha256'),
                             ('grounded_numeric_rendering.py', 'numericSourceSha256')]:
    hashes[name] = hashlib.sha256((ROOT / 'ai-service-python/services' / name).read_bytes()).hexdigest()
    assert hashes[name] == baseline[expected_field], 'Product code changed after verified reload'

health = {}
for name, url in [('python', 'http://127.0.0.1:8000/health'),
                  ('frontend', 'http://127.0.0.1:5173/?unified=1'),
                  ('java', 'http://127.0.0.1:8081/api/task-workspaces'),
                  ('grobid', 'http://127.0.0.1:8070/api/isalive')]:
    with urlopen(url, timeout=30) as response:
        assert response.status == 200
        data = response.read()
    health[name] = 200
    if name == 'python':
        assert json.loads(data)['status'] == 'ok'

output = {
    'checkedAt': datetime.now(timezone.utc).isoformat(),
    'head': subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip(),
    'method': 'GET and local metadata only', 'providerCalls': 0, 'taskWrites': 0,
    'restarts': 0, 'runningSince': runtime['StartedAt'], 'health': health,
    'configuration': configuration, 'sourceHashes': hashes,
    'taskHashes': report['taskHashes'], 'receiptHashes': report['receiptHashes'],
    'readingRevision': report['readingRevision'], 'existingCritiqueRemainsPartial': True,
    'newModelQualityVerified': False,
    'waivedByUser': ['A18 isolated-browser recovery subcase', 'A20 complete novice observation'],
}
with (HERE / 'stage7-final-state-20261010.json').open('x', encoding='utf-8') as stream:
    json.dump(output, stream, ensure_ascii=False, indent=2)
print(json.dumps({'health': health, 'tasksUnchanged': len(report['taskHashes']),
    'receiptsUnchanged': len(report['receiptHashes']), 'providerOrigin': configuration['origin'],
    'model': configuration['model'], 'providerCalls': 0, 'taskWrites': 0}))
