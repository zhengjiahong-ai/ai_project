import json
import threading

import pytest

from services.deep_research.contracts import BudgetExhaustedError, DeepResearchError
from services.deep_research.facade import ResearchFacade
from services.deep_research.repository import DeepResearchRepository
from services.deep_research.repair import repair_rejected
from services.deep_research.verification import verify_claims


def test_repair_cannot_widen_identity_evidence_or_disguise_fact_as_proposal():
    original = {'claimId': 'c', 'kind': 'reported', 'text': '999 FPS', 'evidenceRefs': ['e']}
    verification = {'accepted': [], 'rejected': [{'claimId': 'c', 'reason': 'numeric_mismatch'}]}
    calls = []
    def invoke(prompt):
        calls.append(prompt)
        return {'content': json.dumps([
            {**original, 'kind': 'proposal'},
            {**original, 'claimId': 'new'},
            {**original, 'evidenceRefs': ['foreign']},
        ])}
    assert repair_rejected({'claims': [original]}, verification, [], '核查', invoke, json.loads) == []
    assert len(calls) == 1


def test_repaired_wording_must_pass_numeric_and_semantic_checks_again():
    original = {'claimId': 'c', 'kind': 'reported', 'text': '999 FPS', 'evidenceRefs': ['e']}
    check = {'accepted': [], 'rejected': [{'claimId': 'c', 'reason': 'numeric_mismatch'}]}
    evidence = [{'evidenceId': 'e', 'quote': '200 FPS', 'verification': {'literal': 'passed'}}]
    revised = repair_rejected({'claims': [original]}, check, evidence, '核查，100字以内',
        lambda p: {'content': json.dumps([{**original, 'text': '速度为200 FPS', 'conditions': '本次评测'}])}, json.loads)
    assert revised[0]['conditions'] == {'context': '本次评测'}
    assert not verify_claims(revised, evidence)['accepted']
    assert verify_claims(revised, evidence, lambda c, e: [{'claimId': 'c', 'status': 'passed'}])['accepted']
    overlong = lambda p: {'content': json.dumps([{**original, 'text': 'x' * 101}])}
    assert repair_rejected({'claims': [original]}, check, evidence, '100字以内', overlong, json.loads) == []


def test_repair_can_use_acquired_same_version_passage_but_must_reverify():
    original = {'claimId': 'c', 'kind': 'reported', 'text': '属性依赖视角。',
                'evidenceRefs': ['e1'], 'obligationIds': ['mechanism']}
    base = {'sourceWorkId': 'paper', 'sourceVersionId': 'v1', 'accessLevel': 'fulltext',
            'verification': {'literal': 'passed'}}
    evidence = [dict(base, evidenceId='e1', quote='Attributes depend on the viewing position.',
                     obligationIds=['mechanism']),
                dict(base, evidenceId='e2', quote='Inside the frustum, directions and distances condition the attributes.',
                     obligationIds=['generalization'])]
    revised = dict(original, text='视锥内根据方向和距离预测属性。', evidenceRefs=['E2'],
                   obligationIds=['invented'])
    def invoke(prompt):
        assert '"c": ["E1", "E2"]' in prompt
        return {'content': json.dumps([revised])}
    result = repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'c'}]},
                             evidence, '说明机制', invoke, json.loads)
    assert result[0]['evidenceRefs'] == ['e2']
    assert result[0]['obligationIds'] == ['mechanism']
    assert not verify_claims(result, evidence)['accepted']
    checked = verify_claims(result, evidence, lambda *_: [{'claimId': 'c', 'status': 'passed'}])
    assert checked['accepted']


