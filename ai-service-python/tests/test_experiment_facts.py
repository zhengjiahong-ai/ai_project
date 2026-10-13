from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from services.evidence_quotes import prepare_quote_sources, resolve_references
from services.grounded_numeric_rendering import check_numeric_claim, brief_experiment_claim
from services.grounded_comparison import synthesize_comparison
from services.experiment_facts import HARDWARE
from test_comparison_measurements import fixture


def facts():
    _, sources = fixture()
    return prepare_quote_sources(list(sources.values()))


def choose(clean, model='Ours', dataset='Alpha Dataset', metric='FPS'):
    return next(fact['factId'] for source in clean for fact in source.get('experimentFacts', [])
                if (fact['model'], fact['dataset'], fact['metric']) == (model, dataset, metric))


def claim(clean, operation='value', metric='FPS'):
    binding = {'id': 1, 'kind': 'experiment', 'factId': choose(clean, metric=metric), 'operation': operation}
    if operation != 'value':
        binding['baselineFactId'] = choose(clean, 'Baseline *', metric=metric)
    return {'summary': '核对结果为⟦数值1⟧。', 'kind': 'reported' if operation == 'value' else 'inference',
            'references': [], 'numericBindings': [binding]}


def test_fact_ids_are_stable_and_only_visible_cells_become_choices():
    _, sources = fixture()
    sources['t']['text'] += '\nTable row 4: Unverified | 999 | 2MB | 999 | 2MB'
    before = deepcopy(sources)
    clean, validation, _ = prepare_quote_sources(list(sources.values()))
    again, _, _ = prepare_quote_sources(list(reversed(list(sources.values()))))
    assert clean[0]['experimentFacts'] == again[1]['experimentFacts']
    assert len(clean[0]['experimentFacts']) == 8
    assert {fact['model'] for fact in clean[0]['experimentFacts']} == {'Baseline *', 'Ours'}
    assert all(fact['row'] in {2, 3} for fact in validation[0]['_experimentFacts'].values())
    assert sources == before


@pytest.mark.parametrize('operation,metric,expected', [
    ('value', 'FPS', 'Ours FPS 200'),
    ('difference', 'FPS', 'Ours FPS上升100'),
    ('ratio', 'Size', 'Ours 存储为基线的0.20倍'),
    ('inverse_ratio', 'Size', 'Ours 存储压缩5.00倍'),
])
def test_selected_fact_restores_numbers_conditions_and_all_references(operation, metric, expected):
    clean, validation, catalog = facts()
    raw = claim(clean, operation, metric)
    before = deepcopy(raw)
    result = check_numeric_claim(resolve_references(raw, catalog, require_selection=True), validation)
    assert expected in result['summary'] and 'GPU A' in result['summary']
    assert ('模型Ours' if operation == 'value' else 'Ours相对基线Baseline *') in result['summary']
    assert {ref['sourceId'] for ref in result['references']} == {'t', 'h'}
    assert 'factId' not in result and '⟦' not in result['summary']
    assert raw == before


@pytest.mark.parametrize('mutation', ['unknown', 'free_row', 'free_value', 'internal_model',
                                    'missing_baseline', 'same_cell', 'other_dataset', 'other_metric', 'wrong_kind'])
def test_fact_bindings_cannot_override_conditions_or_mix_incompatible_cells(mutation):
    clean, validation, _ = facts()
    raw = claim(clean, 'difference')
    binding = raw['numericBindings'][0]
    if mutation == 'unknown':
        binding['factId'] = 'invented'
    elif mutation == 'free_row':
        binding['row'] = 999
    elif mutation == 'free_value':
        binding['value'] = 999
    elif mutation == 'internal_model':
        binding['_factModel'] = 'Invented model'
    elif mutation == 'missing_baseline':
        binding.pop('baselineFactId')
    elif mutation == 'same_cell':
        binding['baselineFactId'] = binding['factId']
    elif mutation == 'other_dataset':
        binding['baselineFactId'] = choose(clean, 'Baseline *', dataset='Beta Dataset')
    elif mutation == 'other_metric':
        binding['baselineFactId'] = choose(clean, 'Baseline *', metric='Size')
    else:
        binding['kind'] = 'author_report'
    with pytest.raises(ValueError):
        check_numeric_claim(raw, validation)


def test_value_does_not_accept_a_baseline_and_calculations_are_inferences():
    clean, validation, _ = facts()
    raw = claim(clean)
    raw['numericBindings'][0]['baselineFactId'] = choose(clean, 'Baseline *')
    with pytest.raises(ValueError, match='单个实验值'):
        check_numeric_claim(raw, validation)
    raw = claim(clean, 'difference')
    raw['kind'] = 'reported'
    with pytest.raises(ValueError, match='须标为推断'):
        check_numeric_claim(raw, validation)


