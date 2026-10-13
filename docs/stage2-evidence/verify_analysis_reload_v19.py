"""Read-only post-reload checks; no task writes or model invocation."""
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

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.argv = [str(HERE / 'verify_analysis_preservation_v19.py'), 'inspect']
captured = io.StringIO()
with contextlib.redirect_stdout(captured):
    runpy.run_path(sys.argv[0], run_name='__main__')
preservation = json.loads(captured.getvalue())
baseline = json.loads((HERE / 'stage4-analysis-v19-preservation-before.json').read_text(encoding='utf-8-sig'))
assert preservation['taskHashes'] == baseline['taskHashes'], 'Task state changed; inspect before accepting.'
assert preservation['receiptHashes'] == baseline['receiptHashes'], 'Receipt state changed; inspect before accepting.'

def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, encoding='utf-8').strip()

runtime = json.loads(docker('inspect', '--format', '{{json .State}}', 'ai_service_python'))
assert runtime['Running']
assert runtime['StartedAt'] > '2026-10-10T06:04:36.675666382Z'
source = ROOT / 'ai-service-python/services/grounded_critique.py'
expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
loaded_hash = docker('exec', 'ai_service_python', 'python', '-c',
    'import hashlib, inspect; from services.grounded_critique import _atomic_findings; '
    'print(hashlib.sha256(open(inspect.getsourcefile(_atomic_findings), "rb").read()).hexdigest())')
assert loaded_hash == expected_hash
with urlopen('http://127.0.0.1:8000/health', timeout=30) as response:
    health = json.load(response)
assert health['status'] == 'ok', health
with urlopen('http://127.0.0.1:5173/?unified=1', timeout=15) as response:
    assert response.status == 200

report = {'checkedAt': datetime.now(timezone.utc).isoformat(),
          'authorization': '用户明确回复：允许现在短暂重启并加载修复',
          'codeCommit': '2bbc095', 'checkoutHeadAtRestart': '5a07192',
          'runningSince': runtime['StartedAt'], 'running': runtime['Running'],
          'sourceSha256': loaded_hash, 'health': health, 'frontendHttpStatus': 200,
          'baselineTaskCount': len(preservation['taskHashes']),
          'baselineReceiptCount': len(preservation['receiptHashes']),
          'preservation': preservation, 'providerCalls': 0, 'taskWrites': 0,
          'note': 'Old before/after files predate the actual restart and remain unchanged. '
                  'Module import and source hash are checked in the restarted container; '
                  'no new live generation or semantic acceptance is claimed.'}
with (HERE / 'stage4-analysis-v19-post-reload.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps({key: report[key] for key in ('runningSince', 'baselineTaskCount',
      'baselineReceiptCount', 'providerCalls', 'taskWrites')}))
