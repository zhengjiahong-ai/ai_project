"""Archive the sole v22 task and verify all nine previous tasks, GET only."""
import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    sys.argv = [str(HERE / 'verify_analysis_preservation_v19.py'), 'inspect']
    check = runpy.run_path(sys.argv[0], run_name='__main__')
report = check['report']
identity = 'stage4-3dgs-critique-20261010-v19'
report['taskHashes']['v19-critique'] = check['digest'](check['get']('/' + identity))
report['receiptHashes']['v19-critique'] = check['digest'](check['get'](f'/{identity}/operations/{identity}-request'))
before = json.loads((HERE / 'stage4-analysis-v22-preservation-before.json').read_text(encoding='utf-8'))
assert report['taskHashes'] == before['taskHashes']
assert report['receiptHashes'] == before['receiptHashes']
identity = 'stage4-3dgs-critique-20261010-v22'
task = check['get']('/' + identity)
receipt = check['get'](f'/{identity}/operations/{identity}-request')
assert receipt['status'] in {'succeeded', 'failed', 'cancelled'}
if receipt['status'] == 'succeeded':
    assert len(task['artifacts']) == 1 and len(task['messages']) == 2
    assert task['artifacts'][0]['text'] == receipt['result']['artifact']['text']
    assert receipt['result']['artifact']['text']
report.update(newTaskId=identity, newTaskHash=check['digest'](task),
              newReceiptHash=check['digest'](receipt),
              oldTasksUnchanged=9, oldReceiptsUnchanged=8, providerCalls=0, taskWrites=0)
for name, value in [('stage4-critique-v22-task.json', task),
                    ('stage4-analysis-v22-preservation-after.json', report)]:
    with (HERE / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
print(json.dumps({'oldTasksUnchanged': 9, 'oldReceiptsUnchanged': 8,
                  'status': receipt['status'], 'providerCalls': 0, 'taskWrites': 0}))
