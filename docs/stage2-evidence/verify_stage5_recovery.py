"""Read-only HTTP verification after the real browser version/conflict cases.

No IndexedDB, AI execution, retries, uploads or writes to task data.
This verifies an independent HTTP client, not an isolated browser profile.
"""
import hashlib
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

BASE = 'http://localhost:8081/api/task-workspaces'
TASK = 'stage5-version-recovery-20261008'
PAPER = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=Path(__file__).with_name('stage5-recovery-client-runtime.json'))
args = parser.parse_args()


def read(path):
    with urlopen(BASE + path, timeout=20) as response:
        return json.load(response)


task = read('/' + TASK)
version = next(note for note in task['notes'] if note['id'] == 'stage5-version-note')
assert version['text'] == ''
assert any(v['text'] == '已保存正文 A' for v in version['versions'])
assert any(v['text'] == '未保存草稿 D' and v['kind'] == 'unsaved-draft' for v in version['versions'])
assert len(version['sources']) == 1
conflict = next(note for note in task['notes'] if note['id'] == 'stage5-conflict-note')
assert conflict['text'] == '未保存冲突草稿 E'
assert any(v['text'] == '另一个客户端已保存正文 F' for v in conflict['versions'])
with urlopen(f'{BASE}/{TASK}/materials/{PAPER}/file', timeout=20) as response:
    pdf = response.read()
assert pdf.startswith(b'%PDF-') and hashlib.sha256(pdf).hexdigest() + '.pdf' == PAPER
analysis = read(f'/{TASK}/materials/{PAPER}/analysis')
assert analysis['pdfId'] == PAPER and analysis['readingReady'] is True
missing = read('/stage5-missing-file-20261008')
assert missing['notes'][0]['text'] == '原笔记仍可访问；本案例不恢复全部旧论文。'
try:
    read('/stage5-missing-file-20261008/materials/2311.17245v6.pdf/file')
    raise AssertionError('Missing file must not be reported as available')
except HTTPError as failure:
    assert failure.code == 404

identity = json.loads(Path(__file__).with_name('stage5-identity-runtime.json').read_text(encoding='utf-8-sig'))
identity_id = identity['originalTask']['id']
backup = read(f"/{identity_id}/migration-backups/{identity['backupId']}")
assert backup == identity['originalTask'], 'Original identity-repair backup changed'
identified = read('/' + identity_id)
assert identified['notes'] == identity['identifiedTask']['notes'], 'Identified documents lost content or identity'
assert identified['revision'] == identity['identifiedTask']['revision']

move = json.loads(Path(__file__).with_name('stage5-ui-move-after-restart.json').read_text(encoding='utf-8-sig'))
target, source = read('/' + move['targetTask']['id']), read('/' + move['sourceTask']['id'])
for expected in move['targetTask']['notes']:
    current = next(note for note in target['notes'] if note['id'] == expected['id'])
    assert current == expected, 'Moved note content, versions or sources changed'
    assert all(note.get('id') != expected['id'] for note in source['notes'])
assert set(move['targetTask']['paperIds']).issubset(target['paperIds'])
receipt = {'status': 'passed', 'taskId': TASK, 'revision': task['revision'],
    'checkedAt': datetime.now(timezone.utc).isoformat(),
    'emptyBodyRetained': True, 'savedAndUnsavedVersionsRetained': True,
    'confirmedConflictPreservesOtherVersion': True, 'sourcesRetained': True,
    'independentHttpClient': True, 'isolatedBrowserProfileVerified': False,
    'pdfHashMatchesId': True, 'pdfBytes': len(pdf), 'analysisReadingReady': True,
    'identityBackupUnchanged': True, 'identifiedDocumentsUnchanged': True,
    'movedNotesAndMaterialAssociationsRetained': True,
    'missingFileIs404AndNotesRetained': True}
args.output.write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt))
