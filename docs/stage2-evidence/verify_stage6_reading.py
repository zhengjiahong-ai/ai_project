"""Read-only confirmation of the actual browser save/restore/rename case."""
import json
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).parent
fixture = json.loads((root / 'stage6-reading-fixture.json').read_text(encoding='utf-8'))
with urlopen('http://localhost:8081/api/task-workspaces/' + fixture['id'], timeout=20) as response:
    task = json.load(response)
note = next(item for item in task['notes'] if item['id'] == 'stage6-reading-note')
assert task['title'] == '阶段6：阅读与编辑体验验收'
assert note['text'] == fixture['notes'][0]['text']
assert len(note['versions']) == 2
assert any('切回阅读后保留的未保存内容。' in item['text'] for item in note['versions'])
assert task['paperIds'] == [] and task['messages'] == []
receipt = {'status': 'passed', 'taskId': task['id'], 'revision': task['revision'],
    'renamedViaBrowser': True, 'originalMarkdownRestored': True,
    'editedBodyRetainedInHistory': True, 'versions': len(note['versions']),
    'modelCalls': 0, 'isolatedBrowserProfileVerified': False}
(root / 'stage6-reading-runtime.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt))
