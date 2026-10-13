"""Record the user's single-case approval after read-only runtime/preservation checks."""
import contextlib
import hashlib
import io
import json
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
path = HERE / 'stage4-analysis-v22-case-plan.json'
plan = json.loads(path.read_text(encoding='utf-8-sig'))
assert plan['status'] in {'pending_new_authorization', 'authorized_pending_runtime'} and plan['casesExecuted'] == 0
assert not (HERE / 'stage4-critique-v22-attempt.json').exists()
baseline = json.loads((HERE / 'stage7-final-state-20261010.json').read_text(encoding='utf-8'))
with contextlib.redirect_stdout(io.StringIO()):
    sys.argv = [str(HERE / 'verify_analysis_preservation_v19.py'), 'inspect']
    check = runpy.run_path(sys.argv[0], run_name='__main__')
report = check['report']
identity = 'stage4-3dgs-critique-20261010-v19'
report['taskHashes']['v19-critique'] = check['digest'](check['get']('/' + identity))
report['receiptHashes']['v19-critique'] = check['digest'](check['get'](f'/{identity}/operations/{identity}-request'))
assert report['taskHashes'] == baseline['taskHashes']
assert report['receiptHashes'] == baseline['receiptHashes']
runtime = json.loads(subprocess.check_output(['docker', 'inspect', '--format', '{{json .State}}',
    'ai_service_python'], text=True, encoding='utf-8'))
assert runtime['Running'] and runtime['StartedAt'] >= baseline['runningSince']
probe = '''import hashlib,json
from urllib.parse import urlsplit
from core.config import settings
from pathlib import Path
u=urlsplit(settings.deepseek_base_url)
names=['conversation_capability_service.py','grounded_numeric_rendering.py','grounded_critique.py']
print(json.dumps({'scheme':u.scheme,'hostname':u.hostname,'port':u.port,'model':settings.deepseek_model,
    'sourceHashes':{n:hashlib.sha256((Path('/app/services')/n).read_bytes()).hexdigest() for n in names}}))'''
actual = json.loads(subprocess.check_output(['docker', 'exec', 'ai_service_python', 'python', '-c', probe],
    text=True, encoding='utf-8'))
assert actual['scheme'] == 'https' and actual['hostname'] == 'api.deepseek.com' and actual['port'] in (None, 443)
assert actual['model'] == baseline['configuration']['model']
for name, digest in actual['sourceHashes'].items():
    assert digest == hashlib.sha256((ROOT / 'ai-service-python/services' / name).read_bytes()).hexdigest()
    if name in baseline['sourceHashes']:
        assert digest == baseline['sourceHashes'][name]
with urlopen('http://127.0.0.1:8000/health', timeout=30) as response:
    assert json.load(response)['status'] == 'ok'
paper = plan['materials'][0]['pdfId']
with urlopen('http://127.0.0.1:8081/api/task-workspaces/stage4-3dgs-critique-20261010-v19/materials/' + paper + '/processing', timeout=30) as response:
    assert json.load(response)['questionReady'] is True
verification = {'origin': plan['provider'], 'model': actual['model'], 'runningSince': runtime['StartedAt'],
    'sourceHashes': actual['sourceHashes']}
plan.update(status='authorized', authorization='用户明确回复：允许这 1 个批判案例',
    authorizedAt=datetime.now(timezone.utc).isoformat(), providerOriginVerified=True,
    providerVerification=verification)
report.update(checkedAt=plan['authorizedAt'], runtimeVerification=verification, providerCalls=0, taskWrites=0,
    previousRunningSince=baseline['runningSince'], serviceRestored=runtime['StartedAt'] != baseline['runningSince'])
with (HERE / 'stage4-analysis-v22-preservation-before.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'authorizedCases': 1, 'provider': plan['provider'], 'model': actual['model'],
    'runningSince': runtime['StartedAt'], 'oldTasksUnchanged': len(report['taskHashes']),
    'oldReceiptsUnchanged': len(report['receiptHashes']), 'providerCalls': 0, 'taskWrites': 0}))