def test_same_model_and_dataset_share_labels_for_values_and_computed_differences():
    clean, validation, _ = facts()
    raw = claim(clean, 'difference')
    second = claim(clean)['numericBindings'][0]
    second['id'] = 2
    raw.update(summary='变化为⟦数值1⟧，结果为⟦数值2⟧。', numericBindings=[raw['numericBindings'][0], second])
    text = check_numeric_claim(raw, validation)['summary']
    assert text == 'Alpha Dataset（Ours）：变化为FPS上升100，结果为FPS 200。（GPU A，Ours相对基线Baseline *）'


def test_brief_experiments_keep_each_dataset_baseline_and_quality_value():
    clean, validation, _ = facts()
    bindings = []
    for dataset in ('Alpha Dataset', 'Beta Dataset'):
        for metric, operation in [('Size', 'inverse_ratio'), ('FPS', 'difference')]:
            bindings.append({'id': len(bindings) + 1, 'kind': 'experiment',
                'factId': choose(clean, dataset=dataset, metric=metric), 'operation': operation,
                'baselineFactId': choose(clean, 'Baseline *', dataset=dataset, metric=metric)})
    raw = {'summary': '压缩为⟦数值1⟧、⟦数值3⟧；差异为⟦数值2⟧、⟦数值4⟧。结果仅适用于已核对场景。',
           'kind': 'inference', 'references': [], 'numericBindings': bindings}
    before = deepcopy((raw, validation))
    checked = check_numeric_claim(raw, validation)
    full = deepcopy(checked)
    brief = brief_experiment_claim(raw, checked, validation)
    assert 'Alpha Dataset（GPU A，Ours相对基线Baseline *）：存储压缩5.00倍、FPS上升100' in brief
    assert 'Beta Dataset（GPU A，Ours相对基线Baseline *）：存储压缩3.00倍、FPS上升100' in brief
    assert '结果仅适用于已核对场景。' in brief
    assert checked == full and (raw, validation) == before


def test_brief_results_never_merge_distinct_table_identities():
    _, original = fixture()
    other = deepcopy(original['t'])
    other['sourceId'] = 'other'
    original['other'] = other
    clean, validation, _ = prepare_quote_sources(list(original.values()))
    choices = [next(fact['factId'] for fact in source['experimentFacts']
                    if (fact['model'], fact['dataset'], fact['metric']) == ('Ours', 'Alpha Dataset', 'FPS'))
               for source in clean if source.get('experimentFacts')]
    raw = {'summary': '两次记录为⟦数值1⟧、⟦数值2⟧。', 'kind': 'reported', 'references': [],
           'numericBindings': [{'id': i + 1, 'kind': 'experiment', 'factId': choice, 'operation': 'value'}
                               for i, choice in enumerate(choices)]}
    checked = check_numeric_claim(raw, validation)
    assert brief_experiment_claim(raw, checked, validation).count('Alpha Dataset（') == 2


def test_brief_quality_cost_keeps_negative_direction_and_unit():
    _, original = fixture()
    table = original['t']
    table['_verifiedTable']['groups'][0][1][0] = 'PSNR'
    table['_verifiedTable']['rows'][0][2][0] = '27.40'
    table['_verifiedTable']['rows'][1][2][0] = '27.13'
    table['metadata']['table_verified_data'] = json.dumps(table['_verifiedTable'])
    table['text'] = table['text'].replace('100 | 100MB', '27.40 | 100MB').replace('200 | 20MB', '27.13 | 20MB')
    clean, validation, _ = prepare_quote_sources(list(original.values()))
    raw = claim(clean, 'difference', 'PSNR')
    checked = check_numeric_claim(raw, validation)
    brief = brief_experiment_claim(raw, checked, validation)
    assert 'PSNR下降0.27 dB' in brief and 'Ours相对基线Baseline *' in brief
    assert '上升' not in brief and '27.13 dB' not in brief


def renamed_datasets(first, second):
    _, sources = fixture()
    packet = deepcopy(sources['t']['_verifiedTable'])
    packet['groups'][0][0], packet['groups'][1][0] = first, second
    sources['t']['_verifiedTable'] = packet
    sources['t']['metadata']['table_verified_data'] = json.dumps(packet)
    return prepare_quote_sources(list(sources.values()))


def test_plural_header_suffix_is_shortened_without_sharing_two_dataset_identities():
    clean, validation, _ = renamed_datasets('Alpha Datasets', 'Beta Datasets')
    first = {'id': 1, 'kind': 'experiment',
             'factId': choose(clean, dataset='Alpha Datasets'), 'operation': 'value'}
    second = {'id': 2, 'kind': 'experiment',
              'factId': choose(clean, dataset='Beta Datasets'), 'operation': 'value'}
    raw = {'summary': '分别为⟦数值1⟧与⟦数值2⟧。', 'kind': 'reported',
           'references': [], 'numericBindings': [first, second]}
    before = deepcopy((raw, validation))
    result = check_numeric_claim(raw, validation)
    assert 'Alpha：Ours FPS 200' in result['summary']
    assert 'Beta：Ours FPS 400' in result['summary']
    assert 'Datasets' not in result['summary']
    assert {ref['sourceId'] for ref in result['references']} == {'t', 'h'}
    assert (raw, validation) == before


