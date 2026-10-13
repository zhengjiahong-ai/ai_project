"""Explicit, separately receipted repair-only diagnostics; never publish a report."""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read_source(path, run_id):
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        row = conn.execute('SELECT payload FROM deep_research_runs_v2 WHERE run_id=?', (run_id,)).fetchone()
    if row is None:
        raise ValueError('Source run does not exist')
    source = json.loads(row[0])
    if source.get('status') not in {'completed', 'failed'}:
        raise ValueError('Source run must be terminal')
    if not source.get('state', {}).get('reportBody', {}).get('claims'):
        raise ValueError('Source run has no draft')
    return source


class SourceView:
    def __init__(self, source):
        self.source = deepcopy(source)

    def require_run(self, run_id):
        if run_id != self.source['runId']:
            raise ValueError('Unexpected source identity')
        return deepcopy(self.source)


class ParentScope:
    def __init__(self, validator, source_run_id):
        self.validator, self.source_run_id = validator, source_run_id

    def validate_run(self, diagnostic_id):
        return self.validator.validate_run(self.source_run_id)

    def __call__(self, diagnostic_id, material_id):
        return self.validator(self.source_run_id, material_id)


def run_diagnostic(source, output, revision, *, submit=False, client_factory=None, scope=None):
    from services.deep_research.acceptance_receipts import claim_submission, confirm_submission, read_receipt
    from services.deep_research.repository import DeepResearchRepository
    from services.deep_research.runtime import AuthoritativeScopeValidator, ScopedModelClient, research_model, research_model_options
    from services.deep_research.tools import TrackedLLMInvoker, BudgetedSemanticChecker
    from services.deep_research.repair import repair_rejected
    from services.deep_research.repair_budget import repair_prompt_byte_limit
    from services.deep_research.verification import verify_claims
    from services.deep_research.graph import _safe_parse_json

    output = Path(output)
    intent = {'sourceRunId': source['runId'], 'sourceDigest': hashlib.sha256(
        json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'runnerDigest': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'revision': revision, 'mode': 'repair_and_verify_only', 'maxModelCalls': 4,
        'isEndToEndAcceptance': False}
    receipt, result_path = output / 'receipt.json', output / 'result.json'
    if receipt.exists():
        if read_receipt(receipt)['intent'] != intent:
            raise ValueError('Existing receipt belongs to different inputs')
        if result_path.exists():
            return json.loads(result_path.read_text(encoding='utf-8'))
        raise ValueError('Existing attempt has no final result; inspect its ledger, never automatically resend')
    if not submit:
        return {'preview': True, 'intent': intent}
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'ledger.sqlite3').exists():
        raise ValueError('Unreceipted existing ledger; refuse to overwrite')
    claim_submission(receipt, intent)  # Durable intent before any model request.
    repo = DeepResearchRepository(str(output / 'ledger.sqlite3'))
    repo.initialize()
    run_id = 'repair_diag_' + uuid.uuid4().hex
    payload = {key: deepcopy(source[key]) for key in
               ('taskId', 'materials', 'materialSnapshot', 'sourcePolicy', 'question') if key in source}
    payload.update(runId=run_id, workspaceId='repair-diagnostics', idempotencyKey=run_id,
                   status='running', startedAt=datetime.now(UTC).isoformat(),
                   budget={'profile': 'standard', 'maxModelCalls': 4, 'reserveModelCalls': 3,
                           'maxTokens': 100000, 'reserveTokens': 50000, 'maxWallClockSeconds': 240})
    repo.create_run(payload)
    confirm_submission(receipt, run_id)
    scope = scope or ParentScope(AuthoritativeScopeValidator(SourceView(source), origin=os.environ.get(
        'DEEP_RESEARCH_JAVA_ORIGIN', 'http://127.0.0.1:8081/api')), source['runId'])
    model = ScopedModelClient(repo, scope, client_factory or research_model).for_run(run_id)
    invoke = TrackedLLMInvoker(model, repo.reserve_call, repo.complete_call, request_options=research_model_options)
    domain = source['state']
    result = {'intent': intent, 'diagnosticRunId': run_id, 'status': 'running', 'qualityAccepted': False}
    try:
        # Re-check current structure; no prior model verdict is silently trusted.
        initial = verify_claims(domain['reportBody']['claims'], domain['evidence'])
        revised = repair_rejected(domain['reportBody'], initial, domain['evidence'], source['question'],
            lambda prompt: invoke(run_id, 'repair_claims', prompt, {'max_tokens': 8192}),
            _safe_parse_json, max_prompt_bytes=min(repair_prompt_byte_limit(source['budget']),
                repair_prompt_byte_limit(repo.require_run(run_id)['budget'])),
            metric_domains=domain.get('metricDomains'))
        checked = verify_claims(revised, domain['evidence'], BudgetedSemanticChecker(
            invoke, run_id, metric_domains=domain.get('metricDomains')))
        result.update(status='completed', revised=revised, verification=checked)
        repo.update_run(run_id, lambda r: {**r, 'status': 'completed', 'outcome': 'partial'})
    except Exception as exc:
        # The tracked ledger retains raw response or unknown-call state. Never retry.
        result.update(status='error', errorType=type(exc).__name__, errorCode=getattr(exc, 'code', None))
    result['budget'] = repo.require_run(run_id)['budget']
    with result_path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', type=Path, required=True)
    parser.add_argument('--source-run', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--submit', action='store_true')
    args = parser.parse_args()
    if args.source_db.resolve() == (args.output / 'ledger.sqlite3').resolve():
        raise ValueError('Diagnostic ledger must not be the source database')
    result = run_diagnostic(read_source(args.source_db, args.source_run), args.output,
                            args.revision, submit=args.submit)
    print(json.dumps({key: value for key, value in result.items() if key not in {'revised', 'verification'}},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
