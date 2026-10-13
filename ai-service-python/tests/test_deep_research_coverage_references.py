import json
from copy import deepcopy

import pytest

from services.deep_research.coverage_references import resolve_coverage_references
from services.deep_research.coverage_aspects import invalid_coverage_aspects
from services.deep_research.final_coverage import audit_final_answer


CLAIMS = [{'claimId': 'c', 'kind': 'reported', 'text': '编码器输出时空特征，解码器预测形变。',
           'conditions': {'输入': '固定已知的时间戳'}, 'evidenceRefs': ['e']}]
ROWS = [{'evidenceId': 'e', 'quote': 'The encoder\nproduces features.',
         'sourceContext': {'before': 'Given a known timestamp. ', 'after': ' The decoder predicts deformation.'}}]
VERDICT = {'obligationId': 'o', 'status': 'covered', 'bindings': [{'claimId': 'c', 'field': 'text'}],
           'aspects': [{'aspectId': 'io', 'requirement': '输入输出分工', 'status': 'covered',
                       'basis': {'kind': 'source', 'evidenceId': 'e', 'field': 'quote'},
                       'bindings': [{'claimId': 'c', 'field': 'text'}]}]}


def test_field_references_preserve_original_source_whitespace_and_full_answer():
    before = deepcopy((VERDICT, CLAIMS, ROWS))
    result = resolve_coverage_references([VERDICT], CLAIMS, ROWS)
    assert result[0]['aspects'][0]['basis']['excerpt'] == ROWS[0]['quote']
    assert result[0]['bindings'][0]['excerpt'] == CLAIMS[0]['text']
    assert invalid_coverage_aspects(result, CLAIMS, ROWS, []) == []
    assert (VERDICT, CLAIMS, ROWS) == before


def test_context_and_conditions_are_bound_only_to_the_selected_field():
    value = deepcopy(VERDICT)
    value['aspects'][0]['basis']['field'] = 'sourceContext.after'
    value['aspects'][0]['bindings'][0]['field'] = 'conditions'
    result = resolve_coverage_references([value], CLAIMS, ROWS)
    assert result[0]['aspects'][0]['basis']['excerpt'] == ROWS[0]['sourceContext']['after']
    assert result[0]['aspects'][0]['bindings'][0]['excerpt'] == json.dumps(CLAIMS[0]['conditions'], ensure_ascii=False, sort_keys=True)
    assert invalid_coverage_aspects(result, CLAIMS, ROWS, []) == []


@pytest.mark.parametrize('change', ['unknown_field', 'unknown_source', 'source_not_in_prompt',
    'context_not_in_prompt', 'unknown_claim', 'duplicate_source', 'duplicate_claim',
    'source_excerpt_conflict', 'answer_excerpt_conflict', 'nonstring_field'])
def test_invalid_references_never_close_an_obligation(change):
    value, claims, rows = deepcopy((VERDICT, CLAIMS, ROWS))
    basis = value['aspects'][0]['basis']
    if change == 'unknown_field': basis['field'] = 'title'
    elif change == 'nonstring_field': basis['field'] = []
    elif change == 'unknown_source': basis['evidenceId'] = 'invented'
    elif change == 'source_not_in_prompt': rows = []
    elif change == 'context_not_in_prompt':
        basis['field'] = 'sourceContext.after'; rows[0].pop('sourceContext')
    elif change == 'unknown_claim': value['aspects'][0]['bindings'][0]['claimId'] = 'rejected'
    elif change == 'duplicate_source': rows.append(deepcopy(rows[0]))
    elif change == 'duplicate_claim': claims.append(deepcopy(claims[0]))
    elif change == 'source_excerpt_conflict': basis['excerpt'] = 'fabricated words'
    elif change == 'answer_excerpt_conflict': value['aspects'][0]['bindings'][0]['excerpt'] = 'changed answer'
    result = resolve_coverage_references([value], claims, rows)
    assert invalid_coverage_aspects(result, claims, rows, []) == ['o']


def test_legacy_literal_response_is_never_repaired_or_rewritten():
    value = deepcopy(VERDICT)
    value['bindings'] = [{'claimId': 'c', 'excerpt': '编码器输出时空特征……预测形变'}]
    value['aspects'][0]['bindings'] = deepcopy(value['bindings'])
    value['aspects'][0]['basis'] = {'kind': 'source', 'evidenceId': 'e', 'excerpt': 'The encoder produces features.'}
    result = resolve_coverage_references([value], CLAIMS, ROWS)
    assert result == [value]
    assert invalid_coverage_aspects(result, CLAIMS, ROWS, []) == ['o']


def test_field_and_literal_are_rejected_even_when_the_literal_is_true_and_preserved():
    value = deepcopy(VERDICT)
    value['aspects'][0]['basis']['excerpt'] = ROWS[0]['quote']
    value['bindings'][0]['excerpt'] = CLAIMS[0]['text']
    result = resolve_coverage_references([value], CLAIMS, ROWS)
    assert result[0]['aspects'][0]['basis']['excerpt'] == ROWS[0]['quote']
    assert result[0]['bindings'][0]['excerpt'] == CLAIMS[0]['text']
    assert result[0]['aspects'][0]['basis']['referenceError'] == 'field_excerpt_conflict'
    assert result[0]['bindings'][0]['referenceError'] == 'field_excerpt_conflict'
    assert invalid_coverage_aspects(result, CLAIMS, ROWS, []) == ['o']


def test_audit_resolves_reference_response_before_existing_hard_checks():
    def invoke(run_id, node, prompt, options, **kwargs):
        assert '"field":"text"' in prompt and '"field":"quote"' in prompt
        return {'content': json.dumps([VERDICT, {**VERDICT, 'obligationId': 'answer_scope'}])}
    result = audit_final_answer('r', '研究输入输出关系', [{'obligations': [{'obligationId': 'o', 'question': '输入输出'}]}],
                               CLAIMS, ROWS, invoke, json.loads)
    assert result['status'] == 'checked' and result['gaps'] == []
    assert result['verdicts'][0]['bindings'][0]['excerpt'] == CLAIMS[0]['text']


def test_field_bindings_cannot_replace_an_omitted_whole_question_verdict():
    def invoke(run_id, node, prompt, options, **kwargs):
        assert 'including the original-question scope: ["o", "answer_scope"]' in prompt
        return {'content': json.dumps([VERDICT])}
    result = audit_final_answer('r', '研究输入输出关系', [{'obligations': [{'obligationId': 'o', 'question': '输入输出'}]}],
                               CLAIMS, ROWS, invoke, json.loads)
    assert [gap['obligationId'] for gap in result['gaps']] == ['answer_scope']
