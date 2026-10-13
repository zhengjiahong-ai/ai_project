"""Two authorized fixed repair cases. One submit attempt per identity, GET-only queries thereafter."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

A = 'f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf'
B = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
CASES = {
    'critique': ([B], '重点批判LightGaussian的15倍压缩与200+FPS主张：证据适用于哪些场景、比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？区分作者原文、推断及未检索覆盖，不能把片段缺失当作论文缺陷。', []),
    'compose': ([A, B], '先用两句话解释3DGS的高斯、透明度与球谐颜色，再比较原始3DGS与LightGaussian如何在表示规模、质量和渲染速度之间取舍。对比较中的每篇论文给出原文依据。', ['chat', 'compare']),
}
case, action = sys.argv[1:3]
assert action in {'start', 'query'} and case in CASES
papers, question, steps = CASES[case]
task_id = f'stage4-3dgs-{case}-20261008-v3'
request_id = f'{task_id}-request'
base = 'http://127.0.0.1:8081/api/task-workspaces'
here = Path(__file__).parent
attempt = here / f'stage4-{case}-v3-attempt.json'
receipt_path = here / f'stage4-{case}-v3-receipt.json'


def http(path, body=None):
    request = Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


try:
    receipt = http(f'/{task_id}/operations/{request_id}')
except HTTPError as error:
    if error.code != 404 or action != 'start':
        raise
    if attempt.exists():
        raise RuntimeError('An earlier submit attempt was recorded. Query only; do not automatically resubmit.')
    try:
        task = http('/' + task_id)
    except HTTPError as missing:
        if missing.code != 404:
            raise
        task = http('', {'id': task_id, 'title': f'阶段4：{case}修复核验-v3', 'paperIds': papers})
    for paper in papers:
        status = http(f'/{task_id}/materials/{paper}/processing')
        assert status['questionReady'], 'Material must be indexed before generation'
    body = {'requestId': request_id, 'kind': 'conversation.execute', 'input': {
        'message': question, 'capability': case, 'steps': steps, 'allowedPaperIds': papers,
        'strictScope': case == 'critique', 'primaryPaperId': B if case == 'critique' else None,
        'expectedTaskRevision': task['revision'], 'allowExternalSearch': False}}
    with attempt.open('x', encoding='utf-8') as stream:
        json.dump({'authorization': 'User explicitly approved at most 4 fixed cases; this is one of critique/compose/translation/selection',
                   'taskId': task_id, 'requestId': request_id, 'request': body,
                   'submitAttempts': 1, 'automaticRetryAllowed': False}, stream, ensure_ascii=False, indent=2)
    receipt = http(f'/{task_id}/operations', body)

receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
if receipt['status'] == 'succeeded':
    result = receipt['result']
    assert result['capability'] == case and result['materialScope']['allowedPaperIds'] == papers
    assert result['artifact']['text'] and len(result['message']) <= 600
    assert all(source['pdfId'] in papers for source in result['sources'])
    task = http('/' + task_id)
    assert len(task['artifacts']) == 1
    assert len([item for item in task['messages'] if item.get('artifactId') == task['artifacts'][0]['id']]) == 1
print(json.dumps({'case': case, 'taskId': task_id, 'requestId': request_id,
                  'status': receipt['status'], 'error': receipt.get('error')}, ensure_ascii=False))
