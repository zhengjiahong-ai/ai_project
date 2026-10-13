"""GET-only baseline and preservation check; never writes tasks or calls a model."""
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
mode = sys.argv[1]
assert mode in {'inspect', 'before', 'after'}


def get(path):
    with urlopen('http://127.0.0.1:8081/api/task-workspaces' + path, timeout=30) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def differences(a, b, path=''):
    if type(a) is not type(b):
        return [path + ': type changed']
    if isinstance(a, dict):
        return [item for key in a.keys() | b.keys() for item in (
            [path + '/' + key + ': missing'] if key not in a or key not in b
            else differences(a[key], b[key], path + '/' + key))]
    if isinstance(a, list):
        lengths = [path + ': length changed'] if len(a) != len(b) else []
        return lengths + [item for i, (x, y) in enumerate(zip(a, b)) for item in differences(x, y, path + '/' + str(i))]
    return [] if a == b else [path + ': ' + repr(a)[:160] + ' -> ' + repr(b)[:160]]


old = json.loads((HERE / 'stage4-analysis-v17-preservation-after.json').read_text(encoding='utf-8-sig'))
hashes, receipt_hashes, changes, task_changes = {}, {}, {}, {}
for version in ('v12', 'v13', 'v16', 'v18'):
    plan = json.loads((HERE / f'stage4-analysis-{version}-case-plan.json').read_text(encoding='utf-8-sig'))
    for case in plan['cases']:
        name = version + '-' + case['capability']
        receipt = get(f'/{case["taskId"]}/operations/{case["requestId"]}')
        archived = json.loads((HERE / f'stage4-{case["capability"]}-{version}-receipt.json').read_text(encoding='utf-8-sig'))
        changes[name] = differences(archived, receipt)
        receipt_hashes[name] = digest(receipt)
        task = get('/' + case['taskId'])
        hashes[name] = digest(task)
        if version in {'v16', 'v18'}:
            archived_task = json.loads((HERE / f'stage4-{case["capability"]}-{version}-task.json').read_text(encoding='utf-8-sig'))
            task_changes[name] = differences(archived_task, task)
reading = get('/task:f8b18af5-9681-4bda-ad15-30fd2f3dbafe')
hashes['reading'] = digest(reading)
report = {'mode': mode, 'taskHashes': hashes, 'receiptHashes': receipt_hashes,
          'archivedReceiptDifferences': changes,
          'archivedTaskDifferences': task_changes,
          'changedTaskHashesSinceV17': [key for key in old['taskHashes'] if hashes[key] != old['taskHashes'][key]],
          'readingRevision': reading['revision'], 'providerCalls': 0, 'taskWrites': 0}
if mode == 'inspect':
    print(json.dumps(report, ensure_ascii=True, indent=2))
else:
    # The v16 browser review focused a paper after the v17 baseline. The
    # receipt endpoint embeds the current task; the immutable result is intact.
    assert report['changedTaskHashesSinceV17'] == ['v16-compare'], report
    allowed = {'/focusedPaperId', '/updatedAt', '/revision'}
    assert {item.split(': ', 1)[0] for item in task_changes['v16-compare']} == allowed, report
    assert {item.split(': ', 1)[0] for item in changes['v16-compare']} == {'/task' + key for key in allowed}, report
    assert all(not value for key, value in changes.items() if key not in {'v16-compare', 'v18-critique'}), report
    # A separate app interaction focused LightGaussian and appended a completed
    # ordinary chat after the archived fixed case. Keep that interaction too.
    appended = {'/focusedPaperId', '/updatedAt', '/revision', '/messages', '/appliedRequestIds'}
    assert {item.split(': ', 1)[0] for item in task_changes['v18-critique']} == appended, report
    assert {item.split(': ', 1)[0] for item in changes['v18-critique']} == {'/task' + key for key in appended}, report
    assert hashes['v18-critique'] == '0a328a7080fe016d8564d27312cbee3f61a13cc8553faaf763ce4867d98b9dd9', report
    assert hashes['v16-compare'] == 'e8bb36dcac4fe966d06b0130ea6b478c8a3efb7ed67ed5d47bd7b19fd802382b', report
    report['baselineNote'] = ('v16 comparison focus changed revision 1 to 2 before this baseline. '
        'v18 focused LightGaussian and appended chat 56d684aa-c693-401a-bc44-4eb7e0b05173 (user: 讲解一下), revision 1 to 3. '
        'Both archived fixed results remain unchanged; old archives preserved. App interaction is not counted as an agent-generated fixed case or participant understanding evidence.')
    if mode == 'after':
        before = json.loads((HERE / 'stage4-analysis-v19-preservation-before.json').read_text(encoding='utf-8-sig'))
        assert hashes == before['taskHashes'] and receipt_hashes == before['receiptHashes']
    with (HERE / f'stage4-analysis-v19-preservation-{mode}.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'mode': mode, 'archivedResultsUnchanged': 7, 'baselineTaskCount': 8,
                      'readingRevision': reading['revision'], 'providerCalls': 0, 'taskWrites': 0}))
