"""Read-only verification after actual upload while switching tasks."""
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

HERE = Path(__file__).parent
browser = json.loads((HERE / 'stage6-upload-scope-browser.json').read_text(encoding='utf-8'))
restored_a = json.loads((HERE / 'stage6-upload-scope-A-restored.json').read_text(encoding='utf-8'))
restored_b = json.loads((HERE / 'stage6-upload-scope-B-restored.json').read_text(encoding='utf-8'))
tasks = {item['title'][-1]: item['id'] for item in browser['taskOptions']}
base = 'http://127.0.0.1:8081/api/task-workspaces/'
def read(task, suffix=''):
    with urlopen(base + quote(tasks[task], safe='') + suffix, timeout=30) as response:
        return response.read()

a, b = (json.loads(read(task)) for task in ('A', 'B'))
original = Path('D:/3DGS/paper/LightGaussian/2311.17245v6.pdf').read_bytes()
pdf_id = hashlib.sha256(original).hexdigest() + '.pdf'
material = '/materials/' + pdf_id
processing = json.loads(read('A', material + '/processing'))
saved_reading = json.loads((HERE / 'stage6-reading-v5-saved-runtime.json').read_text(encoding='utf-8'))
with urlopen(base + quote(saved_reading['task']['id'], safe=''), timeout=30) as response:
    previous_task = json.load(response)
try:
    read('B', material + '/file')
    task_b_status = 200
except HTTPError as error:
    task_b_status = error.code
checks = {
    'sourceTaskOwnsUploadedPaper': a['paperIds'] == [pdf_id] and a['focusedPaperId'] == pdf_id,
    'otherTaskRemainsEmpty': b['paperIds'] == [] and b['focusedPaperId'] is None,
    'serverFileMatchesOriginal': read('A', material + '/file') == original,
    'taskOutsideScopeFileRejected': task_b_status == 404,
    'noConversationOrLearningCreated': all(not task[key] for task in (a, b) for key in ('messages', 'notes', 'artifacts', 'activeActivity', 'activityHistory')),
    'overviewNotRequested': processing['aiAnalysisStatus'] == 'not_requested',
    'paperReadyForReadingAndQuestions': processing['readingReady'] and processing['questionReady'] and processing['ragIndexed'],
    'browserRemainedOnOtherTask': browser['currentTask'].endswith('-B') and browser['uploadButton'] == '上传 PDF',
    'otherDraftPreserved': browser['draft'] == '任务B草稿：稍后继续，不发送。' and not browser['alerts'],
    'sourceDraftAndReadingRestored': restored_a['draft'] == '任务A草稿：上传结束后继续，不发送。' and restored_a['page'] == '1' and restored_a['canvasCount'] > 0 and restored_a['task'].endswith('-A'),
    'otherDraftAndEmptyStateRestored': restored_b['draft'] == '任务B草稿：稍后继续，不发送。' and '从一篇论文开始' in restored_b['emptyReader'] and restored_b['task'].endswith('-B'),
    'existingReadingTaskPreserved': all(previous_task[key] == saved_reading['task'][key] for key in ('notes', 'artifacts', 'messages', 'revision')),
}
result = {'scope': 'Actual IAB upload followed by task switch and authoritative GET audit, no model answer validation',
    'checks': checks, 'tasks': {key: {'id': task['id'], 'revision': task['revision'], 'paperIds': task['paperIds'], 'focusedPaperId': task['focusedPaperId']} for key, task in (('A', a), ('B', b))},
    'fileBytes': len(original), 'pdfId': pdf_id, 'taskBFileStatus': task_b_status,
    'processing': {key: processing[key] for key in ('processingStatus', 'aiAnalysisStatus', 'readingReady', 'questionReady', 'ragIndexed')},
    'verifierWrites': 0, 'verifierModelRequests': 0,
    'limitations': 'This already-indexed PDF used the existing-file upload path. Draft restoration and original rendering are separate browser observations; no fresh parsing or content quality claimed.'}
(HERE / 'stage6-upload-scope-runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
assert all(checks.values())
