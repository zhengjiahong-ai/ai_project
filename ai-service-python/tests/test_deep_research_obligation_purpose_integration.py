import json
from copy import deepcopy
from unittest.mock import Mock

from services.deep_research.final_coverage import audit_final_answer, remaining_retrieval_gaps
from services.deep_research.graph import make_publish_node
from services.deep_research.reporting import render_report

QUESTION = '设计一个尚未执行的四组实验，不要求复述论文全部历史指标。'
PLAN = [{'itemId': 'p', 'question': '设计实验', 'obligations': [{'obligationId': 'support',
    'question': '论文历史主表报告了哪些指标？', 'purpose': 'supporting_research', 'requestExcerpt': QUESTION}]}]
CLAIMS = [{'claimId': 'c', 'kind': 'reported', 'text': '所读原文给出了可用于定义干预的剪枝机制。',
           'verification': 'semantic_passed', 'evidenceRefs': ['e']}]
EVIDENCE = [{'evidenceId': 'e', 'sourceWorkId': 'paper', 'quote': CLAIMS[0]['text'],
             'verification': {'literal': 'passed'}}]
GAPS = [{'obligationId': 'support', 'sourceWorkId': 'paper', 'question': PLAN[0]['obligations'][0]['question']}]


def verdicts():
    binding = [{'claimId': 'c', 'excerpt': CLAIMS[0]['text']}]
    return [{'obligationId': 'support', 'status': 'not_required',
             'reason': '当前交付是拟议实验，所读机制已足以定义干预，无需复述历史主表。',
             'requestExcerpt': QUESTION, 'bindings': binding},
            {'obligationId': 'answer_scope', 'status': 'covered', 'bindings': binding,
             'aspects': [{'aspectId': 'scope', 'requirement': '原始交付要求', 'status': 'covered',
                         'basis': {'kind': 'request', 'excerpt': QUESTION}, 'bindings': binding}]}]


def audit(rows=None, plan=None):
    return audit_final_answer('r', QUESTION, PLAN if plan is None else plan, CLAIMS, EVIDENCE,
        Mock(return_value={'content': json.dumps(verdicts() if rows is None else rows)}), json.loads)


def test_auxiliary_question_is_not_falsely_marked_answered_and_history_survives():
    before = deepcopy(GAPS)
    result = audit()
    assert result['status'] == 'checked' and not result['gaps']
    assert result['verdicts'][0]['status'] == 'not_required'
    assert [x['obligationId'] for x in result['nonblockingResearch']] == ['support']
    assert remaining_retrieval_gaps(GAPS, result, CLAIMS, EVIDENCE, plan=PLAN, question=QUESTION) == []
    assert GAPS == before
    # Legacy callers cannot silently waive source-specific research gaps.
    assert remaining_retrieval_gaps(GAPS, result, CLAIMS, EVIDENCE) == GAPS


def test_original_question_gap_keeps_auxiliary_gap_blocking():
    rows = verdicts()
    rows[1]['status'] = 'partial'
    result = audit(rows)
    assert not result['nonblockingResearch']
    assert {x['obligationId'] for x in result['gaps']} == {'support', 'answer_scope'}
    assert remaining_retrieval_gaps(GAPS, result, CLAIMS, EVIDENCE, plan=PLAN, question=QUESTION) == GAPS


def test_user_requirement_or_bad_grounding_cannot_be_waived():
    for change in [{'purpose': 'answer_requirement'}, {'requestExcerpt': 'invented user request'}]:
        plan = deepcopy(PLAN)
        plan[0]['obligations'][0].update(change)
        result = audit(plan=plan)
        assert not result['nonblockingResearch']
        assert result['gaps'][0]['obligationId'] == 'support'


def test_missing_aspect_validation_prevents_optional_exemption():
    rows = verdicts()
    del rows[1]['aspects']
    result = audit(rows)
    assert result['status'] == 'invalid_response'
    assert not result['nonblockingResearch']


def test_stored_exemption_does_not_survive_changed_final_answer():
    result = audit()
    changed = [{**CLAIMS[0], 'text': 'The accepted final answer has changed completely.'}]
    assert remaining_retrieval_gaps(GAPS, result, changed, EVIDENCE, plan=PLAN, question=QUESTION) == GAPS


def test_publication_retains_research_notes_in_collapsed_area():
    result = audit()
    record = {'question': QUESTION, 'state': {'plan': deepcopy(PLAN), 'gaps': deepcopy(GAPS),
        'evidence': EVIDENCE, 'outputKind': 'claim_verification', 'verifiedReport': {
            'verifiedClaims': CLAIMS, 'rejectedClaims': [], 'answerCoverage': result}}}
    def update(_run, mutate, **kwargs):
        nonlocal record
        record = mutate(record)
        return record
    save = Mock(return_value=({'publicationId': 'pub'}, True))
    output = make_publish_node(save, update)({'run_id': 'r'})
    assert output['outcome'] == 'complete'
    payload = save.call_args.kwargs['payload']
    assert not payload['gaps'] and payload['researchNotes']
    assert record['state']['gaps'] == GAPS
    text = render_report(payload)
    assert '<summary>查证范围说明</summary>' in text
    assert PLAN[0]['obligations'][0]['question'] in text
    assert verdicts()[0]['reason'] not in text
