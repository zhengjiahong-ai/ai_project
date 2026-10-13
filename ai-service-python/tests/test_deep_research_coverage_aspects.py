from copy import deepcopy

import pytest

from services.deep_research.coverage_aspects import invalid_coverage_aspects


CLAIMS = [{'claimId': 'c', 'text': 'The mechanism depends on direction and distance.'}]
ROWS = [{'evidenceId': 'e', 'quote': 'Direction and distance condition the attributes.'}]
VERDICT = {'obligationId': 'o', 'status': 'covered', 'aspects': [{
    'aspectId': 'inputs', 'requirement': 'Conditioning inputs', 'status': 'covered',
    'basis': {'kind': 'source', 'evidenceId': 'e', 'excerpt': 'Direction and distance'},
    'bindings': [{'claimId': 'c', 'excerpt': 'direction and distance'}]}]}


def test_grounded_aspect_with_answer_binding_is_structurally_valid():
    original = deepcopy(VERDICT)
    assert invalid_coverage_aspects([VERDICT], CLAIMS, ROWS, []) == []
    assert VERDICT == original


def test_access_metadata_requires_cited_identity_exact_value_and_request_binding():
    claims = [{'claimId': 'c', 'kind': 'reported', 'text': '本回答使用全文中的方法片段。', 'evidenceRefs': ['e']}]
    binding = [{'claimId': 'c', 'excerpt': '使用全文中的方法片段'}]
    basis = {'kind': 'source_metadata', 'evidenceId': 'e', 'field': 'accessLevel',
             'value': 'fulltext', 'requestExcerpt': '实际读到的是摘要还是全文'}
    v = {'obligationId': 'o', 'status': 'covered', 'bindings': binding, 'aspects': [{
        'aspectId': 'access', 'requirement': '访问范围', 'status': 'covered',
        'basis': basis, 'bindings': binding}]}
    rows = [{'evidenceId': 'e', 'accessLevel': 'fulltext'}]
    questions = ['实际读到的是摘要还是全文？']
    assert invalid_coverage_aspects([v], claims, rows, questions) == []
    for key, value in [('value', 'abstract'), ('field', 'title'), ('evidenceId', 'foreign'),
                       ('requestExcerpt', 'invented question')]:
        changed = deepcopy(v); changed['aspects'][0]['basis'][key] = value
        assert invalid_coverage_aspects([changed], claims, rows, questions) == ['o']
    assert invalid_coverage_aspects([v], [{**claims[0], 'evidenceRefs': []}], rows, questions) == ['o']
    mixed = deepcopy(v)
    mixed['aspects'].append({**deepcopy(v['aspects'][0]), 'aspectId': 'method',
                            'basis': {'kind': 'request', 'excerpt': questions[0]}})
    assert invalid_coverage_aspects([mixed], claims, rows, questions) == ['o']


@pytest.mark.parametrize('change', ['absent', 'missing', 'invented_source', 'unknown_source',
                                   'invented_answer', 'unknown_claim', 'duplicate', 'bad_id'])
def test_overall_covered_cannot_hide_invalid_or_missing_aspect(change):
    v = deepcopy(VERDICT)
    aspect = v['aspects'][0]
    if change == 'absent': v.pop('aspects')
    elif change == 'missing': aspect['status'] = 'missing'
    elif change == 'invented_source': aspect['basis']['excerpt'] = 'fabricated source words'
    elif change == 'unknown_source': aspect['basis']['evidenceId'] = 'foreign'
    elif change == 'invented_answer': aspect['bindings'][0]['excerpt'] = 'not in the final answer'
    elif change == 'unknown_claim': aspect['bindings'][0]['claimId'] = 'rejected'
    elif change == 'duplicate': v['aspects'].append(deepcopy(aspect))
    elif change == 'bad_id': aspect['aspectId'] = []
    assert invalid_coverage_aspects([v], CLAIMS, ROWS, []) == ['o']


def test_explicit_request_can_ground_prospective_requirement_without_source():
    v = deepcopy(VERDICT)
    v['aspects'][0]['basis'] = {'kind': 'request', 'excerpt': 'compare inputs'}
    assert invalid_coverage_aspects([v], CLAIMS, [], ['Please compare inputs']) == []
    assert invalid_coverage_aspects([v], CLAIMS, [], ['Different request']) == ['o']


def test_source_basis_may_use_exact_antecedent_context_but_not_invent_it():
    v = deepcopy(VERDICT)
    v['aspects'][0]['basis']['excerpt'] = 'Baseline B has this limitation.'
    rows = [{**ROWS[0], 'sourceContext': {'before': 'Baseline B has this limitation. ', 'after': ''}}]
    assert invalid_coverage_aspects([v], CLAIMS, rows, []) == []
    assert invalid_coverage_aspects([v], CLAIMS, ROWS, []) == ['o']


def test_ambiguous_duplicate_evidence_identity_cannot_ground_aspect():
    assert invalid_coverage_aspects([VERDICT], CLAIMS, ROWS * 2, []) == ['o']


def test_synthetic_request_check_can_reuse_factual_obligations_without_source_duplication():
    v = deepcopy(VERDICT)
    v['bindings'] = v['aspects'][0]['bindings']
    v['aspects'][0]['basis'] = {'kind': 'request', 'excerpt': 'Explain the mechanism'}
    claims = [{**CLAIMS[0], 'kind': 'reported'}]
    assert invalid_coverage_aspects([v], claims, ROWS, ['Explain the mechanism']) == ['o']
    assert invalid_coverage_aspects([v], claims, ROWS, ['Explain the mechanism'],
                                    request_only_obligations=['o']) == []
