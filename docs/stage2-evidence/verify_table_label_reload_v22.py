"""Keep the actual v22 partial receipt intact around a local code reload."""
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
mode = sys.argv[1]
assert mode in {'before', 'after'}
version = sys.argv[2] if len(sys.argv) > 2 else 'v22'
assert version in {'v22', 'v23', 'v23-final', 'v25', 'v26'}
prefix = 'stage4-table-label-v22' if version == 'v22' else 'stage4-output-' + version
with contextlib.redirect_stdout(io.StringIO()):
    sys.argv = [str(HERE / 'verify_analysis_preservation_v19.py'), 'inspect']
    check = runpy.run_path(sys.argv[0], run_name='__main__')
report = check['report']
for prior_version in (('v19', 'v22', 'v24', 'v25') if version == 'v26' else
                      ('v19', 'v22', 'v24') if version == 'v25' else ('v19', 'v22')):
    identity = 'stage4-3dgs-critique-20261010-' + prior_version
    report['taskHashes'][prior_version + '-critique'] = check['digest'](check['get']('/' + identity))
    receipt = check['get'](f'/{identity}/operations/{identity}-request')
    assert receipt['status'] == 'failed' if prior_version == 'v25' else (
        receipt['status'] == 'succeeded' and receipt['result']['partial'] is True)
    report['receiptHashes'][prior_version + '-critique'] = check['digest'](receipt)
report.update(mode=mode, checkedAt=datetime.now(timezone.utc).isoformat())
report['runningSince'] = subprocess.check_output(['docker', 'inspect', '--format',
    '{{.State.StartedAt}}', 'ai_service_python'], text=True).strip()
if mode == 'after':
    before = json.loads((HERE / f'{prefix}-reload-before.json').read_text(encoding='utf-8'))
    assert report['taskHashes'] == before['taskHashes']
    assert report['receiptHashes'] == before['receiptHashes']
    assert report['runningSince'] > before['runningSince']
    names = ['grounded_numeric_rendering.py'] if version == 'v22' else [
        'grounded_numeric_rendering.py', 'grounded_critique.py', 'conversation_capability_service.py']
    report['sourceHashes'] = {}
    for name in names:
        actual = subprocess.check_output(['docker', 'exec', 'ai_service_python', 'python', '-c',
            "import hashlib; from services.grounded_numeric_rendering import _mask_cited_table_labels; "
            f"print(hashlib.sha256(open('/app/services/{name}','rb').read()).hexdigest())"], text=True).strip()
        assert actual == hashlib.sha256((HERE.parent.parent / 'ai-service-python/services' / name).read_bytes()).hexdigest()
        report['sourceHashes'][name] = actual
    with urlopen('http://127.0.0.1:8000/health', timeout=30) as response:
        report['health'] = json.load(response)
    assert report['health']['status'] == 'ok'
with (HERE / f'{prefix}-reload-{mode}.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps({'mode': mode, 'tasksUnchanged': len(report['taskHashes']), 'receiptsUnchanged': len(report['receiptHashes']),
                  'providerCalls': 0, 'taskWrites': 0}))