def test_shortening_is_disabled_when_distinct_dataset_names_would_collide():
    clean, validation, _ = renamed_datasets('Alpha', 'Alpha Datasets')
    bindings = [{'id': i, 'kind': 'experiment', 'factId': choose(clean, dataset=name), 'operation': 'value'}
                for i, name in enumerate(('Alpha', 'Alpha Datasets'), 1)]
    raw = {'summary': '分别为⟦数值1⟧与⟦数值2⟧。', 'kind': 'reported',
           'references': [], 'numericBindings': bindings}
    text = check_numeric_claim(raw, validation)['summary']
    assert 'Alpha：Ours FPS 200' in text and 'Alpha Datasets：Ours FPS 400' in text


def test_shared_short_label_keeps_storage_and_speed_values_and_the_same_baseline():
    clean, validation, _ = renamed_datasets('Alpha Datasets', 'Beta Datasets')
    size = {'id': 1, 'kind': 'experiment', 'operation': 'inverse_ratio',
            'factId': choose(clean, dataset='Alpha Datasets', metric='Size'),
            'baselineFactId': choose(clean, 'Baseline *', 'Alpha Datasets', 'Size')}
    fps = {'id': 2, 'kind': 'experiment', 'operation': 'value',
           'factId': choose(clean, dataset='Alpha Datasets')}
    raw = {'summary': '结果为⟦数值1⟧，⟦数值2⟧。', 'kind': 'inference',
           'references': [], 'numericBindings': [size, fps]}
    text = check_numeric_claim(raw, validation)['summary']
    assert text == 'Alpha（Ours）：结果为存储压缩5.00倍，FPS 200。（GPU A，Ours相对基线Baseline *）'


@pytest.mark.parametrize('other_model,other_dataset', [('Baseline *', 'Alpha Dataset'), ('Ours', 'Beta Dataset')])
def test_different_models_or_datasets_keep_their_local_identity(other_model, other_dataset):
    clean, validation, _ = facts()
    raw = claim(clean)
    second = {'id': 2, 'kind': 'experiment', 'factId': choose(clean, other_model, other_dataset), 'operation': 'value'}
    raw.update(summary='⟦数值1⟧；⟦数值2⟧。', numericBindings=[raw['numericBindings'][0], second])
    text = check_numeric_claim(raw, validation)['summary']
    assert 'Alpha Dataset：Ours FPS 200' in text
    assert f'{other_dataset}：{other_model} FPS' in text


@pytest.mark.parametrize('condition', ['missing', 'ambiguous', 'another_paper', 'unverified_table'])
def test_no_fact_is_offered_without_a_whitelist_and_unambiguous_same_paper_hardware(condition):
    _, sources = fixture()
    if condition == 'missing':
        sources.pop('h')
    elif condition == 'ambiguous':
        sources['h']['text'] += ' Other experiments were performed on NVIDIA A5000 GPU.'
    elif condition == 'another_paper':
        sources['h']['pdfId'] = 'B'
    else:
        sources['t']['metadata'].pop('table_verified_data')
    clean, validation, _ = prepare_quote_sources(list(sources.values()))
    assert all('experimentFacts' not in source for source in clean)
    assert all('_experimentFacts' not in source for source in validation)


def test_preexisting_private_choices_cannot_survive_a_missing_hardware_context():
    _, sources = fixture()
    sources.pop('h')
    sources['t']['_experimentFacts'] = {'stale': {'hardware': 'Invented'}}
    _, validation, _ = prepare_quote_sources(list(sources.values()))
    assert '_experimentFacts' not in validation[0]


@pytest.mark.parametrize('text,expected', [
    ('All evaluations use NVIDIA A6000 GPU.', 'NVIDIA A6000 GPU'),
    ('The experiments use RTX 4090 GPU.', 'RTX 4090 GPU'),
    ('The system requires 100 GPU hours.', None),
    ('Our method uses 1000 CPU cores.', None),
])
def test_device_options_do_not_mistake_resource_counts_for_hardware_models(text, expected):
    matches = list(HARDWARE.finditer(text))
    assert ([match.group() for match in matches] if matches else None) == ([expected] if expected else None)


def test_cross_paper_table_cannot_use_another_papers_selected_fact():
    _, sources = fixture()
    sources['b'] = {'sourceId': 'b', 'pdfId': 'B', 'text': 'The second method uses an alternative representation.'}
    clean, _, catalog = prepare_quote_sources(list(sources.values()))
    selected = claim(clean)
    selected['paperId'] = 'B'
    other = {'paperId': 'A', 'summary': '结果来自原文。', 'kind': 'reported',
             'references': [{'sourceId': 'h', 'quoteId': next(iter(catalog['h']))}]}
    payload = {'claims': [], 'dimensions': [{'label': '速度', 'cells': [other, selected]}]}
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(payload)):
        with pytest.raises(ValueError, match='其他论文'):
            synthesize_comparison('比较速度', list(sources.values()), ['A', 'B'])
