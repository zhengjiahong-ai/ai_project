"""Read only the two tasks created through the browser; no AI requests."""
import json
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote

ids = ['task:acaca995-12ca-4ecb-883f-8fb26899db30', 'task:f8b18af5-9681-4bda-ad15-30fd2f3dbafe']
titles = ['阶段6：首次使用与任务输入验收', '阶段6：有材料的对话起点验收']
paper = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
tasks = []
for task_id in ids:
    with urlopen('http://127.0.0.1:8081/api/task-workspaces/' + quote(task_id, safe=''), timeout=15) as response:
        tasks.append(json.load(response))
for task, title in zip(tasks, titles):
    assert task['title'] == title
    assert not task['messages'] and not task['artifacts'] and not task['notes']
    assert not task['activeActivity'] and not task['activityHistory']
assert tasks[0]['paperIds'] == []
assert tasks[1]['paperIds'] == [paper] and tasks[1]['focusedPaperId'] == paper
receipt = {'method': 'Read-only Java tasks, independently checking browser-created fixtures',
    'checks': {'tasksCreatedAndRenamedThroughUI': True, 'emptyTaskNotChangedByInvalidInputOrFailedUpload': True,
        'existingMaterialAttachedToSecondTask': True, 'noMessagesArtifactsOrLearningActivities': True},
    'tasks': [{'id': task['id'], 'title': task['title'], 'revision': task['revision'],
        'paperIds': task['paperIds']} for task in tasks],
    'limitation': 'Input drafts and layout are proven by browser observations, not this server check.',
    'modelRequestsSubmittedByThisVerifier': 0}
Path(__file__).with_name('stage6-onboarding-runtime.json').write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checks': receipt['checks'], 'revisions': [task['revision'] for task in tasks]}))
