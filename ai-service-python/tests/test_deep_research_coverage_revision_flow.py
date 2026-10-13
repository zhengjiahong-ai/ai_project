import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from services.deep_research.final_coverage import remaining_retrieval_gaps
from services.deep_research.graph import make_verify_node, make_publish_node
from services.deep_research.verification import verify_claims
from services.deep_research.coverage_repair import prepare_coverage_repair

SHORT = '相机标定使用相机内参。'
FULL = '相机标定同时使用焦距和主点，并固定评测图像划分。'
EVIDENCE = [{'evidenceId': 'e', 'sourceWorkId': 'paper', 'accessLevel': 'fulltext',
             'quote': 'Camera calibration uses focal length and principal point, with a fixed evaluation split.',
             'verification': {'literal': 'passed'}}]


def test_unmapped_original_question_still_targets_existing_claims_and_ignores_malformed_bindings():
    claim = {'claimId': 'c', 'id': 'unrelated-alias', 'text': SHORT}
    audit = {'gaps': [{'obligationId': 'whole', 'question': '其他必要条件？', 'wholeQuestion': True}],
             'verdicts': [None, {'obligationId': ['bad']}, {'obligationId': 'whole', 'bindings': [None, {'claimId': []}]}]}
    result = prepare_coverage_repair({'claims': [claim]}, {'accepted': [claim], 'rejected': []}, audit)
    assert result['accepted'] == []
    assert result['rejected'] == [{'claimId': 'c', 'reason': 'answer_incomplete', 'missingQuestions': ['其他必要条件？']}]


def test_missing_requirement_is_routed_to_its_rejected_draft_instead_of_unrelated_fact():
    good = {'claimId': 'c', 'text': SHORT, 'obligationIds': ['mechanism']}
    rejected = {'claimId': 'limit', 'text': 'Overbroad claim', 'obligationIds': ['boundary']}
    result = prepare_coverage_repair({'claims': [good, rejected]},
        {'accepted': [good], 'rejected': [{'claimId': 'limit', 'reason': 'absence_not_established'}]},
        {'gaps': [{'obligationId': 'boundary', 'question': '保证边界？'}], 'verdicts': []})
    assert result['accepted'] == [good]
    assert result['rejected'] == [{'claimId': 'limit', 'reason': 'absence_not_established', 'missingQuestions': ['保证边界？']}]


def test_repair_receives_specific_missing_aspects_from_the_audit():
    claim = {'claimId': 'c', 'text': SHORT, 'obligationIds': ['o']}
    result = prepare_coverage_repair({'claims': [claim]}, {'accepted': [claim], 'rejected': []},
        {'gaps': [{'obligationId': 'o', 'question': '必要条件？',
                   'missingAspects': ['相机主点', '固定划分', '相机主点', None],
                   'aspectEvidenceRefs': ['late', 'late', None]}], 'verdicts': []})
    assert result['rejected'][0]['missingQuestions'] == ['必要条件？', '相机主点', '固定划分']
    assert result['rejected'][0]['missingEvidenceRefs'] == ['late']


def audit_rows(text, status):
    return [{'obligationId': oid, 'status': status, 'bindings': [{'claimId': 'c', 'excerpt': text}],
             'aspects': [{'aspectId': 'conditions', 'requirement': 'Necessary camera conditions',
                          'status': status, 'basis': {'kind': 'source', 'evidenceId': 'e',
                          'excerpt': 'Camera calibration uses focal length and principal point'},
                          'bindings': [{'claimId': 'c', 'excerpt': text}]}]}
            for oid in ('o', 'answer_scope')]


def test_one_revision_completes_omitted_conditions_and_rechecks_without_duplicate_claims():
    original = {'claimId': 'c', 'text': SHORT, 'kind': 'reported', 'evidenceRefs': ['e'], 'obligationIds': ['o']}
    revised = {**original, 'text': FULL}
    gap = {'obligationId': 'o', 'sourceWorkId': 'paper', 'question': '需要哪些条件？'}
    record = {'question': '标定需要哪些条件？', 'state': {'reportBody': {'claims': [original]},
        'plan': [{'itemId': 'i', 'status': 'gap', 'obligations': [{'obligationId': 'o', 'question': '需要哪些条件？'}]}],
        'evidence': deepcopy(EVIDENCE), 'gaps': [gap], 'outputKind': 'claim_verification'}}
    def update(rid, fn, **kwargs):
        nonlocal record
        record = fn(record)
        return record
    stages = []
    def invoke(rid, node, prompt, options, **kwargs):
        stages.append(node)
        if node == 'repair_claims':
            assert 'answer_incomplete' in prompt and 'conditioning inputs' in prompt
            return {'content': json.dumps([{**revised, 'evidenceRefs': ['E1']}])}
        assert node == 'verify_answer_coverage' and kwargs['use_reserve'] is True
        return {'content': json.dumps(audit_rows(FULL, 'covered') if FULL in prompt else audit_rows(SHORT, 'partial'))}
    checker = Mock(side_effect=lambda claims, evidence: [{'claimId': c['claimId'], 'status': 'passed'} for c in claims])
    checker.check_revisions = Mock(side_effect=lambda claims, evidence, context:
        [{'claimId': c['claimId'], 'status': 'passed'} for c in claims])
    make_verify_node(verify_claims, checker, update, invoke)({'run_id': 'r'})
    verified = record['state']['verifiedReport']
    assert len(verified['verifiedClaims']) == 1 and verified['verifiedClaims'][0]['text'] == FULL
    assert verified['answerCoverage']['gaps'] == []
    assert record['state']['initialVerification']['accepted'][0]['text'] == SHORT
    assert record['state']['initialAnswerCoverage']['gaps']
    assert stages == ['verify_answer_coverage', 'repair_claims', 'verify_answer_coverage']
    checker.check_revisions.assert_called_once()
    publish = Mock(return_value=({'publicationId': 'pub'}, True))
    result = make_publish_node(publish, update)({'run_id': 'r', 'report_version_id': 'v'})
    assert result['outcome'] == 'complete'
    assert publish.call_args.kwargs['payload']['gaps'] == []
    assert record['state']['plan'][0]['status'] == 'completed'


