from copy import deepcopy

import pytest

from services.deep_research.obligation_purpose import (
    normalize_obligation_purposes, nonblocking_research_obligations,
)

QUESTION = 'Explain the requested experimental design without historical benchmark repetition.'
TEXT = 'The accepted answer contains concrete paired experimental groups.'
CLAIMS = [{'claimId': 'c', 'text': TEXT}]
BINDINGS = [{'claimId': 'c', 'excerpt': TEXT}]
EXCERPT = 'requested experimental design'
REASON = 'The historical benchmark list is unnecessary for this proposed intervention.'


def plan():
    return [{'itemId': 'p', 'question': 'subtask', 'dependencies': [], 'obligations': [
        {'obligationId': 'required', 'question': 'give experiment'},
        {'obligationId': 'support', 'question': 'historical benchmark list',
         'purpose': 'supporting_research', 'requestExcerpt': EXCERPT}]}]


def verdicts():
    return [{'obligationId': 'required', 'status': 'covered', 'bindings': deepcopy(BINDINGS)},
            {'obligationId': 'support', 'status': 'not_required', 'reason': REASON,
             'requestExcerpt': EXCERPT, 'bindings': deepcopy(BINDINGS)},
            {'obligationId': 'whole', 'status': 'covered', 'bindings': deepcopy(BINDINGS)}]


def check(p=None, v=None, claims=None, **kwargs):
    return nonblocking_research_obligations(plan() if p is None else p, QUESTION,
        CLAIMS if claims is None else claims, verdicts() if v is None else v, 'whole', **kwargs)


def test_normalization_preserves_nested_plan_and_input():
    p = plan()
    before = deepcopy(p)
    result = normalize_obligation_purposes(p, QUESTION)
    assert result[0]['itemId'] == 'p' and result[0]['dependencies'] == []
    assert result[0]['obligations'][0]['purpose'] == 'answer_requirement'
    assert result[0]['obligations'][1]['purpose'] == 'supporting_research'
    assert p == before


@pytest.mark.parametrize('excerpt', [None, '', 'short', 'not in original question', [], {}])
def test_ungrounded_support_hint_stays_required(excerpt):
    p = plan()
    p[0]['obligations'][1]['requestExcerpt'] = excerpt
    row = normalize_obligation_purposes(p, QUESTION)[0]['obligations'][1]
    assert row['purpose'] == 'answer_requirement'
    assert 'requestExcerpt' not in row
    assert not check(p=p)


def test_positive_scope_record_uses_real_binding_and_coverage_helpers():
    result = check()
    assert result == [{'obligationId': 'support', 'reason': REASON,
                       'requestExcerpt': EXCERPT, 'bindings': BINDINGS}]


@pytest.mark.parametrize('change', [{'status': 'covered'}, {'status': 'missing'},
    {'reason': 'vague'}, {'reason': ' ' * 20}, {'requestExcerpt': 'forged original request'},
    {'bindings': []}, {'bindings': [{'claimId': 'c', 'excerpt': 'fabricated answer text'}]},
    {'bindings': [{'claimId': 'unknown', 'excerpt': TEXT}]}])
def test_optional_exemption_requires_explicit_grounded_final_verdict(change):
    v = verdicts()
    v[1].update(change)
    assert not check(v=v)


def test_required_or_legacy_obligation_cannot_be_exempted():
    for purpose in ['answer_requirement', None, 'invented']:
        p = plan()
        p[0]['obligations'][1]['purpose'] = purpose
        assert not check(p=p)


@pytest.mark.parametrize('change', ['missing', 'partial', 'duplicate', 'invalid_binding'])
def test_whole_original_request_must_have_unique_supported_coverage(change):
    v = verdicts()
    if change == 'missing':
        v.pop()
    elif change == 'partial':
        v[-1]['status'] = 'partial'
    elif change == 'duplicate':
        v.append(deepcopy(v[-1]))
    else:
        v[-1]['bindings'] = [{'claimId': 'c', 'excerpt': 'fabricated original scope coverage'}]
    assert not check(v=v)


@pytest.mark.parametrize('change', ['missing', 'partial', 'duplicate', 'invalid_binding'])
def test_every_required_deliverable_must_still_be_covered(change):
    v = verdicts()
    if change == 'missing':
        v.pop(0)
    elif change == 'partial':
        v[0]['status'] = 'partial'
    elif change == 'duplicate':
        v.append(deepcopy(v[0]))
    else:
        v[0]['bindings'] = []
    assert not check(v=v)


def test_duplicate_identities_and_invalid_aspects_fail_closed():
    p = plan()
    p[0]['obligations'].append(deepcopy(p[0]['obligations'][1]))
    assert not check(p=p)
    p = plan()
    p[0]['obligations'][1]['obligationId'] = 'whole'
    assert not check(p=p)
    assert not check(claims=CLAIMS + deepcopy(CLAIMS))
    assert not check(v=verdicts() + [deepcopy(verdicts()[1])])
    assert not check(invalid_aspect_ids=['whole'])


@pytest.mark.parametrize('bad', [None, {}, 'bad', [None], [{'obligations': None}],
    [{'obligations': ['bad']}], [{'obligations': [{'obligationId': []}]}]])
def test_malformed_plan_does_not_exempt_anything(bad):
    assert nonblocking_research_obligations(bad, QUESTION, CLAIMS, verdicts(), 'whole') == []


def test_unknown_or_malformed_verdict_ids_cannot_match():
    v = verdicts()
    v[1]['obligationId'] = ['support']
    assert not check(v=v)
    assert not check(v=[None, {}, {'id': 'support'}])


def test_one_pending_support_question_does_not_change_another_scope_decision():
    p = plan()
    p[0]['obligations'].append({'obligationId': 'other', 'purpose': 'supporting_research',
                               'requestExcerpt': EXCERPT, 'question': 'another context query'})
    assert [r['obligationId'] for r in check(p=p)] == ['support']


def test_output_is_independent_copy():
    p, v = plan(), verdicts()
    before = deepcopy((p, v, CLAIMS))
    result = check(p=p, v=v)
    result[0]['bindings'][0]['excerpt'] = 'changed'
    assert (p, v, CLAIMS) == before
