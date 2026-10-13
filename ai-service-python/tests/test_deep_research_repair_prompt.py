from copy import deepcopy
import json
from services.deep_research.repair_prompt import factor_repair_questions


def test_factorization_roundtrip_retains_every_question_and_claim_binding():
    original = {'a': {'reason': 'incomplete', 'missingQuestions': ['exact question 一', 'other', 'exact question 一'],
                      'missingEvidenceRefs': ['e1']},
                'b': {'missingQuestions': ['other'], 'detail': 'unchanged'}}
    before = deepcopy(original)
    dictionary, packed = factor_repair_questions(original)
    assert len(dictionary) == 2
    restored = deepcopy(packed)
    for row in restored.values():
        row['missingQuestions'] = [dictionary[key] for key in row.pop('missingQuestionIds')]
    assert restored == original == before


def test_unknown_or_colliding_fields_are_preserved_without_reinterpretation():
    original = {'a': {'missingQuestions': [None]}, 'b': {'detail': 'plain'},
                'c': {'missingQuestions': ['x'], 'missingQuestionIds': ['user-field']}}
    dictionary, packed = factor_repair_questions(original)
    assert dictionary == {} and packed == original


def test_repeated_long_questions_are_stored_once_without_truncation():
    question = '完整的实验条件与数据范围问题' * 30
    original = {str(i): {'missingQuestions': [question]} for i in range(10)}
    dictionary, packed = factor_repair_questions(original)
    assert list(dictionary.values()) == [question]
    assert len(json.dumps([dictionary, packed], ensure_ascii=False)) < len(json.dumps(original, ensure_ascii=False)) / 2


def test_repair_target_is_not_also_frozen_and_only_generated_suffix_is_removed():
    from services.deep_research.execution_materialization import materialize_execution_claim
    from services.deep_research.repair import repair_rejected
    from test_deep_research_group_spec_integration import group_claim
    target = materialize_execution_claim(group_claim())
    accepted_other = {'claimId': 'other', 'kind': 'proposal', 'text': 'Keep this choice.'}
    verification = {'accepted': [target, accepted_other], 'rejected': [
        {'claimId': 'g', 'reason': 'answer_incomplete', 'missingEvidenceRefs': ['long-evidence']} ]}
    evidence = [{'evidenceId': 'long-evidence', 'sourceWorkId': 'paper', 'sourceVersionId': 'v',
                 'quote': 'Exact existing source', 'obligationIds': []}]
    target['evidenceRefs'] = ['long-evidence']
    original = deepcopy((target, verification, evidence))
    def capture(prompt):
        decoder = json.JSONDecoder()
        context = decoder.raw_decode(prompt.split('Accepted experimental definitions (consistency only; do not revise these or treat them as paper evidence):\n')[1])[0]
        assert [c['claimId'] for c in context] == ['other']
        targets = decoder.raw_decode(prompt.split('Rejected claims and checks:\n')[1])[0]
        assert targets[0]['claim']['text'] == group_claim()['text']
        assert targets[0]['claim']['executionSpec'] == target['executionSpec']
        assert targets[0]['check']['missingEvidenceRefs'] == ['E1']
        assert 'Exact existing source' in prompt
        return {'content': '[]'}
    assert repair_rejected({'claims': [target]}, verification, evidence, 'Repair', capture, json.loads) == []
    assert (target, verification, evidence) == original