def test_failed_revision_keeps_original_verified_text_and_never_attempts_second_repair():
    original = {'claimId': 'c', 'text': SHORT, 'kind': 'reported', 'evidenceRefs': ['e']}
    record = {'question': '完整条件？', 'state': {'reportBody': {'claims': [original]}, 'evidence': deepcopy(EVIDENCE),
        'plan': [{'obligations': [{'obligationId': 'o', 'question': '完整条件？'}]}]}}
    def update(rid, fn, **kwargs):
        nonlocal record
        record = fn(record)
        return record
    calls = []
    def invoke(rid, node, prompt, options, **kwargs):
        calls.append(node)
        return {'content': json.dumps([{**original, 'text': FULL, 'evidenceRefs': ['E1']}])
                if node == 'repair_claims' else json.dumps(audit_rows(SHORT, 'partial'))}
    checker = Mock(return_value=[{'claimId': 'c', 'status': 'passed'}])
    checker.check_revisions = Mock(return_value=[{'claimId': 'c', 'status': 'failed', 'reason': 'unsupported rewrite'}])
    make_verify_node(verify_claims, checker, update, invoke)({'run_id': 'r'})
    report = record['state']['verifiedReport']
    assert report['verifiedClaims'][0]['text'] == SHORT
    assert report['answerCoverage']['gaps'] and report['rejectedClaims'] == []
    assert calls == ['verify_answer_coverage', 'repair_claims']


@pytest.mark.parametrize('checked,expected', [(True, 'complete'), (False, 'partial')])
def test_dropped_extraneous_claim_does_not_force_partial_when_final_answer_is_fully_checked(checked, expected):
    claim = {'claimId': 'c', 'text': FULL, 'kind': 'reported', 'evidenceRefs': ['e'], 'verification': 'semantic_passed'}
    record = {'state': {'outputKind': 'claim_verification', 'evidence': EVIDENCE,
        'verifiedReport': {'verifiedClaims': [claim], 'rejectedClaims': [{'claimId': 'bad', 'reason': 'unsupported'}],
            'answerCoverage': {'status': 'checked' if checked else 'not_checked', 'gaps': [], 'verdicts': audit_rows(FULL, 'covered')}}}}
    def update(rid, fn, **kwargs):
        nonlocal record
        record = fn(record)
        return record
    publish = Mock(return_value=({'publicationId': 'pub'}, True))
    result = make_publish_node(publish, update)({'run_id': 'r', 'report_version_id': 'v'})
    assert result['outcome'] == expected
    assert [c['claimId'] for c in publish.call_args.kwargs['payload']['claims']] == ['c']


@pytest.mark.parametrize('change', ['other_paper', 'proposal', 'unverified', 'invalid_binding', 'duplicate_verdict'])
def test_unrelated_or_unchecked_answer_cannot_close_a_source_gap(change):
    gap = {'obligationId': 'o', 'sourceWorkId': 'paper', 'question': '条件？'}
    claims = [{'claimId': 'c', 'text': FULL, 'kind': 'inference', 'verification': 'semantic_passed', 'evidenceRefs': ['e']}]
    evidence = deepcopy(EVIDENCE)
    audit = {'status': 'checked', 'gaps': [], 'verdicts': audit_rows(FULL, 'covered')[:1]}
    assert remaining_retrieval_gaps([gap], audit, claims, evidence) == []
    if change == 'other_paper':
        evidence[0]['sourceWorkId'] = 'other'
    elif change == 'proposal':
        claims[0]['kind'] = 'proposal'
    elif change == 'unverified':
        claims[0]['verification'] = 'unchecked'
    elif change == 'invalid_binding':
        audit['verdicts'][0]['bindings'][0]['excerpt'] = 'invented unsupported excerpt'
    else:
        audit['verdicts'] *= 2
    assert remaining_retrieval_gaps([gap], audit, claims, evidence) == [gap]
