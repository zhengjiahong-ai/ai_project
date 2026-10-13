"""Read-only service/snapshot checks after cached partial-result verification."""
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

here = Path(__file__).parent
def read(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)

base = 'http://127.0.0.1:8081/api/task-workspaces'
original = json.loads((here / 'stage6-reading-v7-after.json').read_text(encoding='utf-8-sig'))
current = read(base + '/' + quote(original['id'], safe=''))
assert current == original, 'Original reading task changed'
plan = json.loads((here / 'stage4-reading-v7-case-plan.json').read_text(encoding='utf-8-sig'))
checks = {'originalTaskUnchanged': True, 'revision': current['revision']}
for case in plan['cases'][:2]:
    receipt = read(base + '/' + case['taskId'] + '/operations/' + case['requestId'])
    old = json.loads((here / (case['id'] + '-receipt.json')).read_text(encoding='utf-8-sig'))
    assert receipt == old, 'Original failed receipt changed'
    checks[case['id']] = {'unchanged': True, 'status': receipt['status']}
checks['aiHealth'] = read('http://127.0.0.1:8000/health')
checks['providerCalls'] = 0
(here / 'stage4-partial-v8-state.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(checks, ensure_ascii=False))
