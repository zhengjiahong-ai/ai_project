"""Create a named task for real PDF navigation, without model calls."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = 'http://localhost:8081/api/task-workspaces'
TASK = 'stage6-paper-tools-20261008'
A = 'f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf'
B = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
try:
    with urlopen(BASE + '/' + TASK, timeout=20) as response:
        task = json.load(response)
except HTTPError as error:
    if error.code != 404:
        raise
    payload = {'id': TASK, 'title': '阶段6：真实论文阅读工具验收', 'paperIds': [A, B], 'focusedPaperId': B,
        'notes': [{'id': 'stage6-paper-position-note', 'title': '阅读位置验收（界面样例）',
            'text': '人工界面验收笔记：打开成果后应能返回原阅读页；点击来源应定位到LightGaussian第4页。',
            'paperIds': [B], 'sources': [{'sourceId': 'stage6-page4', 'pdfId': B, 'pageIndex': 3,
                'label': 'LightGaussian 第4页', 'text': 'Global Significance Calculation.'}], 'versions': []}],
        'artifacts': [], 'messages': [], 'activities': []}
    request = Request(BASE, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=20) as response:
        task = json.load(response)
Path(__file__).with_name('stage6-paper-tools-fixture.json').write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'id': task['id'], 'revision': task['revision'], 'modelCalls': 0}))
