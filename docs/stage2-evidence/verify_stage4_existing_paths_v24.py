"""Read previous comparison, composition and research results without regenerating them."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8081/api/task-workspaces'


def get(path):
    with urlopen(BASE + path, timeout=30) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


checks = []
for name, identity, archive_name, steps in [
    ('comparison', 'stage4-3dgs-compare-20261010-v16', 'stage4-compare-v16-receipt.json', ['compare']),
    ('composition', 'stage4-3dgs-compose-20261009-v9', 'stage4-compose-v9-receipt.json', ['chat', 'compare']),
]:
    old = json.loads((HERE / archive_name).read_text(encoding='utf-8-sig'))
    receipt = get(f'/{identity}/operations/{identity}-request')
    assert receipt['status'] == 'succeeded' and receipt['result'] == old['result']
    assert [step['capability'] for step in receipt['result']['steps']] == steps
    task = get('/' + identity)
    assert len(task['artifacts']) == 1
    assert task['artifacts'][0]['text'] == receipt['result']['artifact']['text']
    allowed = set(receipt['result']['materialScope']['allowedPaperIds'])
    assert len(allowed) == 2 and all(source['pdfId'] in allowed for source in receipt['result']['sources'])
    assert get('/' + identity) == task
    checks.append({'path': name, 'originalResultUnchanged': True, 'scopePapers': 2,
                   'steps': steps, 'taskSha256': digest(task), 'resultSha256': digest(receipt['result'])})
identity = 'stage4-3dgs-research-20261008'
receipt = get(f'/{identity}/operations/stage4-3dgs-research-request-20261008')
run = receipt['task']['researchRuns'][0]['researchId']
research = get(f'/{identity}/research/{run}')
old = json.loads((HERE / 'stage4-3dgs-research-state.json').read_text(encoding='utf-8-sig'))
assert research['task']['status'] == 'succeeded'
assert research['task']['report'] == old['task']['report']
assert research['task']['findings'] == old['task']['findings']
task = research['workspace']
assert len(task['artifacts']) == len(task['messages']) == 1
assert task['artifacts'][0]['text'] == research['task']['report']
assert task['messages'][0]['artifactId'] == task['artifacts'][0]['id']
assert len(research['task']['plan']) == len(research['task']['findings']) == 1
assert get(f'/{identity}/research/{run}') == research
checks.append({'path': 'research', 'originalReportAndFindingsUnchanged': True,
               'published': True, 'planQuestions': 1, 'findings': 1,
               'taskSha256': digest(task), 'reportSha256': digest(research['task']['report'])})
report = {'checks': checks, 'httpMethod': 'GET only', 'providerCalls': 0, 'taskWrites': 0,
          'scope': 'Preservation and pipeline evidence; historical content limits remain in the original audits'}
with (HERE / 'stage4-existing-paths-v24.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False))
