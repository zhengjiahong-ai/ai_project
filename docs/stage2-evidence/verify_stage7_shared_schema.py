"""Validate selected live Java responses using the existing container's jsonschema.

GET only, no model generation. Keep response bodies in memory; archive counts and
validation paths only. Semantic ownership is checked by verify_stage7_read_contract.py.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://localhost:8081/api/task-workspaces'
TASK_IDS = ['stage4-3dgs-critique-20261008-v3', 'stage4-3dgs-compose-20261008-v3',
            'stage5-version-recovery-20261008', 'stage5-identity-runtime-20261008']
schemas = {}
hashes = {}
for kind in ('task-workspace', 'task-operation'):
    data = (ROOT / 'contracts' / (kind + '.schema.json')).read_bytes()
    schemas[kind] = json.loads(data)
    hashes[kind] = hashlib.sha256(data).hexdigest()


def read(path):
    with urlopen(BASE + path, timeout=15) as response:
        return json.load(response)


before = {task_id: read('/' + quote(task_id)) for task_id in TASK_IDS}
samples = [{'kind': 'task-workspace', 'name': task_id, 'data': task} for task_id, task in before.items()]
for task_id in TASK_IDS[:2]:
    receipt = read(f'/{task_id}/operations/{task_id}-request')
    assert receipt['status'] in ('succeeded', 'failed'), 'Expected terminal fixture'
    samples.append({'kind': 'task-operation', 'name': task_id + '-request', 'data': receipt})
    if receipt.get('task'):
        samples.append({'kind': 'task-workspace', 'name': task_id + '-receipt-task', 'data': receipt['task']})

VALIDATE = r'''
import copy, json, sys
from importlib.metadata import version
from jsonschema.validators import validator_for
payload = json.load(sys.stdin)
validators = {}
for kind, schema in payload['schemas'].items():
    cls = validator_for(schema)
    cls.check_schema(schema)
    validators[kind] = cls(schema)
checks = []
for sample in payload['samples']:
    errors = sorted(validators[sample['kind']].iter_errors(sample['data']), key=lambda e: str(e.path))
    checks.append({'name': sample['name'], 'kind': sample['kind'], 'passed': not errors,
                   'errors': [{'path': '/'.join(map(str,e.path)), 'keyword': e.validator} for e in errors]})
task = payload['samples'][0]['data']
operation = next(s['data'] for s in payload['samples'] if s['kind']=='task-operation' and s['data']['status']=='succeeded')
negatives = []
def rejected(name, kind, value):
    negatives.append({'name':name, 'rejected': bool(list(validators[kind].iter_errors(value)))})
missing = copy.deepcopy(task); missing.pop('revision')
rejected('missing task revision','task-workspace',missing)
negative = copy.deepcopy(task); negative['revision'] = -1
rejected('negative task revision','task-workspace',negative)
duplicate = copy.deepcopy(task); duplicate['paperIds'] *= 2
rejected('duplicate task materials','task-workspace',duplicate)
incomplete = copy.deepcopy(operation); incomplete.pop('result')
rejected('success without result','task-operation',incomplete)
invalid = copy.deepcopy(operation); invalid['status'] = 'made-up'
rejected('unknown operation state','task-operation',invalid)
print(json.dumps({'validator':'jsonschema','validatorVersion':version('jsonschema'),
                  'checks':checks,'negativeChecks':negatives,
                  'status':'passed' if all(c['passed'] for c in checks) and all(c['rejected'] for c in negatives) else 'failed'}))
'''
process = subprocess.run(['docker', 'exec', '-i', 'ai_service_python', 'python', '-c', VALIDATE],
    input=json.dumps({'schemas': schemas, 'samples': samples}), text=True, capture_output=True, check=True)
receipt = json.loads(process.stdout)
after = {task_id: read('/' + quote(task_id)) for task_id in TASK_IDS}
receipt.update({'checkedAt': datetime.now(timezone.utc).isoformat(), 'schemaSha256': hashes,
                'taskStateUnchanged': before == after, 'httpMethod': 'GET only', 'providerCallsStarted': 0,
                'scope': 'Selected live responses; no browser, teaching quality or write-flow claim'})
Path(__file__).with_name('stage7-shared-schema-runtime.json').write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
assert receipt['status'] == 'passed' and receipt['taskStateUnchanged']
