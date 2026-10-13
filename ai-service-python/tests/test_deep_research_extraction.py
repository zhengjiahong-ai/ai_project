import json
from unittest.mock import Mock

import pytest

from services.deep_research.extraction import make_batched_extract_node
from services.deep_research.repository import DeepResearchRepository
from services.deep_research.verification import make_evidence
from services.deep_research.tools import BudgetedSemanticChecker


def setup(tmp_path):
    repo = DeepResearchRepository(str(tmp_path / 'r.sqlite3'))
    repo.initialize()
    reads = [{'sourceId': f's{i}', 'workId': f'p{i}', 'versionId': f'v{i}', 'contentHash': f'h{i}',
              'accessLevel': 'fulltext', 'location': {'page': i + 2}, 'obligationIds': ['o'],
              'pages': [{'text': f'Method {i} reports a complete result under the fixed evaluation condition.'}]}
             for i in range(3)]
    repo.create_run({'runId': 'r', 'taskId': 't', 'state': {'readResults': reads,
        'plan': [{'itemId': 'p', 'question': 'Compare', 'obligations': [{'obligationId': 'o', 'question': 'fixed evaluation'}]}]}})
    repo.begin_execution('r')
    return repo, reads


def test_batch_saves_calls_without_mixing_paper_locations_or_hashes(tmp_path):
    repo, reads = setup(tmp_path)
    invoke = Mock(return_value={'content': json.dumps([{'sourceId': r['sourceId'], 'quote': r['pages'][0]['text'],
        'obligationIds': ['o'], 'conditions': {'setting': 'fixed'}} for r in reads])})
    result = make_batched_extract_node(invoke, make_evidence, lambda *args: True, repo.update_run)({'run_id': 'r'})
    assert invoke.call_count == 1 and len(result['evidence_ids']) == 3
    evidence = repo.require_run('r')['state']['evidence']
    assert {(e['sourceWorkId'], e['location']['page'], e['contentHash']) for e in evidence} == {
        ('p0', 2, 'h0'), ('p1', 3, 'h1'), ('p2', 4, 'h2')}
    # An incremental pass reuses exact source+version evidence, while reassessing its goal separately.
    make_batched_extract_node(invoke, make_evidence, lambda *args: True, repo.update_run)({'run_id': 'r'})
    assert invoke.call_count == 1


def test_batch_stores_original_span_after_whitespace_only_recovery(tmp_path):
    repo, reads = setup(tmp_path)
    original = reads[0]['pages'][0]['text'].replace('complete result', 'complete\nresult')
    reads[0]['pages'][0]['text'] = original
    repo.update_run('r', lambda r: {**r, 'state': {**r['state'], 'readResults': [reads[0]]}})
    invoke = Mock(return_value={'content': json.dumps([{'sourceId': 's0',
        'quote': original.replace('\n', ' '), 'obligationIds': ['o'], 'conditions': {}}])})
    make_batched_extract_node(invoke, make_evidence, lambda *a: True, repo.update_run)({'run_id': 'r'})
    saved = repo.require_run('r')['state']['evidence']
    assert len(saved) == 1
    assert saved[0]['quote'] == original
    assert saved[0]['sourceContext'] == original
    assert saved[0]['sourceWorkId'] == 'p0' and saved[0]['location']['page'] == 2


def test_extraction_carries_only_parser_cells_in_the_selected_quote(tmp_path):
    repo, reads = setup(tmp_path)
    data = {'groups': [['Room', ['FPS', 'Mem']]],
            'rows': [[1, 'Baseline', ['30', '400MB']], [2, 'Ours*', ['60', '100MB']]]}
    quoted = 'Table row 2: Ours* | 60 | 100MB'
    text = 'Room benchmark.\nTable row 1: Baseline | 30 | 400MB\n' + quoted
    reads[0].update(tableData=data, pages=[{'text': text}])
    repo.update_run('r', lambda r: {**r, 'state': {**r['state'], 'readResults': [reads[0]]}})
    invoke = Mock(return_value={'content': json.dumps([{'sourceId': 's0', 'quote': quoted,
                                                       'obligationIds': ['o'], 'conditions': {}}])})
    make_batched_extract_node(invoke, make_evidence, lambda *args: True, repo.update_run)({'run_id': 'r'})
    saved = repo.require_run('r')['state']['evidence']
    ev = next(e for e in saved if e['quote'] == quoted)
    assert len(saved) == 2
    assert ev['tableData'] == {'groups': data['groups'], 'rows': [data['rows'][1]]}
    prompt_rows = json.loads(invoke.call_args.args[2].split('Passages:\n')[1])
    assert prompt_rows[0]['tableData'] == data