@pytest.mark.parametrize('foreign', [
    {'sourceWorkId': 'another-paper'}, {'sourceVersionId': 'v2'},
    {'verification': {'literal': 'failed'}}, {'accessLevel': 'abstract'},
])
def test_repair_cannot_add_foreign_or_untrusted_passage(foreign):
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'fact', 'evidenceRefs': ['e1'],
                'obligationIds': ['o']}
    base = {'sourceWorkId': 'paper', 'sourceVersionId': 'v1', 'accessLevel': 'fulltext',
            'verification': {'literal': 'passed'}, 'obligationIds': ['o'], 'quote': 'source passage'}
    evidence = [dict(base, evidenceId='e1'), dict(base, evidenceId='foreign', **foreign)]
    def invoke(prompt):
        assert '"evidenceId": "E2"' not in prompt
        return {'content': json.dumps([dict(original, evidenceRefs=['foreign'])])}
    assert repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'c'}]},
                           evidence, '', invoke, json.loads) == []


def test_repair_cannot_cite_candidate_omitted_by_prompt_byte_limit():
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'fact', 'evidenceRefs': ['e1'],
                'obligationIds': ['o']}
    base = {'sourceWorkId': 'paper', 'sourceVersionId': 'v1', 'accessLevel': 'fulltext',
            'verification': {'literal': 'passed'}, 'obligationIds': ['o']}
    evidence = [dict(base, evidenceId='e1', quote='Known original passage.'),
                dict(base, evidenceId='huge', quote='x' * 25000)]
    def invoke(prompt):
        assert 'x' * 1000 not in prompt
        assert '"c": ["E1"]' in prompt
        return {'content': json.dumps([dict(original, evidenceRefs=['huge'])])}
    assert repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'c'}]},
                           evidence, '', invoke, json.loads) == []


def test_missing_aspect_hint_prioritizes_late_passage_without_allowing_foreign_source():
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'fact', 'evidenceRefs': ['anchor'],
                'obligationIds': ['o']}
    base = {'sourceWorkId': 'paper', 'sourceVersionId': 'v1', 'accessLevel': 'fulltext',
            'verification': {'literal': 'passed'}, 'obligationIds': ['o']}
    evidence = [dict(base, evidenceId='anchor', quote='Original passage.')]
    evidence.extend(dict(base, evidenceId=f'e{i}', quote='Earlier but irrelevant passage.') for i in range(20))
    evidence.extend([dict(base, evidenceId='late', quote='Essential late condition.'),
                     dict(base, evidenceId='foreign', sourceWorkId='other', quote='Foreign source words.')])
    def invoke(prompt):
        assert 'Essential late condition.' in prompt
        assert 'Foreign source words.' not in prompt
        return {'content': json.dumps([dict(original, evidenceRefs=['late'])])}
    result = repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'c',
        'missingEvidenceRefs': ['late', 'foreign']}]}, evidence, '', invoke, json.loads)
    assert result[0]['evidenceRefs'] == ['late']


def test_repair_stops_when_normal_budget_is_exhausted():
    def exhausted(_):
        raise BudgetExhaustedError('modelCalls', 15, 15)
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'bad', 'evidenceRefs': []}
    assert repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'c'}]}, [], '', exhausted, json.loads) == []


def test_repair_short_ids_restore_claim_and_cell_identity_without_mutating_input():
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'FPS 200', 'evidenceRefs': ['ev_full_identity']}
    evidence = [{'evidenceId': 'ev_full_identity', 'quote': 'FPS 200'}]
    def invoke(prompt):
        assert '"evidenceRefs": ["E1"]' in prompt
        assert '"value":"200"' in prompt
        return {'content': json.dumps([{**original, 'evidenceRefs': ['E1'], 'tableBindings': [
            {'evidenceId': 'E1', 'rowNumber': 1, 'groupIndex': 0, 'metric': 'FPS', 'value': '200'}]}])}
    revised = repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'c'}]}, evidence, '', invoke, json.loads)
    assert revised[0]['evidenceRefs'] == ['ev_full_identity']
    assert revised[0]['tableBindings'][0]['evidenceId'] == 'ev_full_identity'
    assert original == {'claimId': 'c', 'kind': 'reported', 'text': 'FPS 200', 'evidenceRefs': ['ev_full_identity']}
    assert evidence == [{'evidenceId': 'ev_full_identity', 'quote': 'FPS 200'}]


