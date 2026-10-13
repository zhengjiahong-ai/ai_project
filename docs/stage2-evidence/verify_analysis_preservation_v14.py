"""Read-only checks around loading the v14 source; never rewrite old evidence."""
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
mode = sys.argv[1]
assert mode in {'before', 'after'}
version = sys.argv[2] if len(sys.argv) == 3 else 'v14'
assert version in {'v14', 'v15'} and len(sys.argv) <= 3
base = 'http://127.0.0.1:8081/api/task-workspaces'


def get(path):
    with urlopen(base + path, timeout=30) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


hashes = {}
for case_version in ('v12', 'v13'):
    plan = json.loads((HERE / f'stage4-analysis-{case_version}-case-plan.json').read_text(encoding='utf-8-sig'))
    for case in plan['cases']:
        kind = case['capability']
        receipt = get(f'/{case["taskId"]}/operations/{case["requestId"]}')
        saved = json.loads((HERE / f'stage4-{kind}-{case_version}-receipt.json').read_text(encoding='utf-8-sig'))
        assert receipt == saved and receipt['status'] == 'succeeded' and receipt['result']['partial'] is True
        task = get('/' + case['taskId'])
        assert len(task['artifacts']) == 1 and task['artifacts'][0]['text'] == receipt['result']['artifact']['text']
        hashes[case_version + '-' + kind] = digest(task)
reading = get('/task:f8b18af5-9681-4bda-ad15-30fd2f3dbafe')
assert reading['revision'] == 19
hashes['reading'] = digest(reading)
historical = json.loads((HERE / 'stage4-analysis-v12-preservation-before.json').read_text(encoding='utf-8-sig'))
assert hashes['reading'] == historical['taskHashes']['readingTask']
with urlopen('http://127.0.0.1:8000/health', timeout=30) as response:
    health = json.load(response)
assert health['status'] == 'ok'
if mode == 'after':
    before = json.loads((HERE / f'stage4-analysis-{version}-preservation-before.json').read_text(encoding='utf-8-sig'))
    assert hashes == before['taskHashes']
with (HERE / f'stage4-analysis-{version}-preservation-{mode}.json').open('x', encoding='utf-8') as stream:
    json.dump({'mode': mode, 'taskHashes': hashes, 'receiptsUnchanged': 4, 'readingRevision': 19,
               'health': health, 'providerCalls': 0, 'taskWrites': 0}, stream, ensure_ascii=False, indent=2)
print(json.dumps({'mode': mode, 'receiptsUnchanged': 4, 'taskSnapshotsChecked': 5,
                  'readingRevision': 19, 'health': 'ok', 'providerCalls': 0, 'taskWrites': 0}))
