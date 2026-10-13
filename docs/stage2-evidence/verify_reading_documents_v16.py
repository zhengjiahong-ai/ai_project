"""Read-only check after the saved-document navigation change. No Provider calls."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
base = 'http://127.0.0.1:8081/api/task-workspaces'


def get(path):
    with urlopen(base + path, timeout=30) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


hashes = {}
for version in ('v12', 'v13'):
    plan = json.loads((HERE / f'stage4-analysis-{version}-case-plan.json').read_text(encoding='utf-8-sig'))
    for case in plan['cases']:
        receipt = get(f'/{case["taskId"]}/operations/{case["requestId"]}')
        archived = json.loads((HERE / f'stage4-{case["capability"]}-{version}-receipt.json').read_text(encoding='utf-8-sig'))
        assert receipt == archived
        hashes[f'{version}-{case["capability"]}'] = digest(get('/' + case['taskId']))
reading = get('/task:f8b18af5-9681-4bda-ad15-30fd2f3dbafe')
hashes['reading'] = digest(reading)
before = json.loads((HERE / 'stage4-analysis-v15-preservation-after.json').read_text(encoding='utf-8-sig'))
assert hashes == before['taskHashes'] and reading['revision'] == 19
saved = json.loads((HERE / 'stage6-reading-v9-after-save.json').read_text(encoding='utf-8-sig'))
assert reading == saved
report = {'taskHashes': hashes, 'receiptsUnchanged': 4, 'readingRevision': 19,
          'notesUnchanged': len(reading['notes']), 'artifactsUnchanged': len(reading['artifacts']),
          'providerCalls': 0, 'taskWrites': 0}
with (HERE / 'stage6-document-list-v16-preservation.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report))
