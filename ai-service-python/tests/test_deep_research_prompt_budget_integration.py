"""Full request limits and evidence permissions across actual send sites."""
import json
from unittest.mock import Mock

from services.deep_research.final_coverage import audit_final_answer
from services.deep_research.graph import make_synthesize_node
from services.deep_research.repair import repair_rejected
from services.deep_research.tools import BudgetedSemanticChecker


def test_truncated_synthesis_never_saves_even_a_valid_json_prefix():
    from types import SimpleNamespace
    record = {'question': 'Explain', 'state': {'evidence': []}}
    content = json.dumps({'claims': [{'claimId': 'c', 'text': 'Incomplete result'}], 'sections': []})
    for response in ({'content': content, 'finishReason': 'length'},
                     {'content': content, 'finish_reason': 'length'},
                     SimpleNamespace(content=content, finish_reason='length')):
        invoke, update = Mock(return_value=response), Mock(return_value=record)
        result = make_synthesize_node(invoke, update)({'run_id': 'r'})
        assert result == {'error_code': 'invalid_synthesis_response'}
        assert update.call_count == 1  # Only the initial stage transition, no report body.
        invoke.assert_called_once()


def test_synthesis_compacts_routing_without_changing_quotes_or_source_scope():
    from copy import deepcopy
    record = {'question': 'Explain', 'materials': [{'materialId': 'paper-a', 'title': 'Same title'},
              {'materialId': 'paper-b', 'title': 'Same title'}], 'state': {
        'plan': [{'obligations': [{'obligationId': 'o', 'question': 'Compare',
            'purpose': 'answer_requirement', 'requestExcerpt': 'Explain',
            'requiredSources': ['paper-a', 'paper-b'], 'searchQuery': 'SEARCH_ONLY_PAYLOAD'}]}],
        'evidence': [{'evidenceId': f'e{i}', 'sourceWorkId': paper,
            'quote': f'Literal quote {i}', 'conditions': {'scope': f'condition-{i}'},
            'location': {'chunk': 123, 'pageResolution': 'resolved', 'section': 'Methods', 'page': 7},
            'obligationIds': ['o']} for i, paper in enumerate(['paper-a', 'paper-b'])]}}
    before = deepcopy(record)
    invoke = Mock(return_value={'content': '{}'})
    make_synthesize_node(invoke, lambda *a, **k: record)({'run_id': 'r'})
    prompt = invoke.call_args.args[2]
    registry = json.loads(prompt.split('Source registry (P keys identify papers, not evidenceRefs): ')[1].split('\n', 1)[0])
    rows = json.loads(prompt.split('Evidence summaries:\n')[1].split('\n\nReturn ONLY')[0])
    assert [registry[row['source']]['workId'] for row in rows] == ['paper-a', 'paper-b']
    assert [row['quote'] for row in rows] == ['Literal quote 0', 'Literal quote 1']
    assert all(registry[row['source']]['title'] == 'Same title' for row in rows)
    assert [row['conditions']['scope'] for row in rows] == ['condition-0', 'condition-1']
    assert all(row['location'] == {'section': 'Methods', 'page': 7} for row in rows)
    assert 'SEARCH_ONLY_PAYLOAD' not in prompt
    assert 'answer_requirement' in prompt and 'requiredSources' in prompt
    assert record == before


def test_experiment_synthesis_counts_instructions_and_keeps_whole_quotes():
    evidence = [{'evidenceId': f'e{i}', 'quote': '完整引文' * 350,
                 'sourceWorkId': f'p{i % 2}', 'sourceVersionId': 'v',
                 'obligationIds': ['o']} for i in range(12)]
    record = {'question': '设计可执行的实验', 'state': {'outputKind': 'experiment_design',
              'metricDomains': ['quality'], 'evidence': evidence}}
    invoke = Mock(return_value={'content': '{}'})
    result = make_synthesize_node(invoke, lambda *a, **k: record)({'run_id': 'r'})
    prompt = invoke.call_args.args[2]
    assert len(prompt.encode('utf-8')) <= 24000
    assert 'Statistical reference' in prompt and 'designRole' in prompt
    rows = json.loads(prompt.split('Evidence summaries:\n')[1].split('\n\nReturn ONLY')[0])
    assert 0 < len(rows) < len(evidence)
    assert all(row['quote'] == evidence[0]['quote'] for row in rows)
    assert result['error_code'] == 'invalid_synthesis_response'


def test_repair_cannot_cite_row_removed_from_complete_request():
    claim = {'claimId': 'c', 'kind': 'reported', 'text': '待修订',
             'evidenceRefs': ['huge', 'small']}
    evidence = [{'evidenceId': 'huge', 'quote': '原文' * 15000},
                {'evidenceId': 'small', 'quote': '完整短引文'}]
    def invoke(prompt):
        assert len(prompt.encode('utf-8')) <= 24000
        assert '\"c\": [\"E2\"]' in prompt
        return {'content': json.dumps([{**claim, 'evidenceRefs': ['E1']}])}
    result = repair_rejected({'claims': [claim]}, {'rejected': [{'claimId': 'c'}]},
                             evidence, '核查', invoke, json.loads)
    assert result == []


def test_semantic_pass_cannot_hide_evidence_omitted_for_capacity():
    def invoke(**kwargs):
        assert len(kwargs['prompt'].encode('utf-8')) <= 24000
        return {'content': json.dumps([{'claimId': 'c', 'status': 'passed'}])}
    result = BudgetedSemanticChecker(invoke, 'r')(
        [{'claimId': 'c', 'kind': 'reported', 'text': '事实', 'evidenceRefs': ['e']}],
        [{'evidenceId': 'e', 'quote': '证据' * 15000}])
    assert result[0]['status'] == 'failed'


def test_final_audit_cannot_bind_to_omitted_source_excerpt():
    claim = {'claimId': 'c', 'kind': 'reported', 'text': '最终回答中的可核对完整句子', 'evidenceRefs': ['e']}
    binding = [{'claimId': 'c', 'excerpt': claim['text']}]
    def invoke(*args, **kwargs):
        assert len(args[2].encode('utf-8')) <= 24000
        return {'content': json.dumps([{'obligationId': 'o', 'status': 'covered',
            'bindings': binding, 'aspects': [{'aspectId': 'a', 'requirement': '必要条件',
            'status': 'covered', 'basis': {'kind': 'source', 'evidenceId': 'e',
            'excerpt': '不可展示的完整原文片段'}, 'bindings': binding}]}])}
    result = audit_final_answer('r', '', [{'obligations': [{'obligationId': 'o', 'question': '必要条件'}]}],
        [claim], [{'evidenceId': 'e', 'quote': '不可展示的完整原文片段' * 3000}], invoke, json.loads)
    assert result['status'] == 'invalid_response'
    assert result['gaps']