def test_foreign_identity_wrong_quote_and_revoked_passage_never_become_evidence(tmp_path):
    repo, reads = setup(tmp_path)
    invoke = Mock(return_value={'content': json.dumps([
        {'sourceId': 's0', 'quote': reads[1]['pages'][0]['text'], 'obligationIds': ['o']},
        {'sourceId': 's1', 'quote': reads[1]['pages'][0]['text'], 'obligationIds': ['o']},
        {'sourceId': 'foreign', 'quote': reads[0]['pages'][0]['text'], 'obligationIds': ['o']},
    ])})
    make_batched_extract_node(invoke, make_evidence, lambda _, pid: pid != 'p1', repo.update_run)({'run_id': 'r'})
    assert not repo.require_run('r')['state']['evidence']
    assert 's1' not in {p['sourceId'] for p in json.loads(invoke.call_args.args[2].split('Passages:\n')[1])}


def test_verified_row_after_long_caption_survives_model_budget_exhaustion(tmp_path):
    from services.deep_research.contracts import BudgetExhaustedError
    repo, reads = setup(tmp_path)
    quote = 'Table row 8: Ours-30K | 134 | 734MB'
    reads[0].update(tableData={'groups': [['Dataset', ['FPS', 'Mem']]],
                              'rows': [[8, 'Ours-30K', ['134', '734MB']]]},
                    pages=[{'text': 'Caption context. ' * 240 + '\n' + quote}])
    repo.update_run('r', lambda r: {**r, 'state': {**r['state'], 'readResults': [reads[0]]}})
    invoke = Mock(side_effect=BudgetExhaustedError('modelCalls', 13, 13))
    with pytest.raises(BudgetExhaustedError):
        make_batched_extract_node(invoke, make_evidence, lambda *a: True, repo.update_run)({'run_id': 'r'})
    saved = repo.require_run('r')['state']['evidence']
    assert len(saved) == 1 and saved[0]['quote'] == quote
    assert saved[0]['tableData']['rows'][0][1] == 'Ours-30K'
    assert saved[0]['verification']['semantic'] == 'unchecked'
    # Resume does not duplicate the exact row or spend a second transcription call.
    make_batched_extract_node(invoke, make_evidence, lambda *a: True, repo.update_run)({'run_id': 'r'})
    assert len(repo.require_run('r')['state']['evidence']) == 1
    assert invoke.call_count == 1


def test_unverified_or_revoked_rows_are_not_promoted_by_deterministic_extraction(tmp_path):
    repo, reads = setup(tmp_path)
    quote = 'Table row 8: Ours-30K | 134 | 734MB'
    for index, source in enumerate(reads):
        source.update(tableData={'groups': [['Dataset', ['FPS', 'Mem']]],
                                 'rows': [[8, 'Ours-30K', ['134', '734MB']]]},
                      pages=[{'text': 'Long enough surrounding evaluation context.\n' + quote}])
    reads[0]['tableData'] = None
    reads[1]['tableData']['rows'][0][2][1] = '999MB'
    repo.update_run('r', lambda r: {**r, 'state': {**r['state'], 'readResults': reads}})
    invoke = Mock(return_value={'content': '[]'})
    make_batched_extract_node(invoke, make_evidence, lambda _, pid: pid != 'p2', repo.update_run)({'run_id': 'r'})
    assert repo.require_run('r')['state']['evidence'] == []


def test_semantic_check_accepts_fenced_json_but_not_prose():
    invoke = Mock(return_value={'content': '```json\n[{"claimId":"c","status":"passed","reason":"literal supports"}]\n```'})
    checker = BudgetedSemanticChecker(invoke, 'r')
    assert checker([{'claimId': 'c', 'evidenceRefs': []}], [])[0]['status'] == 'passed'
    invoke.return_value = {'content': 'looks correct'}
    from services.deep_research.contracts import DeepResearchError
    with pytest.raises(DeepResearchError) as error:
        checker([{'claimId': 'c', 'evidenceRefs': []}], [])
    assert error.value.code == 'invalid_verification_response'


