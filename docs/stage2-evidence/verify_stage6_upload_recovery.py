"""Read-only server verification after the browser upload; never submits AI work."""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen


def get(url):
    with urlopen(url, timeout=20) as response:
        return response.read()


task_id = 'task:acaca995-12ca-4ecb-883f-8fb26899db30'
source = Path('D:/3DGS/paper/3DGV/3DGV_3D_Gaussian_Splatting-Based_Holographic_Video_Streaming_over_Wireless_Networks.pdf')
original = source.read_bytes()
paper_id = hashlib.sha256(original).hexdigest() + '.pdf'
base = 'http://127.0.0.1:8081/api/task-workspaces/' + quote(task_id, safe='')
task = json.loads(get(base))
material = base + '/materials/' + paper_id
processing = json.loads(get(material + '/processing'))
health = json.loads(get('http://127.0.0.1:8000/health'))
assert task['paperIds'] == [paper_id]
assert task['focusedPaperId'] == paper_id
assert not any(task[key] for key in ['messages', 'notes', 'artifacts', 'activeActivity', 'activityHistory'])
assert get(material + '/file') == original
assert processing['processingStatus'] == 'ready'
assert processing['readingReady'] and processing['questionReady'] and processing['ragIndexed']
assert processing['aiAnalysisStatus'] == 'not_requested'
assert health['status'] == 'ok'
receipt = {
    'method': 'Read-only Java task, file bytes, processing status and Python health after actual browser upload/retry',
    'task': {'id': task_id, 'revision': task['revision'], 'paperIds': task['paperIds'], 'focusedPaperId': task['focusedPaperId']},
    'fileBytes': len(original),
    'processing': {key: processing.get(key) for key in ['status', 'processingStatus', 'readingReady', 'questionReady', 'ragIndexed', 'aiAnalysisStatus']},
    'checks': {'exactServerFileBytes': True, 'focusedTaskMaterial': True, 'parsingAndIndexReady': True,
               'noMessagesNotesArtifactsOrLearningActivities': True, 'overviewNotRequested': True, 'serviceHealthOk': True},
    'modelRequestsSubmittedByThisVerifier': 0,
    'limitation': 'Browser file chooser, page 4 and draft recovery are separate UI observations; this GET-only check does not prove model answer quality.'
}
Path(__file__).with_name('stage6-upload-recovery-runtime.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checks': receipt['checks'], 'fileBytes': len(original)}, ensure_ascii=False))
