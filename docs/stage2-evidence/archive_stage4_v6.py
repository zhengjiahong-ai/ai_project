"""Archive completed v6 cases from local cache/API. No model calls or writes to tasks."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
plan = json.loads((HERE / 'stage4-reading-v6-case-plan.json').read_text(encoding='utf-8-sig'))
start = datetime.fromisoformat(plan['authorizedAt']).timestamp()
end = datetime.now(timezone.utc).timestamp()
code = '''
import json, sqlite3, sys
from services.llm_cache import _cache_db_path
from services.agent_grounded_answer import _extract_json_object
db=sqlite3.connect('file:'+_cache_db_path()+'?mode=ro',uri=True)
rows=db.execute('SELECT model,temperature,response,created_at FROM llm_cache WHERE created_at>=? AND created_at<? ORDER BY created_at',(float(sys.argv[1]),float(sys.argv[2]))).fetchall()
result=[]
for model,temp,response,created in rows:
    try: parsed=_extract_json_object(response)
    except Exception: parsed=response
    result.append({'model':model,'temperature':temp,'createdAt':created,'response':parsed})
print(json.dumps(result,ensure_ascii=False))
'''
cached = subprocess.run(['docker', 'exec', 'ai_service_python', 'python', '-c', code, str(start), str(end)],
                        text=True, encoding='utf-8', capture_output=True, check=True)
responses = json.loads(cached.stdout)
(HERE / 'stage4-reading-v6-cached-responses.json').write_text(json.dumps({
    'scope': 'Local cache rows in authorization time window; rows are not total requests or charges',
    'startUtc': datetime.fromtimestamp(start, timezone.utc).isoformat(),
    'endUtc': datetime.fromtimestamp(end, timezone.utc).isoformat(),
    'cacheRows': responses, 'newModelCalls': 0}, ensure_ascii=False, indent=2), encoding='utf-8')
before = json.loads((HERE / 'stage6-reading-v6-before.json').read_text(encoding='utf-8-sig'))
with urlopen('http://127.0.0.1:8081/api/task-workspaces/task%3Af8b18af5-9681-4bda-ad15-30fd2f3dbafe', timeout=30) as response:
    task = json.load(response)
checks = {}
for key in ('notes', 'artifacts', 'messages'):
    old = {item['id']: item for item in before[key]}
    saved = {item['id']: item for item in task[key]}
    checks[key + 'Preserved'] = all(saved.get(identifier) == item for identifier, item in old.items())
    checks[key + 'Added'] = len(saved) - len(old)
notes = [item for item in task['notes'] if item['id'] not in {old['id'] for old in before['notes']}]
artifacts = [item for item in task['artifacts'] if item['id'] not in {old['id'] for old in before['artifacts']}]
assert all(checks[key + 'Preserved'] for key in ('notes', 'artifacts', 'messages'))
assert checks['notesAdded'] == checks['artifactsAdded'] == 1 and checks['messagesAdded'] == 2
note, artifact = notes[0], artifacts[0]
assert note['sources'][0]['pageIndex'] == artifact['pageIndex'] == 3
assert note['sources'][0]['text'] == 'significance'
checks['newReadingDocumentsHavePage4'] = True
checks['newDocumentsKeepMaterial'] = note['paperIds'] == artifact['paperIds'] == before['paperIds']
for case in ('critique', 'compose'):
    receipt = json.loads((HERE / f'stage4-{case}-v6-receipt.json').read_text(encoding='utf-8'))
    with urlopen('http://127.0.0.1:8081/api/task-workspaces/' + receipt['taskId'], timeout=30) as response:
        current = json.load(response)
    checks[case + 'FailedWithoutPublishedArtifact'] = receipt['status'] == 'failed' and current['artifacts'] == []
    assert checks[case + 'FailedWithoutPublishedArtifact']
(HERE / 'stage6-reading-v6-saved-runtime.json').write_text(json.dumps({
    'checks': checks, 'newNote': note, 'newArtifact': artifact, 'task': task,
    'newModelCalls': 0}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'cacheRows': len(responses), 'revision': task['revision'], 'checks': checks}, ensure_ascii=True))