@pytest.mark.parametrize('response', [
    {'content': '', 'finishReason': 'length'},
    {'content': '[]'},
    {'content': '[{"claimId":"other","status":"passed"}]'},
    {'content': '[{"claimId":"c","status":"unknown"}]'},
    {'content': '[{"claimId":"c","status":"passed"}]', 'finishReason': 'length'},
])
def test_incomplete_verifier_is_failure_not_insufficient_evidence(response):
    from services.deep_research.contracts import DeepResearchError
    invoke = Mock(return_value=response)
    with pytest.raises(DeepResearchError) as error:
        BudgetedSemanticChecker(invoke, 'r')([{'claimId': 'c', 'evidenceRefs': []}], [])
    assert error.value.code == 'invalid_verification_response'
    assert invoke.call_count == 1


def test_new_snapshot_inherits_only_unchanged_authorized_source_versions(tmp_path):
    from services.deep_research.facade import ResearchFacade
    from services.deep_research.contracts import DeepResearchError
    repo, _ = setup(tmp_path)
    sources = [{'sourceId': 'old-a', 'workId': 'a', 'contentHash': 'ha'},
               {'sourceId': 'old-b', 'workId': 'b', 'contentHash': 'hb'},
               {'sourceId': 'public', 'workId': 'arxiv:1', 'sourceKind': 'arxiv', 'contentHash': 'hp'}]
    repo.create_run({'runId': 'parent', 'taskId': 't', 'status': 'completed', 'state': {'sources': sources,
        'evidence': [{'evidenceId': s['sourceId'], 'sourceId': s['sourceId']} for s in sources]}})
    facade = ResearchFacade(repo, lambda **kwargs: None, llm_client=Mock())
    request = {'workspaceTaskId': 't', 'operationKey': 'new-snapshot', 'parentRunId': 'parent',
               'question': 'compare updated task', 'materials': [{'materialId': 'a', 'contentHash': 'ha'},
                                                               {'materialId': 'b', 'contentHash': 'changed'}]}
    child, _ = facade.create(request, start_async=False)
    assert [s['sourceId'] for s in child['state']['sources']] == ['old-a']
    assert [e['sourceId'] for e in child['state']['evidence']] == ['old-a']
    refreshed, _ = facade.create({**request, 'operationKey': 'refresh', 'question': '最新文献',
                                  'sourcePolicy': {'mode': 'academic_external'}}, start_async=False)
    assert 'public' not in {s['sourceId'] for s in refreshed['state']['sources']}
    with pytest.raises(DeepResearchError, match='本任务'):
        facade.create({**request, 'workspaceTaskId': 'other', 'operationKey': 'foreign'}, start_async=False)
    facade.shutdown()


def test_small_answer_shares_call_but_preserves_each_claims_evidence_scope():
    prompts = []
    def invoke(**kwargs):
        prompt = kwargs['prompt']
        prompts.append(prompt)
        claims = json.loads(prompt.split('Claims:\n', 1)[1].split('\n\nEvidence:', 1)[0])
        assert kwargs['use_reserve'] is True
        return {'content': json.dumps([{'claimId': c['claimId'], 'status': 'passed'} for c in claims])}
    claims = [{'claimId': f'c{i}', 'text': f'Claim {i}', 'evidenceRefs': [f'e{i}']} for i in range(3)]
    evidence = [{'evidenceId': f'e{i}', 'quote': f'UNIQUE_SOURCE_{i}'} for i in range(4)]
    result = BudgetedSemanticChecker(invoke, 'r')(claims, evidence)
    assert len(result) == 3 and len(prompts) == 1
    prompt = prompts[0]
    supplied = json.loads(prompt.split('Claims:\n', 1)[1].split('\n\nEvidence:', 1)[0])
    wire_evidence = json.loads(prompt.split('Evidence:\n', 1)[1].split('\n\nReturn JSON', 1)[0])
    assert all(len(c['evidenceRefs']) == 1 for c in supplied)
    refs = [c['evidenceRefs'][0] for c in supplied]
    assert len(set(refs)) == 3
    assert [wire_evidence[ref]['quote'] for ref in refs] == [f'UNIQUE_SOURCE_{i}' for i in range(3)]
    assert 'For each claim use ONLY its own evidenceRefs' in prompt
    assert all(f'UNIQUE_SOURCE_{i}' in prompt for i in range(3))
    assert 'UNIQUE_SOURCE_3' not in prompt