def test_repair_rejects_length_finish_even_if_partial_content_is_valid_json():
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'partial', 'evidenceRefs': []}
    def must_not_parse(_):
        raise AssertionError('truncated provider output must not be salvaged')
    assert repair_rejected({'claims': [original]}, {'rejected': [{'claimId': 'c'}]}, [], '',
        lambda p: {'content': json.dumps([original]), 'finishReason': 'length'}, must_not_parse) == []


def test_repair_normalizes_only_unambiguous_claim_text_alias_and_still_rechecks():
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'bad', 'evidenceRefs': ['e']}
    check = {'rejected': [{'claimId': 'c'}]}
    evidence = [{'evidenceId': 'e', 'quote': '200 FPS', 'verification': {'literal': 'passed'}}]
    response = {k: v for k, v in original.items() if k != 'text'}
    response['claim'] = '200 FPS'
    revised = repair_rejected({'claims': [original]}, check, evidence, '',
        lambda p: {'content': json.dumps([response])}, json.loads)
    assert revised[0]['text'] == '200 FPS' and 'claim' not in revised[0]
    assert not verify_claims(revised, evidence)['accepted']
    response['text'] = '999 FPS'
    assert repair_rejected({'claims': [original]}, check, evidence, '',
        lambda p: {'content': json.dumps([response])}, json.loads) == []


def test_selected_evidence_absence_is_still_subject_to_semantic_check():
    ev = {'evidenceId': 'e', 'quote': 'A limited passage.', 'verification': {'literal': 'passed'}}
    c = {'claimId': 'c', 'kind': 'inference', 'evidenceRefs': ['e'], 'text': '所选证据未提供硬件配置。'}
    assert not verify_claims([c], [ev])['accepted']
    assert verify_claims([c], [ev], lambda *_: [{'claimId': 'c', 'status': 'passed'}])['accepted']
    assert verify_claims([{**c, 'text': '论文未提供硬件配置。'}], [ev])['rejected'][0]['reason'] == 'absence_not_established'


def test_proposal_cannot_bypass_logical_verification():
    claim = {'claimId': 'p', 'kind': 'proposal', 'text': 'PSNR和LPIPS使用相同损失方向', 'evidenceRefs': []}
    result = verify_claims([claim], [], lambda c, e: [{'claimId': 'p', 'status': 'failed', 'reason': 'metric direction'}])
    assert not result['accepted'] and result['rejected'][0]['detail'] == 'metric direction'
    assert not verify_claims([claim], [])['accepted']


@pytest.mark.parametrize('exhausted,finish,expected', [(True, None, 'skipped_budget'),
    (False, 'stop', 'response_received'), (False, 'length', 'output_truncated')])
def test_repair_state_distinguishes_budget_skip_from_model_response(exhausted, finish, expected):
    from services.deep_research.graph import make_verify_node
    original = {'claimId': 'c', 'kind': 'reported', 'text': 'bad', 'evidenceRefs': []}
    record = {'state': {'reportBody': {'claims': [original]}, 'evidence': []}}
    def update(run, change, **kwargs):
        nonlocal record
        record = change(record)
        return record
    def invoke(*args, **kwargs):
        if exhausted:
            raise BudgetExhaustedError('modelCalls', 13, 14)
        return {'content': '[]', 'finishReason': finish}
    verify = lambda *args: {'accepted': [], 'rejected': [{'claimId': 'c', 'reason': 'unsupported'}]}
    make_verify_node(verify, None, update, llm_invoke=invoke)({'run_id': 'r'})
    assert record['state']['repairStatus'] == expected
    assert record['state']['verifiedReport']['verificationSummary'] == {'accepted': 0, 'rejected': 1}


