"""Create one named UI fixture through Java; no model call or legacy import.

Rerunning only reads the existing fixture, preserving browser edits.
"""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = 'http://localhost:8081/api/task-workspaces'
TASK = 'stage6-reading-demo-20261008'
BODY = '''# 论文阅读小结

> 此正文是人工编写的界面验收样例，用于检查阅读、编辑与保存。

## 我准备怎样阅读

先确认研究问题，再记录方法依赖的假设；遇到术语时保留问题，回到原文核对。

| 阅读步骤 | 要留下的结果 |
| --- | --- |
| 确认问题 | 一句话说明论文要解决什么 |
| 理解方法 | 标出关键假设和输入输出 |
| 检查实验 | 记录对照条件与局限 |

## 我自己的判断

- 总结与原文证据分别保存，避免把解释当成原文。
- 接下来比较另一篇论文的实验设置。
'''

def read():
    with urlopen(BASE + '/' + TASK, timeout=20) as response:
        return json.load(response)

try:
    task = read()
except HTTPError as error:
    if error.code != 404:
        raise
    payload = {'id': TASK, 'title': '阶段6：成果阅读体验验收', 'paperIds': [],
        'notes': [{'id': 'stage6-reading-note', 'title': '我的阅读小结（界面样例）',
            'text': BODY, 'sources': [], 'versions': []}],
        'artifacts': [], 'messages': [], 'activities': []}
    request = Request(BASE, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=20) as response:
        task = json.load(response)
Path(__file__).with_name('stage6-reading-fixture.json').write_text(
    json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'taskId': task['id'], 'revision': task['revision'], 'modelCalls': 0}))