def test_large_report_has_at_most_three_verification_batches():
    batches = []
    def invoke(**kwargs):
        claims = json.loads(kwargs['prompt'].split('Claims:\n', 1)[1].split('\n\nEvidence:', 1)[0])
        batches.append(claims)
        return {'content': json.dumps([{'claimId': c['claimId'], 'status': 'passed'} for c in claims])}
    claims = [{'claimId': f'c{i}', 'text': f'Claim {i}', 'evidenceRefs': []} for i in range(12)]
    result = BudgetedSemanticChecker(invoke, 'r')(claims, [])
    assert len(batches) == 3
    assert [v['claimId'] for v in result] == [c['claimId'] for c in claims]


def test_short_answer_and_revision_leave_room_for_both_coverage_audits():
    from services.deep_research.final_coverage import audit_final_answer
    reserved = ['synthesize']
    def invoke(*args, **kwargs):
        node = args[1] if args else kwargs['node']
        assert kwargs['use_reserve']
        reserved.append(node)
        assert len(reserved) <= 5, 'standard reserve must cover the complete short-answer lifecycle'
        if node == 'verify_answer_coverage':
            return {'content': '[]'}
        return {'content': json.dumps([{'claimId': c['claimId'], 'status': 'passed'} for c in claims])}
    claims = [{'claimId': f'c{i}', 'text': 'A supported short statement', 'kind': 'reported',
               'evidenceRefs': []} for i in range(2)]
    checker = BudgetedSemanticChecker(invoke, 'r')
    assert len(checker(claims, [])) == 2
    plan = [{'obligations': [{'obligationId': 'o', 'question': 'Explain the mechanism'}]}]
    audit_final_answer('r', 'Explain', plan, claims, [], invoke, json.loads)
    assert len(checker.check_revisions(claims, [], [])) == 2
    audit_final_answer('r', 'Explain', plan, claims, [], invoke, json.loads)
    assert reserved == ['synthesize', 'verify', 'verify_answer_coverage',
                        'verify_repair', 'verify_answer_coverage']


def test_verifier_receives_literal_context_and_source_scope():
    invoke = Mock(return_value={'content': '[{"claimId":"c","status":"passed"}]'})
    evidence = [{'evidenceId': 'e', 'quote': 'Size falls to 7 MB.',
                 'sourceContext': 'Synthetic dataset, supplementary results. Size falls to 7 MB.',
                 'sourceTitle': 'Example paper', 'location': {'section': 'Supplement'}}]
    BudgetedSemanticChecker(invoke, 'r')([{'claimId': 'c', 'evidenceRefs': ['e']}], evidence)
    prompt = invoke.call_args.kwargs['prompt']
    supplied = json.loads(prompt.split('Claims:\n', 1)[1].split('\n\nEvidence:', 1)[0])
    assert len(supplied[0]['evidenceRefs']) == 1
    received = json.loads(prompt.split('Evidence:\n', 1)[1].split('\n\nReturn JSON', 1)[0])[supplied[0]['evidenceRefs'][0]]
    assert received['sourceContext']['before'] == 'Synthetic dataset, supplementary results. '
    assert received['sourceContext']['after'] == ''
    assert received['location'] == {'section': 'Supplement'}
    assert received['quote'] == 'Size falls to 7 MB.'


def test_prompt_sampling_covers_other_papers_and_obligations_before_repeats():
    from services.deep_research.selection import balanced_sample
    items = [{'paper': 'a', 'obligation': 'quality', 'i': i} for i in range(25)] + [
        {'paper': 'b', 'obligation': 'quality', 'i': 1},
        {'paper': 'b', 'obligation': 'speed', 'i': 2}]
    selected = balanced_sample(items, lambda item: (item['paper'], item['obligation']), 3)
    assert [(i['paper'], i['obligation']) for i in selected] == [
        ('a', 'quality'), ('b', 'quality'), ('b', 'speed')]
    assert len(items) == 27
    assert balanced_sample([], lambda item: item, 10) == []


