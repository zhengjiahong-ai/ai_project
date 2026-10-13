"""GET-only preservation checks around loading precision and prompt fixes."""
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
mode = sys.argv[1]
assert mode in {'before', 'after'} and len(sys.argv) == 2
base = 'http://127.0.0.1:8081/api/task-workspaces'


def get(path):
    with urlopen(base + path, timeout=30) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


hashes = {}
for version in ('v12', 'v13', 'v16'):
    plan = json.loads((HERE / f'stage4-analysis-{version}-case-plan.json').read_text(encoding='utf-8-sig'))
    for case in plan['cases']:
        kind = case['capability']
        assert get(f'/{case["taskId"]}/operations/{case["requestId"]}') == json.loads(
            (HERE / f'stage4-{kind}-{version}-receipt.json').read_text(encoding='utf-8-sig'))
        task = get('/' + case['taskId'])
        hashes[f'{version}-{kind}'] = digest(task)
        if version == 'v16':
            assert task == json.loads((HERE / f'stage4-{kind}-v16-task.json').read_text(encoding='utf-8-sig'))
reading = get('/task:f8b18af5-9681-4bda-ad15-30fd2f3dbafe')
assert reading['revision'] == 19
hashes['reading'] = digest(reading)
old = json.loads((HERE / 'stage4-analysis-v16-preservation-after.json').read_text(encoding='utf-8-sig'))
assert all(hashes[key] == value for key, value in old['taskHashes'].items())
with urlopen('http://127.0.0.1:8000/health', timeout=30) as response:
    health = json.load(response)
assert health['status'] == 'ok'
if mode == 'after':
    before = json.loads((HERE / 'stage4-analysis-v17-preservation-before.json').read_text(encoding='utf-8-sig'))
    assert hashes == before['taskHashes']
report = {'mode': mode, 'taskHashes': hashes, 'receiptsUnchanged': 6, 'readingRevision': 19,
          'health': health, 'providerCalls': 0, 'taskWrites': 0}
with (HERE / f'stage4-analysis-v17-preservation-{mode}.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps({'mode': mode, 'receiptsUnchanged': 6, 'tasksUnchanged': 7,
                  'readingRevision': 19, 'providerCalls': 0, 'taskWrites': 0}))
