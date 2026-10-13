"""Run one frozen acceptance case explicitly; existing receipts are GET-only.

Default invocation previews the case without HTTP. --submit permits a single
submission, not retries. A receipt with unknown outcome requires reconciliation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.deep_research.acceptance_receipts import claim_submission, confirm_submission, read_receipt


def run_case(manifest, case_id, attempt, directory, api, *, submit=False,
             task_id=None, parent_run_id=None, check_ready=None):
    if attempt < 1:
        raise ValueError('attempt must be positive')
    case = next((c for c in manifest['cases'] if c['id'] == case_id), None)
    if not case or not case.get('question'):
        raise ValueError('Select a model case; fault-injection cases use offline tests.')
    if case.get('mode') == 'continuation' and not (parent_run_id and task_id):
        raise ValueError('Continuation needs an existing task and parent run.')
    materials = [manifest['materials'][key]['sha256'] + '.pdf' for key in case['materials']]
    task_id = task_id or f"dr-acceptance-{case_id.lower()}-{manifest['frozenAt']}"
    intent = {'caseId': case_id, 'split': case['split'], 'attempt': attempt,
              'taskId': task_id, 'parentRunId': parent_run_id, 'question': case['question'],
              'materialIds': materials, 'outputKind': case['kind'], 'sourcePolicy': case['policy'],
              'budgetProfile': manifest['budgetProfile'], 'manifestVersion': manifest['version']}
    receipt = Path(directory) / f'{case_id}-v{attempt}.json'
    task_path = '/task-workspaces/' + quote(task_id, safe='')
    if receipt.exists():
        saved = read_receipt(receipt)
        if saved['intent'] != intent:
            raise ValueError('Receipt belongs to different inputs; do not reuse this attempt.')
        if not saved['runId']:
            raise ValueError('Submission outcome is unconfirmed; reconcile it before any new request.')
    elif not submit:
        return {'preview': True, 'intent': intent}
    else:
        if check_ready is not None:
            check_ready()  # Before workspace mutations or durable submission intent.
        task = api('GET', task_path, allow_missing=True)
        if task is None:
            if parent_run_id:
                raise ValueError('Parent task is missing')
            task = api('POST', '/task-workspaces', payload={
                'id': task_id, 'title': '深度研究验收 · ' + case_id,
                'paperIds': materials, 'focusedPaperId': materials[0] if materials else None,
                'notes': [], 'messages': [], 'artifacts': [], 'researchRuns': []})
        if not set(materials) <= set(task.get('paperIds', [])):
            raise ValueError('Frozen case materials are missing from this task')
        request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(intent, sort_keys=True, ensure_ascii=False)))
        payload = {'requestId': request_id, 'question': case['question'],
                   'budgetProfile': manifest['budgetProfile']}
        if parent_run_id:
            parent_path = task_path + '/research/' + quote(parent_run_id, safe='')
            parent = api('GET', parent_path)['task']
            if parent.get('taskId') != task_id or parent.get('runId') != parent_run_id:
                raise ValueError('Parent identity mismatch')
            payload['expectedRunRevision'] = parent['runRevision']
            path = parent_path + '/continue'
        else:
            payload.update(engineVersion='deep-research-v2', contractVersion=2,
                           expectedTaskRevision=task['revision'],
                           materialSelection={'mode': 'explicit' if materials else 'external_only', 'materialIds': materials},
                           focusPaperIds=materials[:1] if case['kind'] == 'claim_verification' else [],
                           sourcePolicy={'mode': case['policy']}, outputKind=case['kind'])
            path = task_path + '/research/start'
        claim_submission(receipt, intent)  # Durable exclusive intent BEFORE model-capable POST.
        result = api('POST', path, payload=payload)
        state = result['task']
        if state.get('taskId') != task_id:
            raise ValueError('Returned task identity mismatch; receipt remains unconfirmed')
        saved = confirm_submission(receipt, state['runId'])
    result = api('GET', task_path + '/research/' + quote(saved['runId'], safe=''))
    state = result.get('task', {})
    if state.get('runId') != saved['runId'] or state.get('taskId') != task_id:
        raise ValueError('Read identity mismatch')
    receipt.with_suffix('.result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'caseId': case_id, 'runId': saved['runId'], 'status': state.get('status'),
            'outcome': state.get('outcome'), 'budget': state.get('budget'), 'error': state.get('error')}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--manifest', type=Path, default=root / 'docs/DEEP_RESEARCH_ACCEPTANCE_CASES_20261012.json')
    parser.add_argument('--receipts', type=Path, default=root / 'tmp/dr-acceptance-receipts')
    parser.add_argument('--origin', default='http://127.0.0.1:8081/api')
    parser.add_argument('--ai-origin', default='http://127.0.0.1:8000')
    parser.add_argument('--task-id')
    parser.add_argument('--parent-run-id')
    args = parser.parse_args()
    import requests
    def check_ready():
        response = requests.get(args.ai_origin.rstrip('/') + '/health', timeout=5)
        response.raise_for_status()
        require_ready_health(response.json())
    def api(method, path, *, payload=None, allow_missing=False):
        response = requests.request(method, args.origin.rstrip('/') + path, json=payload, timeout=25)
        if allow_missing and response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    result = run_case(json.loads(args.manifest.read_text(encoding='utf-8')), args.case, args.attempt,
                      args.receipts, api, submit=args.submit, task_id=args.task_id,
                      parent_run_id=args.parent_run_id, check_ready=check_ready)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def require_ready_health(health):
    if (not isinstance(health, dict) or health.get('status') != 'ok'
            or not isinstance(health.get('checks'), dict)
            or any(not isinstance(health['checks'].get(name), dict)
                   or health['checks'][name].get('status') != 'ok' for name in ('rag', 'grobid'))):
        raise RuntimeError('AI service is not ready; no case submitted. Check API, RAG and GROBID.')


if __name__ == '__main__':
    main()
