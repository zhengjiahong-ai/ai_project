"""GET-only final preservation and original critique identity checks."""
import contextlib
import io
import json
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    sys.argv = [str(HERE / 'verify_analysis_preservation_v19.py'), 'inspect']
    check = runpy.run_path(sys.argv[0], run_name='__main__')
report = check['report']
for version in ('v19', 'v22', 'v24', 'v25'):
    identity = 'stage4-3dgs-critique-20261010-' + version
    report['taskHashes'][version + '-critique'] = check['digest'](check['get']('/' + identity))
    report['receiptHashes'][version + '-critique'] = check['digest'](check['get'](f'/{identity}/operations/{identity}-request'))
baseline = json.loads((HERE / 'stage4-analysis-v26-preservation-before.json').read_text(encoding='utf-8'))
assert report['taskHashes'] == baseline['taskHashes']
assert report['receiptHashes'] == baseline['receiptHashes']
identity = 'stage4-3dgs-critique-20261010-v26'
receipt = check['get'](f'/{identity}/operations/{identity}-request')
archived = json.loads((HERE / 'stage4-critique-v26-receipt.json').read_text(encoding='utf-8'))
assert {key: value for key, value in receipt.items() if key != 'task'} == {
    key: value for key, value in archived.items() if key != 'task'}
task = check['get']('/' + identity)
original = json.loads((HERE / 'stage4-critique-v26-task.json').read_text(encoding='utf-8'))
assert task['artifacts'] == original['artifacts'] and task['messages'] == original['messages']
differences = [key for key in task if task[key] != original.get(key)]
assert set(differences) <= {'focusedPaperId', 'revision', 'updatedAt'}
result = receipt['result']
replay = json.loads((HERE / 'stage4-analysis-v26-cached-response.json').read_text(encoding='utf-8'))['cacheRows'][0]['nativeReplay']
for field in ('message', 'partial', 'capability', 'materialScope'):
    assert result[field] == replay[field]
assert result['artifact']['text'] == replay['artifact']['text'] == task['artifacts'][0]['text']
diagnosis = json.loads((HERE / 'stage4-analysis-v26-diagnosis.json').read_text(encoding='utf-8'))
assert not result['partial'] and len(diagnosis['diagnostics']) == 7
assert all(item['rejection'] is None for item in diagnosis['diagnostics'])
assert len(result['message']) <= 600
for value in ('17.38', '237', '0.270', '0.007', '0.020', 'A6000'):
    assert value in result['message']
with urlopen('http://localhost:8000/health', timeout=30) as stream:
    health = json.load(stream)
assert health['status'] == 'ok'
with urlopen('http://localhost:8070/api/isalive', timeout=30) as stream:
    assert stream.status == 200
with urlopen('http://localhost:5173/', timeout=30) as stream:
    assert stream.status == 200
report.update(checkedAt=datetime.now(timezone.utc).isoformat(), oldTasksUnchanged=12,
    oldReceiptsUnchanged=11, newOperationAndResultUnchanged=True, newArtifactAndMessagesUnchanged=True,
    receiptEmbedsCurrentTask=receipt.get('task') == task,
    expectedReaderFocusChanges=differences, realCritiqueMatchesOriginalResponse=True,
    validatedCritiqueClaims=7, summaryCharacters=len(result['message']), health=health,
    providerCalls=0, taskWrites=0)
with (HERE / 'stage7-default-final-state.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps({key: report[key] for key in ('oldTasksUnchanged', 'oldReceiptsUnchanged',
    'newOperationAndResultUnchanged', 'newArtifactAndMessagesUnchanged', 'expectedReaderFocusChanges',
    'validatedCritiqueClaims', 'summaryCharacters', 'providerCalls', 'taskWrites')}))
