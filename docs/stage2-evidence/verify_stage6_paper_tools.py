"""Read the named browser fixture from Java; never submit model requests."""
import json
from pathlib import Path
from urllib.request import urlopen

TASK = 'stage6-paper-tools-20261008'
A = 'f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf'
B = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
with urlopen('http://localhost:8081/api/task-workspaces/' + TASK, timeout=20) as response:
    task = json.load(response)
notes = [note for note in task['notes'] if note.get('title') == '原文笔记']
assert len(notes) == 1, 'Expected exactly one saved browser selection note'
note = notes[0]
assert note['text'] == 'shot'
assert note['paperIds'] == [B]
assert note['source']['sourcePageIndex'] == 3
assert note['source']['sourceAnchorId']
assert note['sources'][0]['pdfId'] == B
assert note['sources'][0]['pageIndex'] == 3
assert note['sources'][0]['sourceId'] == note['source']['sourceAnchorId']
assert task['paperIds'] == [A, B] and task['focusedPaperId'] == B
assert not task['messages']
assert any(n['id'] == 'stage6-paper-position-note' and '人工界面验收笔记' in n['text'] for n in task['notes'])
receipt = {'taskId': TASK, 'revision': task['revision'], 'checks': {
    'selectionNoteSavedExactlyOnce': True, 'originalTextPreserved': True,
    'paperAndPageSourcePreserved': True, 'sourceAnchorPreserved': True,
    'twoTaskMaterialsAndFocusedPaperPreserved': True,
    'noMessagesInFixture': True, 'artificialFixtureClearlyLabeled': True},
    'method': 'Read-only Java task API, separate from browser observations',
    'selectionNote': note, 'modelRequestsSubmittedByThisVerifier': 0}
Path(__file__).with_name('stage6-paper-tools-runtime.json').write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'taskId': TASK, 'revision': task['revision'], 'checks': receipt['checks']}))