def test_capacity_rejects_before_clock_starts_and_does_not_queue_executor(tmp_path):
    repo = DeepResearchRepository(str(tmp_path / 'runs.sqlite3'))
    repo.initialize()
    facade = ResearchFacade(repo, lambda **kw: None, llm_client=object(), max_concurrent=1)
    entered, release = threading.Event(), threading.Event()
    def execute(run):
        entered.set()
        assert release.wait(5)
    facade._execute_graph = execute
    for run in ('a', 'b'):
        repo.create_run({'runId': run, 'taskId': 't'})
    try:
        facade._start_execution('a')
        assert entered.wait(2)
        with pytest.raises(DeepResearchError) as error:
            facade._action_resume('b', repo.require_run('b')['runRevision'], {})
        assert error.value.code == 'execution_capacity'
        assert repo.require_run('b')['status'] == 'queued'
        assert not repo.require_run('b').get('startedAt')
        assert set(facade._active_futures) == {'a'}
        worker = facade._active_futures['a']
        release.set()
        worker.result(timeout=3)
        facade._action_resume('b', repo.require_run('b')['runRevision'], {})
        assert repo.require_run('b')['status'] == 'running'
    finally:
        release.set()
        facade.shutdown()


def test_elapsed_time_is_visible_for_failure_and_freezes_while_waiting():
    from services.deep_research.facade import _elapsed_seconds
    value = {'status': 'failed', 'startedAt': '2026-10-12T00:00:00Z',
             'finishedAt': '2026-10-12T00:01:04Z', 'budget': {'elapsedSeconds': 0}}
    assert _elapsed_seconds(value) == 64
    value.update(status='waiting_user', state={'waitingSince': '2026-10-12T00:00:12Z'})
    assert _elapsed_seconds(value) == 12


def test_late_repair_does_not_send_or_discard_verified_claims():
    from datetime import datetime, UTC, timedelta
    from services.deep_research.graph import make_verify_node
    from unittest.mock import Mock
    good = {'claimId': 'good', 'kind': 'proposal', 'text': 'Already checked.', 'evidenceRefs': []}
    bad = {'claimId': 'bad', 'kind': 'proposal', 'text': 'Needs repair.', 'evidenceRefs': []}
    record = {'startedAt': (datetime.now(UTC) - timedelta(seconds=300)).isoformat(),
              'budget': {'maxWallClockSeconds': 360},
              'state': {'reportBody': {'claims': [good, bad]}, 'evidence': []}}
    def update(run, change, **kwargs):
        nonlocal record
        record = change(record)
        return record
    invoke = Mock()
    verify = lambda *args: {'accepted': [good], 'rejected': [{'claimId': 'bad', 'reason': 'unsupported'}]}
    make_verify_node(verify, None, update, llm_invoke=invoke)({'run_id': 'r'})
    invoke.assert_not_called()
    assert record['state']['repairStatus'] == 'skipped_time'
    assert record['state']['verifiedReport']['verifiedClaims'] == [good]


def test_graph_passes_accepted_design_context_to_repair_and_independent_check():
    from services.deep_research.graph import make_verify_node
    from unittest.mock import Mock
    good = {'claimId': 'definition', 'kind': 'proposal', 'text': 'Loss is negative PSNR.', 'evidenceRefs': []}
    bad = {'claimId': 'decision', 'kind': 'proposal', 'text': 'Incorrect interval decision.', 'evidenceRefs': []}
    revised = {**bad, 'text': 'Reject zero only if the interval excludes zero.'}
    record = {'state': {'reportBody': {'claims': [good, bad]}, 'evidence': []}}
    def update(run, change, **kwargs):
        nonlocal record
        record = change(record)
        return record
    calls = []
    def verify(claims, evidence, semantic):
        calls.append(claims)
        if len(calls) == 1:
            return {'accepted': [good], 'rejected': [{'claimId': 'decision', 'reason': 'wrong decision'}]}
        semantic(claims, evidence)
        return {'accepted': claims, 'rejected': []}
    checker = Mock()
    def invoke(run, node, prompt, options):
        assert 'Loss is negative PSNR.' in prompt
        assert 'YOUR UNEXECUTED PROPOSAL' in prompt
        return {'content': json.dumps([revised])}
    make_verify_node(verify, checker, update, llm_invoke=invoke)({'run_id': 'r'})
    checker.check_revisions.assert_called_once_with([revised], [], [good])
    assert record['state']['verifiedReport']['verificationSummary'] == {'accepted': 2, 'rejected': 0}
