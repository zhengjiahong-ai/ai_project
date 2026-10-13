"""Read-only verification after the four authorized cases; never generates."""
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
before = json.loads((HERE / 'stage4-light-index-v7-task-after.json').read_text(encoding='utf-8'))
with urlopen('http://127.0.0.1:8081/api/task-workspaces/task%3Af8b18af5-9681-4bda-ad15-30fd2f3dbafe', timeout=30) as response:
    task = json.load(response)
checks = {}
for key in ('notes', 'artifacts', 'messages'):
    saved = {item['id']: item for item in task[key]}
    checks[key + 'Preserved'] = all(saved.get(item['id']) == item for item in before[key])
    assert checks[key + 'Preserved'], key + ' changed historical data'
    checks[key + 'Added'] = len(task[key]) - len(before[key])
assert checks['notesAdded'] == 1 and checks['artifactsAdded'] == 1
new_note = [item for item in task['notes'] if item['id'] not in {old['id'] for old in before['notes']}][0]
new_artifact = [item for item in task['artifacts'] if item['id'] not in {old['id'] for old in before['artifacts']}][0]
assert new_artifact['pageIndex'] == 3 and new_artifact['paperIds'] == before['paperIds']
assert len(new_note['sources']) == 1
assert new_note['sources'][0]['pageIndex'] == 3
assert new_note['sources'][0]['pdfId'] == before['paperIds'][0]
assert new_note['sources'][0]['text'] == 'significance'
(HERE / 'stage6-reading-v5-saved-runtime.json').write_text(json.dumps({
    'task': task, 'checks': checks, 'newNote': new_note, 'newArtifact': new_artifact,
    'newModelCalls': 0, 'scope': 'Read-only server persistence; browser reload separately recorded'
}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'revision': task['revision'], 'checks': checks,
                  'noteKeys': list(new_note), 'artifactKeys': list(new_artifact)}, ensure_ascii=False))
