"""Read-only preservation checks around loading the offline-tested source."""
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
mode = sys.argv[1]
assert mode in {'before', 'after'}
plan = json.loads((HERE / 'stage4-analysis-v12-case-plan.json').read_text(encoding='utf-8-sig'))


def get(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


base = 'http://127.0.0.1:8081/api/task-workspaces'
reading = get(base + '/task:f8b18af5-9681-4bda-ad15-30fd2f3dbafe')
assert reading['revision'] == 19
checks = {}
hashes = {'readingTask': digest(reading)}
for case in plan['cases']:
    kind = case['capability']
    saved = json.loads((HERE / f'stage4-{kind}-v12-receipt.json').read_text(encoding='utf-8-sig'))
    receipt = get(base + '/' + case['taskId'] + '/operations/' + case['requestId'])
    assert receipt == saved, 'Original receipt changed'
    assert receipt['status'] == 'succeeded' and receipt['result']['partial'] is True
    task = get(base + '/' + case['taskId'])
    assert len(task['artifacts']) == 1
    assert task['artifacts'][0]['text'] == receipt['result']['artifact']['text']
    hashes[kind + 'Task'] = digest(task)
    checks[kind + 'ReceiptUnchanged'] = True
health = get('http://127.0.0.1:8000/health')
assert health['status'] == 'ok'
if mode == 'after':
    before = json.loads((HERE / 'stage4-analysis-v12-preservation-before.json').read_text(encoding='utf-8-sig'))
    assert hashes == before['taskHashes'], 'Task state changed during reload'
    checks['allTaskSnapshotsUnchangedAcrossReload'] = True
output = {'checks': checks, 'taskHashes': hashes, 'readingRevision': reading['revision'],
          'health': health, 'providerCallsByCheck': 0, 'taskWritesByCheck': 0}
output_path = HERE / (sys.argv[2] if len(sys.argv) == 3 else f'stage4-analysis-v12-preservation-{mode}.json')
assert output_path.parent.resolve() == HERE.resolve() and output_path.suffix == '.json'
output_path.write_text(
    json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'mode': mode, 'checks': checks, 'readingRevision': 19, 'health': health['status']}))