def test_comparison_sampling_keeps_each_papers_own_verified_rows_before_baselines():
    from copy import deepcopy
    from services.deep_research.selection import comparison_evidence_order, balanced_sample
    def row(work, method):
        return {'sourceWorkId': work, 'obligationIds': ['metrics'],
                'quote': f'Table row 1: {method} | 30',
                'tableData': {'groups': [['Dataset', ['FPS']]], 'rows': [[1, method, ['30']]]}}
    candidates = [row('a', f'Baseline{i}') for i in range(25)] + [row('b', 'Other'), row('a', 'Ours-30K'), row('b', 'ExampleNet*')]
    original = deepcopy(candidates)
    ordered = comparison_evidence_order(candidates, {'a': 'Some paper', 'b': 'ExampleNet: Efficient rendering'})
    chosen = balanced_sample(ordered, lambda e: (e['sourceWorkId'], tuple(e['obligationIds'])), 2)
    assert [e['tableData']['rows'][0][1] for e in chosen] == ['Ours-30K', 'ExampleNet*']
    assert candidates == original and len(ordered) == len(candidates)
    unverified = row('a', 'Ours-30K')
    unverified['quote'] = 'Only a table caption is visible.'
    prose = {'sourceWorkId': 'b', 'quote': 'Actual measured setting.'}
    assert comparison_evidence_order([prose, unverified], {})[0] is prose


def test_context_windows_and_utf8_packing_keep_complete_quotes():
    from services.deep_research.selection import surrounding_context, bounded_evidence_rows, balanced_sample
    quote = 'Result: 30 FPS.'
    context = surrounding_context({'quote': quote, 'sourceContext': '前' * 3000 + quote + '后' * 3000})
    assert context == {'before': '前' * 1000, 'after': '后' * 1000, 'truncated': True}
    rows = [{'source': p, 'quote': quote, 'sourceContext': context} for p in ['A'] * 15 + ['B'] * 15]
    selected = bounded_evidence_rows(balanced_sample(rows, lambda e: e['source'], 20))
    assert {e['source'] for e in selected} == {'A', 'B'}
    assert len(json.dumps(selected, ensure_ascii=False).encode('utf-8')) <= 14000
    assert all(e['quote'] == quote for e in selected)
    assert bounded_evidence_rows([{'quote': '字' * 6000}]) == []


def test_read_balances_papers_before_legacy_source_prefix_and_prefers_new_passages(tmp_path):
    from services.deep_research.graph import make_read_node
    from services.deep_research.repository import DeepResearchRepository
    repo = DeepResearchRepository(str(tmp_path / 'reads.sqlite3'))
    repo.initialize()
    sources = [{'sourceId': f'a{i}', 'workId': 'A', 'contentHash': 'ha', 'text': 'old passage',
                'obligationIds': ['o']} for i in range(25)] + [
        {'sourceId': f'b{i}', 'workId': 'B', 'contentHash': 'hb', 'text': 'new passage',
         'obligationIds': ['o']} for i in range(8)]
    repo.create_run({'runId': 'read', 'taskId': 't', 'state': {'sources': sources,
        'evidence': [{'sourceId': s['sourceId'], 'contentHash': 'ha'} for s in sources[:25]]}})
    repo.begin_execution('read')
    read = Mock(side_effect=lambda rid, sid: {'pages': [{'page': 1, 'text': sid}]})
    make_read_node(read, lambda *a: True, repo.update_run)({'run_id': 'read', 'source_ids': [s['sourceId'] for s in sources]})
    chosen = [s['workId'] for s in repo.require_run('read')['state']['readResults']]
    assert chosen.count('A') == chosen.count('B') == 6
    assert read.call_count == 12


def test_prompt_packing_preserves_other_quotes_before_long_context():
    from services.deep_research.selection import bounded_evidence_rows
    from copy import deepcopy
    rows = [{'evidenceId': str(i), 'quote': f'Complete quote {i}.',
             'sourceContext': {'before': 'x' * 1000, 'after': ''}} for i in range(2)]
    original = deepcopy(rows)
    packed = bounded_evidence_rows(rows, max_bytes=400)
    assert [r['quote'] for r in packed] == [r['quote'] for r in rows]
    assert all(r['contextOmitted'] and r['sourceContext'] == {} for r in packed)
    assert len(json.dumps(packed, ensure_ascii=False).encode('utf-8')) <= 400
    assert rows == original
