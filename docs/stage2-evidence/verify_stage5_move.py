"""Local data-only transfer QA. No provider calls; original identities reused."""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
BASE = 'http://localhost:8081/api/task-workspaces'
SOURCE = 'stage5-move-source-20261008'
TARGET = 'stage5-move-target-20261008'
PAPER = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
def http(path, body=None):
    with urlopen(Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'}), timeout=20) as response:
        return json.load(response)
def create(id, **content):
    try: return http('/' + id)
    except HTTPError as error:
        if error.code != 404: raise
        return http('', {'id': id, **content})
notes = [{'id': 'stage5-' + key, 'title': title, 'text': '数据整理验收笔记：重要性包含透射率 T。\n\n这是本地测试正文。',
          'paperIds': [PAPER], 'sources': [{'pdfId': PAPER, 'sourceId': PAPER + '-chunk-15',
            'text': 'Global significance contains opacity, transmittance and adjusted volume.'}],
          'versions': [{'text': '此前的本地测试理解', 'savedAt': '2026-10-08T03:00:00Z'}]} for key, title in
         [('http', 'HTTP移动验收笔记'), ('ui', '界面移动验收笔记')]]
source = create(SOURCE, title='阶段5：移动原任务', paperIds=[PAPER], notes=notes)
target = create(TARGET, title='阶段5：移动目标任务', paperIds=[])
request_id = 'stage5-http-move-20261008'
try: result = http(f'/{SOURCE}/documents/moves/{request_id}')
except HTTPError as error:
    if error.code != 404: raise
    input = {'requestId': request_id, 'targetTaskId': TARGET, 'documentId': 'stage5-http', 'collection': 'notes',
             'sourceRevision': source['revision'], 'targetRevision': target['revision'], 'includeMaterials': False}
    try: http(f'/{SOURCE}/documents/move', input); raise AssertionError('Missing material consent accepted')
    except HTTPError as refusal: assert refusal.code == 409
    assert http('/' + SOURCE) == source and http('/' + TARGET) == target
    input['includeMaterials'] = True
    result = http(f'/{SOURCE}/documents/move', input)
    again = http(f'/{SOURCE}/documents/move', input)
    assert again == result
assert not any(x['id'] == 'stage5-http' for x in result['sourceTask']['notes'])
moved = next(x for x in result['targetTask']['notes'] if x['id'] == 'stage5-http')
assert moved['text'] == notes[0]['text'] and moved['sources'] == notes[0]['sources'] and moved['versions'] == notes[0]['versions']
assert PAPER in result['targetTask']['paperIds']
Path(__file__).with_name('stage5-http-move-runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': result['status'], 'source': SOURCE, 'target': TARGET, 'versions': len(moved['versions'])}))
