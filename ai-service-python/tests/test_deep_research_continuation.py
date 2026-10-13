import hashlib
import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from services.deep_research.continuation import reusable_local_source, rebind_inherited_state


def test_local_reuse_distinguishes_file_hash_from_exact_indexed_passage_hash():
    material = {'materialId': 'p', 'contentHash': 'file-hash', 'versionId': 'v1'}
    source = {'workId': 'p', 'versionId': 'v1', 'text': 'Exact passage',
              'contentHash': hashlib.sha256(b'Exact passage').hexdigest()}
    assert reusable_local_source(source, material, material)
    assert not reusable_local_source({**source, 'text': 'Altered passage'}, material, material)
    assert not reusable_local_source(source, {**material, 'contentHash': 'changed'}, material)
    assert not reusable_local_source(source, {**material, 'versionId': 'v2'}, material)
    assert not reusable_local_source(source, material, None)
    assert reusable_local_source({**source, 'materialContentHash': 'file-hash'}, material, material)
    assert not reusable_local_source({**source, 'materialContentHash': 'wrong'}, material, material)


def test_rebinding_does_not_treat_parent_relevance_as_a_new_verdict():
    state = {'sources': [{'sourceId': 's', 'workId': 'p', 'obligationIds': ['old']}],
        'evidence': [{'evidenceId': 'e', 'sourceWorkId': 'p', 'obligationIds': ['old'],
            'verification': {'literal': 'passed', 'semantic': 'passed'}}]}
    before = deepcopy(state)
    plan = [{'obligations': [{'obligationId': 'new', 'requiredSources': ['p']},
                            {'obligationId': 'other', 'requiredSources': ['q']}]}]
    result = rebind_inherited_state(state, plan)
    assert result['evidence'][0]['obligationIds'] == ['new']
    assert result['evidence'][0]['verification'] == {'literal': 'passed', 'semantic': 'unchecked'}
    assert state == before


@pytest.mark.parametrize('relevant', [True, False])
def test_compiled_child_graph_assesses_reuse_before_targeted_acquisition(tmp_path, relevant):
    from services.deep_research.repository import DeepResearchRepository
    from services.deep_research.graph import build_deep_research_graph
    from services.deep_research.coverage import validate_plan, coverage_gaps
    from services.deep_research.verification import make_evidence, verify_claims
    repo = DeepResearchRepository(tmp_path / 'child.sqlite3')
    repo.initialize()
    source = {'sourceId': 's', 'workId': 'p', 'versionId': 'v1', 'contentHash': 'h',
              'accessLevel': 'fulltext', 'text': 'We report 30 FPS.', 'obligationIds': ['old']}
    evidence = make_evidence(source, source['text'], source['text'], location={'page': 1}, obligation_ids=['old'])
    evidence['sourceId'] = 's'
    record, _ = repo.create_run({'taskId': 'task', 'idempotencyKey': 'child', 'question': 'Explain speed conditions',
        'materials': [{'materialId': 'p', 'pdfId': 'p'}], 'parentRunId': 'parent',
        'state': {'sources': [source], 'inheritedSources': [source], 'evidence': [evidence], 'inheritedEvidence': [evidence]}})
    started = repo.begin_execution(record['runId'])
    nodes = []
    def invoke(_, node, prompt, *args, **kwargs):
        nodes.append(node)
        if node == 'resolve_brief':
            data = {'outputKind': 'claim_verification', 'clarification': ''}
        elif node == 'plan':
            data = [{'itemId': 'i', 'question': 'New question', 'obligations': [
                {'obligationId': 'new', 'question': 'Speed conditions', 'requiredSources': ['p']}], 'dependencies': []}]
        elif node == 'assess_relevance':
            assert '"obligationId": "new"' in prompt
            data = [{'evidenceId': evidence['evidenceId'], 'obligationId': 'new', 'relevant': relevant}]
        elif node == 'synthesize':
            data = {'sections': [{'title': '判断', 'claimIds': ['c']}], 'claims': [
                {'claimId': 'c', 'kind': 'reported', 'text': '报告30 FPS', 'evidenceRefs': ['E1'], 'conditions': {}}]}
        else:
            data = []
        return {'content': json.dumps(data)}
    retrieve = Mock(return_value=[])
    read = Mock(return_value={'pages': []})
    graph = build_deep_research_graph(llm_invoke=invoke, retrieve_fn=retrieve, read_fn=read,
        scope_validator=lambda *_: True, make_evidence_fn=make_evidence, coverage_gaps_fn=coverage_gaps,
        verify_claims_fn=verify_claims, semantic_check_fn=lambda *_: [{'claimId': 'c', 'status': 'passed'}],
        repo_update=repo.update_run, repo_publish=repo.publish_report, validate_plan_fn=validate_plan)
    graph.invoke({'run_id': record['runId'], 'execution_epoch': started['executionEpoch']})
    assert nodes.index('assess_relevance') < nodes.index('synthesize')
    if relevant:
        retrieve.assert_not_called()
        read.assert_not_called()
    else:
        assert retrieve.call_count > 0
        assert all('Speed conditions' in call.args[0] for call in retrieve.call_args_list)
    final = repo.require_run(record['runId'])
    assert final['status'] == 'completed'
    assert final['state']['evidence'][0]['obligationIds'] == ['new']
