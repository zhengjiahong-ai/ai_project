"""Two fixed API cases against the real index. Submit each once; resume polling only."""
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/critique-evidence-20261011'
TASK = 'critique-final-20261011'
PAPER = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
BASE = 'http://localhost:8081/api/task-workspaces/' + quote(TASK, safe='')
CASES = {
    'focused': '只依据LightGaussian：压缩后“画质几乎不变”的主张在什么条件下成立？给最关键的两点，150字以内，不做全面综述，不写具体数值。每个结论句尽量简短，优先核对直接实验及条件。',
    'review': '对LightGaussian作批判阅读：最影响复现和使用决策的两个判断是什么？区分作者报告、设计推断和待核查问题。每个结论句最多70字，不写具体数值，不强行给机制配缺点。',
}
final = '--final' in sys.argv
names = [arg for arg in sys.argv[1:] if arg != '--final'] or list(CASES)
for name in names:
    if name not in CASES:
        raise SystemExit('Unknown fixed case')
    label = 'complete-' + name if final else name
    request_id = 'critique-final-' + label
    attempt = OUT / f'runtime-{label}-attempt.json'
    result = OUT / f'runtime-{label}.json'
    if result.exists():
        print(name, 'retained result; no submission', flush=True)
        continue
    if not attempt.exists():
        task = requests.get(BASE, timeout=15).json()
        payload = {'requestId': request_id, 'kind': 'conversation.execute', 'input': {
            'expectedTaskRevision': task['revision'], 'message': CASES[name], 'displayText': '/批判 ' + CASES[name],
            'capability': 'critique', 'allowedPaperIds': task['paperIds'], 'primaryPaperId': PAPER,
            'strictScope': False, 'targetPaperIds': [PAPER]}}
        attempt.write_text(json.dumps({'payload': payload, 'submittedOnce': True}, ensure_ascii=False, indent=2), encoding='utf8')
        response = requests.post(BASE + '/operations', json=payload, timeout=30)
        if not response.ok:
            result.write_text(json.dumps({'httpStatus': response.status_code, 'body': response.text}, ensure_ascii=False, indent=2), encoding='utf8')
            print(name, 'submission failed', response.status_code, flush=True)
            continue
        print(name, 'submitted once', flush=True)
    for _ in range(100):
        response = requests.get(BASE + '/operations/' + request_id, timeout=30)
        response.raise_for_status()
        value = response.json()
        if value.get('status') not in ('queued', 'running', 'cancelling'):
            result.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
            packet = value.get('result') or {}
            print(json.dumps({'case': name, 'status': value.get('status'), 'error': value.get('error'),
                              'partial': packet.get('partial'), 'message': packet.get('message'),
                              'issues': len((packet.get('critique') or {}).get('issues') or [])}, ensure_ascii=False), flush=True)
            break
        time.sleep(5)
    else:
        print(name, 'polling deadline; resume polling only, never resubmit', flush=True)
