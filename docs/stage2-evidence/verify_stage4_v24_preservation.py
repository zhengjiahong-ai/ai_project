"""Archive v24 and verify ten older tasks/nine receipts, GET only."""
import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
version = sys.argv[1] if len(sys.argv) > 1 else 'v24'
assert version in {'v24', 'v25', 'v26'}
with contextlib.redirect_stdout(io.StringIO()):
    sys.argv = [str(HERE / 'verify_analysis_preservation_v19.py'), 'inspect']
    check = runpy.run_path(sys.argv[0], run_name='__main__')
report = check['report']
for prior_version in (('v19', 'v22', 'v24', 'v25') if version == 'v26' else
                      ('v19', 'v22', 'v24') if version == 'v25' else ('v19', 'v22')):
    identity = 'stage4-3dgs-critique-20261010-' + prior_version
    report['taskHashes'][prior_version + '-critique'] = check['digest'](check['get']('/' + identity))
    report['receiptHashes'][prior_version + '-critique'] = check['digest'](check['get'](f'/{identity}/operations/{identity}-request'))
before = json.loads((HERE / f'stage4-analysis-{version}-preservation-before.json').read_text(encoding='utf-8'))
assert report['taskHashes'] == before['taskHashes']
assert report['receiptHashes'] == before['receiptHashes']
identity = 'stage4-3dgs-critique-20261010-' + version
task = check['get']('/' + identity)
receipt = check['get'](f'/{identity}/operations/{identity}-request')
assert receipt['status'] in {'succeeded', 'failed', 'cancelled'}
if receipt['status'] == 'succeeded':
    assert len(task['artifacts']) == 1 and len(task['messages']) == 2
    assert task['artifacts'][0]['text'] == receipt['result']['artifact']['text']
report.update(newTaskId=identity, newTaskHash=check['digest'](task),
              newReceiptHash=check['digest'](receipt), oldTasksUnchanged=len(report['taskHashes']),
              oldReceiptsUnchanged=len(report['receiptHashes']), providerCalls=0, taskWrites=0)
for name, value in [(f'stage4-critique-{version}-task.json', task),
                    (f'stage4-analysis-{version}-preservation-after.json', report)]:
    with (HERE / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
print(json.dumps({'oldTasksUnchanged': len(report['taskHashes']), 'oldReceiptsUnchanged': len(report['receiptHashes']),
                  'status': receipt['status'], 'providerCalls': 0, 'taskWrites': 0}))
