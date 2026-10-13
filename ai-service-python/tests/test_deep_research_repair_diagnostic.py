from copy import deepcopy
import json
import sqlite3
import pytest
from llm.provider import LLMResult, LLMUsage, LLMProviderError
from scripts.diagnose_research_repair import run_diagnostic, read_source, ParentScope


def source():
    return {'runId': 'original', 'taskId': 'task', 'status': 'completed',
        'question': 'Design a controlled experiment', 'materials': [{'materialId': 'p'}],
        'materialSnapshot': {'snapshotHash': 'snapshot'}, 'sourcePolicy': {'mode': 'task_only'},
        'budget': {'maxTokens': 100000, 'reserveTokens': 50000, 'tokens': 1000, 'normalTokens': 1000},
        'state': {'reportBody': {'claims': [{'claimId': 'c', 'kind': 'proposal',
            'text': 'Use the same checkpoint.', 'evidenceRefs': [], 'designContractVersion': 2}]},
            'evidence': []}}


class Client:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def invoke(self, request):
        self.calls.append(request)
        if self.fail:
            raise LLMProviderError('timeout', provider='fixture', model='fixture')
        value = ([{**source()['state']['reportBody']['claims'][0], 'designRole': 'controls'}]
                 if len(self.calls) == 1 else [{'claimId': 'c', 'status': 'passed'}])
        return LLMResult('fixture', 'fixture', json.dumps(value), LLMUsage(20, 10, 30), 'stop')


def test_preview_and_completed_receipt_never_send_again(tmp_path):
    data = source()
    before = deepcopy(data)
    client = Client()
    args = dict(client_factory=lambda: client, scope=lambda *args: True)
    assert run_diagnostic(data, tmp_path, 'revision', **args)['preview']
    assert not list(tmp_path.iterdir())
    result = run_diagnostic(data, tmp_path, 'revision', submit=True, **args)
    assert result['status'] == 'completed'
    assert result['verification']['accepted'][0]['designRole'] == 'controls'
    assert len(client.calls) == 2 and not result['qualityAccepted']
    assert not result['intent']['isEndToEndAcceptance']
    assert run_diagnostic(data, tmp_path, 'revision', submit=True, **args) == result
    assert len(client.calls) == 2 and data == before
    with pytest.raises(ValueError, match='different inputs'):
        run_diagnostic(data, tmp_path, 'other revision', submit=True, **args)


def test_unknown_call_keeps_ledger_and_is_not_reissued(tmp_path):
    client = Client(fail=True)
    args = dict(client_factory=lambda: client, scope=lambda *args: True, submit=True)
    result = run_diagnostic(source(), tmp_path, 'revision', **args)
    assert result['status'] == 'error' and len(client.calls) == 1
    assert run_diagnostic(source(), tmp_path, 'revision', **args) == result
    assert len(client.calls) == 1
    with sqlite3.connect(tmp_path / 'ledger.sqlite3') as conn:
        assert conn.execute('SELECT status FROM deep_research_calls_v2').fetchone()[0] == 'unknown'


def test_scope_revocation_prevents_provider_send(tmp_path):
    client = Client()
    result = run_diagnostic(source(), tmp_path, 'revision', submit=True,
        client_factory=lambda: client, scope=lambda *args: False)
    assert result['status'] == 'error' and not client.calls


def test_source_read_is_readonly_and_missing_source_is_not_created(tmp_path):
    path = tmp_path / 'source.sqlite3'
    with pytest.raises(sqlite3.OperationalError):
        read_source(path, 'original')
    assert not path.exists()
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE deep_research_runs_v2 (run_id TEXT, payload TEXT)')
        conn.execute('INSERT INTO deep_research_runs_v2 VALUES (?,?)', ('original', json.dumps(source())))
    before = path.read_bytes()
    assert read_source(path, 'original') == source()
    assert path.read_bytes() == before


def test_scope_checks_use_original_registered_run_and_exact_material():
    calls = []
    class Validator:
        def validate_run(self, run):
            calls.append(run)
            return True
        def __call__(self, run, material):
            calls.append((run, material))
            return False
    scope = ParentScope(Validator(), 'original')
    assert scope.validate_run('diagnostic')
    assert not scope('diagnostic', 'p')
    assert calls == ['original', ('original', 'p')]
