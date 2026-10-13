"""Independent validation boundaries for author observations and interpretations."""
import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from services.evidence_quotes import prepare_quote_sources
from services.grounded_critique import check_critique_payload, synthesize_critique

SOURCES = [
    {'sourceId': 'method', 'pdfId': 'A', 'text': 'The method samples camera positions around training views.'},
    {'sourceId': 'cost', 'pdfId': 'A', 'text': 'Pruning reduces storage with a quality tradeoff.'},
]


def fixture():
    _, sources, catalog = prepare_quote_sources(SOURCES)
    fact = {'summary': '作者在训练视角周围采样相机位置。',
            'references': [{'quoteId': next(iter(catalog['method']))}]}
    inference = {'summary': '评估剪枝应同时考虑存储收益与质量代价。',
                 'references': [{'quoteId': next(iter(catalog['cost']))}]}
    return {'assessments': [{'section': 'risk', 'observation': fact, 'inference': inference}]}, sources, catalog


@pytest.mark.parametrize('mutation', [None, 'unbound', 'changed_value', 'missing_unit', 'wrong_reference'])
def test_nested_method_parameter_requires_its_own_exact_literal_binding(mutation):
    quote = 'The Gaussian volume is normalized by the 90% largest of all sorted Gaussians.'
    _, sources, catalog = prepare_quote_sources([
        {'sourceId': 'parameter', 'pdfId': 'A', 'text': quote}, *SOURCES])
    qid = next(iter(catalog['parameter']))
    fact = {'summary': '作者采用⟦数值1⟧分位的体积归一化参考。',
        'references': [{'quoteId': qid}],
        'numericBindings': [{'id': 1, 'kind': 'method_parameter', 'quoteId': qid,
                             'label': 'normalized', 'literal': '90%'}]}
    if mutation == 'unbound':
        fact['summary'] = fact['summary'].replace('⟦数值1⟧', '90%')
        fact.pop('numericBindings')
    elif mutation == 'changed_value':
        fact['numericBindings'][0]['literal'] = '95%'
    elif mutation == 'missing_unit':
        fact['numericBindings'][0]['literal'] = '90'
    elif mutation == 'wrong_reference':
        fact['numericBindings'][0]['quoteId'] = next(iter(catalog['method']))
    payload = {'assessments': [{'section': 'weakness', 'observation': fact}]}
    before = deepcopy(payload)
    if mutation:
        with pytest.raises(ValueError):
            check_critique_payload(payload, sources, catalog)
    else:
        findings, _ = check_critique_payload(payload, sources, catalog)
        assert findings[0]['kind'] == 'reported' and '90%' in findings[0]['summary']
        assert findings[0]['references'] == [{'sourceId': 'parameter', 'quote': quote}]
    assert payload == before


def test_roles_and_references_stay_independent_without_mutating_response():
    payload, sources, catalog = fixture()
    original = deepcopy(payload)
    findings, questions = check_critique_payload(payload, sources, catalog)
    assert payload == original and questions == []
    assert [claim['kind'] for claim in findings] == ['reported', 'inference']
    assert [claim['references'][0]['sourceId'] for claim in findings] == ['method', 'cost']
    assert all(claim['section'] == 'risk' for claim in findings)


def test_invalid_key_inference_does_not_publish_an_orphan_observation_as_a_judgment():
    payload, _, _ = fixture()
    payload['assessments'][0]['inference']['summary'] = '原文未提供目标域外验证。'
    payload['pendingQuestions'] = [{'topic': '目标域外视角的适用性'}]
    original = deepcopy(payload)
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(payload)) as model:
        result = synthesize_critique('批判采样的适用性', SOURCES, allow_partial=True)
    assert model.call_count == 1 and payload == original
    assert result['partial'] and result['groundedClaims'] == []
    assert result['critique']['issues'] == []
    assert '原文未提供' not in result['message']
    assert '待核查：目标域外视角的适用性' in result['message']
    assert '本次尚不能判断' in result['message']
    assert result['rag_sources'] == []


def test_inference_cannot_borrow_the_observation_citations():
    payload, sources, catalog = fixture()
    payload['assessments'][0]['inference']['references'] = []
    rejected = []
    findings, _ = check_critique_payload(payload, sources, catalog, allow_partial=True, rejected=rejected)
    assert len(findings) == 1 and findings[0]['kind'] == 'reported' and len(rejected) == 1


