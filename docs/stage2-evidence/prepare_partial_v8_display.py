"""Create a clearly labelled local display fixture, never a live acceptance result."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
native = next(json.loads(line) for line in (HERE / 'stage4-partial-v8-native-verified.log').read_text(encoding='utf-8-sig').splitlines()
              if line.startswith('{"scope":'))
plan = json.loads((HERE / 'stage4-reading-v7-case-plan.json').read_text(encoding='utf-8-sig'))
task_id = 'stage4-partial-display-20261009-v8'
base = 'http://127.0.0.1:8081/api/task-workspaces'
artifacts = [{'id': f'offline-v8-{kind}', 'kind': kind, 'title': f'离线展示：{kind}部分结果',
              'text': '**离线展示夹具，不计真实模型验收**\n\n' + result['message'],
              'paperIds': [item['pdfId'] for item in plan['materials']], 'sources': result['rag_sources'],
              'metadata': {'verification': 'offline-cache-display', 'partial': True, 'notLiveGeneration': True}}
             for kind, result in native['results'].items()]
try:
    with urlopen(base + '/' + task_id, timeout=20) as response:
        task = json.load(response)
except HTTPError as error:
    if error.code != 404:
        raise
    request = Request(base, data=json.dumps({'id': task_id, 'title': '阶段4：部分结果离线展示-v8',
                                            'paperIds': [item['pdfId'] for item in plan['materials']],
                                            'artifacts': artifacts}).encode(), headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=20) as response:
        task = json.load(response)
assert all(item['text'].startswith('**离线展示夹具') for item in task['artifacts'])
if any(old['text'] != new['text'] for old, new in zip(task['artifacts'], artifacts)):
    assert [item['id'] for item in task['artifacts']] == [item['id'] for item in artifacts]
    task['artifacts'] = [{**old, 'text': new['text']} for old, new in zip(task['artifacts'], artifacts)]
    request = Request(base + '/' + task_id, data=json.dumps(task).encode(), method='PUT',
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=20) as response:
        task = json.load(response)
(HERE / 'stage4-partial-v8-display-task.json').write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'taskId': task_id, 'artifactCount': len(task['artifacts']), 'providerCalls': 0,
                  'scope': 'Two local fixture artifacts only; original failed operations untouched'}))
