"""GET-only checks of current task/material/receipt boundaries, with no generation.

Checks required fields and enums from the shared schemas plus ownership invariants;
this is not a complete JSON Schema validator or a browser acceptance test.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://localhost:8081/api/task-workspaces'
TASK = 'stage4-3dgs-critique-20261010-v26'
OTHER = 'stage4-3dgs-compare-20261010-v16'
PAPER = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
OUTSIDE = 'f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf'
checks = []


def read(path):
    with urlopen(BASE + path, timeout=15) as response:
        return json.load(response)


def not_found(path):
    try:
        read(path)
    except HTTPError as error:
        assert error.code == 404, f'{path}: expected 404, got {error.code}'
        checks.append({'path': path, 'status': 404})
        return
    raise AssertionError(f'{path}: unexpectedly accessible')


def required(value, schema):
    assert isinstance(value, dict)
    assert set(schema['required']).issubset(value), 'Required contract fields missing'


task_schema = json.loads((ROOT / 'contracts/task-workspace.schema.json').read_text(encoding='utf-8'))
operation_schema = json.loads((ROOT / 'contracts/task-operation.schema.json').read_text(encoding='utf-8'))
before = {task_id: read('/' + task_id) for task_id in (TASK, OTHER)}
for task_id, task in before.items():
    required(task, task_schema)
    assert task['id'] == task_id and type(task['revision']) is int
    assert len(task['paperIds']) == len(set(task['paperIds']))
    assert task['focusedPaperId'] is None or task['focusedPaperId'] in task['paperIds']
    materials = read(f'/{task_id}/materials')
    assert {item['id'] for item in materials} == set(task['paperIds'])
    assert all(type(item['fileAvailable']) is bool for item in materials)
    receipt = read(f'/{task_id}/operations/{task_id}-request')
    required(receipt, operation_schema)
    assert receipt['taskId'] == task_id
    assert receipt['kind'] in operation_schema['properties']['kind']['enum']
    assert receipt['status'] in operation_schema['properties']['status']['enum']
    assert receipt['status'] in ('succeeded', 'failed'), 'Fixture is no longer terminal'
    assert set(receipt['paperIds']).issubset(task['paperIds'])
    assert not {'input', 'upstream', 'provider', 'history', 'state'} & receipt.keys()
    assert not {'history', 'state', 'upstream'} & receipt['request'].keys()
    assert receipt['request'].get('allowExternalSearch') is False
    if receipt['status'] == 'succeeded':
        assert 'task' in receipt and 'result' in receipt
        assert receipt['requestId'] in receipt['task']['appliedRequestIds']
        assert all(source['pdfId'] in receipt['paperIds'] for source in receipt['result']['sources'])
    repeated = read(f'/{task_id}/operations/{task_id}-request')
    assert repeated == receipt, 'Repeated read changed the receipt'
    checks.append({'taskId': task_id, 'status': receipt['status'], 'requiredFieldsAndEnums': True,
                   'materialScopeRetained': True, 'publicRequestOnly': True, 'repeatReadUnchanged': True})

assert OUTSIDE not in before[TASK]['paperIds'] and OUTSIDE in before[OTHER]['paperIds']
for endpoint in ('file', 'analysis', 'processing'):
    not_found(f'/{TASK}/materials/{quote(OUTSIDE)}/{endpoint}')
not_found(f'/{TASK}/operations/{OTHER}-request')
not_found('/stage7-deliberately-missing-task')
analysis = read(f'/{TASK}/materials/{PAPER}/analysis')
assert analysis['pdfId'] == PAPER and analysis['readingReady'] is True
assert analysis['questionReady'] is True
assert analysis['aiAnalysisStatus'] == 'not_requested'
after = {task_id: read('/' + task_id) for task_id in (TASK, OTHER)}
assert before == after, 'Read-only audit changed task state'
receipt = {'status': 'passed', 'checkedAt': datetime.now(timezone.utc).isoformat(),
           'method': 'GET only', 'taskStateUnchanged': True, 'analysisReadingAndQuestionReady': True,
           'overviewNotRequested': True, 'fullJsonSchemaValidation': False,
           'browserRecoveryVerified': False, 'providerCallsStarted': 0, 'checks': checks}
with Path(__file__).with_name('stage7-final-read-v26.json').open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
print(json.dumps(receipt, ensure_ascii=False))
