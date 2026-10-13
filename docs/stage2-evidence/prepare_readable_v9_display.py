"""Publish a separate offline display fixture; never rewrite live results."""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

here = Path(__file__).parent
native = next(json.loads(line) for line in (here/'stage4-readable-v9-native-final.log').read_text(encoding='utf-8-sig').splitlines()
              if line.startswith('{"scope":'))
plan = json.loads((here/'stage4-reading-v7-case-plan.json').read_text(encoding='utf-8-sig'))
task_id = 'stage4-readable-display-20261009-v9'
url = 'http://127.0.0.1:8081/api/task-workspaces'
try:
    with urlopen(url+'/'+task_id, timeout=20) as response:
        task = json.load(response)
except HTTPError as error:
    if error.code != 404:
        raise
    result = native['results']['compose']
    artifact = {'id': 'offline-v9-readable-compare', 'kind': 'compare', 'title': '离线展示：简洁比较-v9',
                'text': '**离线展示夹具，不计真实模型验收**\n\n'+result['message'],
                'paperIds': [paper['pdfId'] for paper in plan['materials']], 'sources': result['rag_sources'],
                'metadata': {'verification': 'offline-cache-display', 'partial': True, 'notLiveGeneration': True}}
    request = Request(url, data=json.dumps({'id': task_id, 'title': '阶段4：简洁比较离线展示-v9',
                      'paperIds': artifact['paperIds'], 'artifacts': [artifact]}).encode(),
                      headers={'Content-Type':'application/json'})
    with urlopen(request, timeout=20) as response:
        task = json.load(response)
assert task['artifacts'][0]['text'].startswith('**离线展示夹具')
(here/'stage4-readable-v9-display-task.json').write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'taskId':task_id, 'providerCalls':0, 'artifactCount':len(task['artifacts'])}))