def test_bad_observation_does_not_hide_independently_supported_inference():
    payload, sources, catalog = fixture()
    payload['assessments'][0]['observation']['references'][0]['quoteId'] = 'unknown'
    rejected = []
    findings, _ = check_critique_payload(payload, sources, catalog, allow_partial=True, rejected=rejected)
    assert len(findings) == 1 and findings[0]['kind'] == 'inference' and len(rejected) == 1
    assert findings[0]['references'][0]['sourceId'] == 'cost'


def test_numeric_calculation_must_still_be_an_inference():
    from test_experiment_facts import facts, claim
    clean, sources, catalog = facts()
    calculated = claim(clean, 'inverse_ratio', 'Size')
    calculated.pop('kind')
    payload = {'assessments': [{'section': 'weakness', 'observation': calculated}]}
    with pytest.raises(ValueError, match='须标为推断'):
        check_critique_payload(payload, sources, catalog)
    payload['assessments'][0] = {'section': 'weakness', 'inference': calculated}
    findings, _ = check_critique_payload(payload, sources, catalog)
    assert findings[0]['kind'] == 'inference' and '压缩5.00倍' in findings[0]['summary']
    assert {reference['sourceId'] for reference in findings[0]['references']} == {'t', 'h'}


@pytest.mark.parametrize('mutation', ['mixed_formats', 'kind_override', 'shared_references',
                                     'empty', 'null', 'invalid_section', 'too_many_claims'])
def test_malformed_new_contract_is_not_partially_repaired(mutation):
    payload, sources, catalog = fixture()
    assessment = payload['assessments'][0]
    if mutation == 'mixed_formats':
        payload['findings'] = []
    elif mutation == 'kind_override':
        assessment['observation']['kind'] = 'inference'
    elif mutation == 'shared_references':
        assessment['references'] = assessment['observation'].pop('references')
    elif mutation == 'empty':
        assessment.pop('observation'); assessment.pop('inference')
    elif mutation == 'null':
        assessment['observation'] = None
    elif mutation == 'invalid_section':
        assessment['section'] = 'whatever'
    else:
        payload['assessments'] *= 9
    with pytest.raises(ValueError):
        check_critique_payload(payload, sources, catalog, allow_partial=True)


@pytest.mark.parametrize('count', [5, 8])
def test_bounded_assessments_validate_every_paired_claim(count):
    payload, sources, catalog = fixture()
    payload['assessments'] = [deepcopy(payload['assessments'][0]) for _ in range(count)]
    original = deepcopy(payload)
    findings, _ = check_critique_payload(payload, sources, catalog)
    assert len(findings) == 2 * count and payload == original
    payload['assessments'][-1]['inference']['references'] = [{'quoteId': 'unknown'}]
    rejected = []
    findings, _ = check_critique_payload(payload, sources, catalog, allow_partial=True, rejected=rejected)
    # The final pair is not silently trimmed to fit the output budget.
    assert len(findings) == 2 * count - 1 and len(rejected) == 1


def test_all_invalid_components_return_a_concrete_unresolved_answer_without_fake_judgments():
    payload, _, _ = fixture()
    for field in ('observation', 'inference'):
        payload['assessments'][0][field]['summary'] = '论文未验证动态场景。'
    payload['pendingQuestions'] = [{'topic': '动态场景表现'}]
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(payload)) as model:
        result = synthesize_critique('批判', SOURCES, allow_partial=True)
    assert result['partial'] and not result['critique']['issues']
    assert result['critique']['coverage']['unresolvedQuestionPartIds'] == ['main']
    assert '动态场景表现' in result['message']
    assert model.call_count == 1


def test_same_source_fact_and_inference_are_distinct_in_the_result():
    payload, _, _ = fixture()
    payload['assessments'][0]['inference']['references'] = deepcopy(payload['assessments'][0]['observation']['references'])
    payload['assessments'][0]['inference']['summary'] = '训练监督视角分布应与目标相机分布一起评估。'
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(payload)) as model:
        result = synthesize_critique('批判', SOURCES)
    assert not result['partial'] and len(result['groundedClaims']) == 2
    assert [claim['kind'] for claim in result['critique']['claims']] == ['reported', 'inference']
    assert result['summary'].count('[1]') == 2
    assert len(result['rag_sources']) == 1
    assert model.call_count == 1
