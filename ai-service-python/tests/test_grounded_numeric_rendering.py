from copy import deepcopy

import pytest

from services.evidence_quotes import prepare_quote_sources, resolve_references
from services.grounded_numeric_rendering import check_numeric_claim
from test_comparison_measurements import fixture


def experiment(operation='value', metric='FPS'):
    raw, sources = fixture()
    binding = raw.pop('measurements')[0]
    binding.pop('value')
    binding.update(id=1, kind='experiment', operation=operation, metric=metric)
    raw.update(summary='核对结果为⟦数值1⟧。', numericBindings=[binding])
    if operation != 'value':
        raw['kind'] = 'inference'
    return raw, list(sources.values())


def literal_claim(kind, quote, literal, label=None):
    source = {'sourceId': 'p', 'pdfId': 'A', 'text': quote}
    binding = {'id': 1, 'kind': kind, 'sourceId': 'p', 'quote': quote, 'literal': literal}
    if label:
        binding['label'] = label
    return {'summary': '正文定义为⟦数值1⟧。', 'kind': 'reported',
            'references': [{'sourceId': 'p', 'quote': quote}], 'numericBindings': [binding]}, [source]


@pytest.mark.parametrize('operation,metric,display', [
    ('value', 'FPS', 'Alpha Dataset：FPS 200'),
    ('difference', 'FPS', 'FPS上升100'),
    ('inverse_ratio', 'Size', 'Size压缩5.00倍'),
    ('ratio', 'Size', 'Size为基线的0.20倍'),
])
def test_server_computes_values_and_keeps_local_conditions(operation, metric, display):
    raw, sources = experiment(operation, metric)
    before = deepcopy((raw, sources))
    checked = check_numeric_claim(raw, sources)
    assert display in checked['summary'] and 'GPU A，基线Baseline *' in checked['summary']
    assert {ref['sourceId'] for ref in checked['references']} == {'t', 'h'}
    assert '⟦数值' not in checked['summary'] and 'numericBindings' not in checked
    assert (raw, sources) == before


@pytest.mark.parametrize('label', ['表1', '表 1', 'Table 1'])
def test_cited_verified_table_label_is_not_an_unbound_measurement(label):
    raw, sources = experiment()
    sources[0]['metadata']['section_title'] = 'Table 1 : Quantitative comparisons'
    raw['summary'] = label + '显示结果为⟦数值1⟧。'
    checked = check_numeric_claim(raw, sources)
    assert label in checked['summary'] and 'FPS 200' in checked['summary']


@pytest.mark.parametrize('mutation', ['wrong_number', 'uncited', 'unverified', 'quantity', 'decimal'])
def test_table_label_exception_cannot_hide_unsupported_numbers(mutation):
    raw, sources = experiment()
    sources[0]['metadata']['section_title'] = 'Table 1 : Quantitative comparisons'
    raw['summary'] = '表1显示结果为⟦数值1⟧。'
    if mutation == 'wrong_number':
        raw['summary'] = raw['summary'].replace('表1', '表2')
    elif mutation == 'uncited':
        raw['references'] = [ref for ref in raw['references'] if ref['sourceId'] != 't']
    elif mutation == 'unverified':
        sources[0].pop('_verifiedTable')
    elif mutation == 'quantity':
        raw['summary'] = raw['summary'].replace('表1', '表1%')
    else:
        raw['summary'] = raw['summary'].replace('表1', '表1.5')
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def test_unverified_surrounding_table_does_not_expand_or_invalidate_checked_row_whitelist():
    raw, sources = experiment()
    sources[0]['metadata']['table_column_mapping_unverified'] = True
    sources[0]['text'] += '\nTable row 4: Unknown | 999 | 20MB | 400 | 30MB'
    _, validation, _ = prepare_quote_sources(sources)
    assert 'FPS 200' in check_numeric_claim(raw, validation)['summary']
    raw['numericBindings'][0]['row'] = 4
    with pytest.raises(ValueError, match='实验绑定结果、基线或指标未核对'):
        check_numeric_claim(raw, validation)


def test_rounding_and_direction_come_from_source_cells_not_duplicate_model_values():
    raw, sources = experiment('difference', 'FPS')
    table = sources[0]
    table['_verifiedTable']['rows'][0][2][0] = '200.27'
    table['text'] = table['text'].replace('100 | 100MB', '200.27 | 100MB')
    raw['references'][0]['quote'] = table['text'].splitlines()[0]
    checked = check_numeric_claim(raw, sources)
    assert 'FPS下降0.27' in checked['summary'] and '-0.27' not in checked['summary']
    raw['numericBindings'][0]['value'] = '-0.27'
    with pytest.raises(ValueError, match='不重复填写value'):
        check_numeric_claim(raw, sources)


def test_ratio_is_rounded_from_cells_once():
    raw, sources = experiment('inverse_ratio', 'Size')
    table = sources[0]
    table['_verifiedTable']['rows'][0][2][1] = '782MB'
    table['_verifiedTable']['rows'][1][2][1] = '45MB'
    table['text'] = table['text'].replace('100MB', '782MB').replace('20MB', '45MB')
    for ref, line in zip(raw['references'], table['text'].splitlines()):
        ref['quote'] = line
    assert '17.38倍' in check_numeric_claim(raw, sources)['summary']


@pytest.mark.parametrize('baseline,result', [('782MB', '45MB'), ('433MB', '25MB')])
def test_coarse_model_precision_cannot_distort_small_storage_ratios(baseline, result):
    raw, sources = experiment('ratio', 'Size')
    raw['numericBindings'][0]['decimals'] = 1
    table = sources[0]
    table['_verifiedTable']['rows'][0][2][1] = baseline
    table['_verifiedTable']['rows'][1][2][1] = result
    table['text'] = table['text'].replace('100MB', baseline).replace('20MB', result)
    for ref, line in zip(raw['references'], table['text'].splitlines()):
        ref['quote'] = line
    before = deepcopy((raw, sources))
    text = check_numeric_claim(raw, sources)['summary']
    assert '0.058倍' in text and '0.1倍' not in text
    assert (raw, sources) == before


def test_ratio_precision_preserves_real_changes_near_one():
    raw, sources = experiment('ratio', 'FPS')
    raw['numericBindings'][0]['decimals'] = 2
    table = sources[0]
    table['_verifiedTable']['rows'][0][2][0] = '1000'
    table['_verifiedTable']['rows'][1][2][0] = '1000.4'
    table['text'] = table['text'].replace('100 | 100MB', '1000 | 100MB').replace('200 | 20MB', '1000.4 | 20MB')
    for ref, line in zip(raw['references'], table['text'].splitlines()):
        ref['quote'] = line
    assert '1.0004倍' in check_numeric_claim(raw, sources)['summary']


def test_ratio_that_cannot_be_represented_without_distortion_is_rejected():
    raw, sources = experiment('ratio', 'Size')
    table = sources[0]
    table['_verifiedTable']['rows'][0][2][1] = '100000000MB'
    table['_verifiedTable']['rows'][1][2][1] = '1MB'
    table['text'] = table['text'].replace('100MB', '100000000MB').replace('20MB', '1MB')
    for ref, line in zip(raw['references'], table['text'].splitlines()):
        ref['quote'] = line
    with pytest.raises(ValueError, match='比值在可显示精度内仍失真'):
        check_numeric_claim(raw, sources)


def test_psnr_difference_keeps_db_unit_and_decimal_precision():
    raw, sources = experiment('difference', 'PSNR')
    table = sources[0]
    table['_verifiedTable']['groups'][0][1][0] = 'PSNR'
    table['_verifiedTable']['rows'][0][2][0] = '27.40'
    table['_verifiedTable']['rows'][1][2][0] = '27.13'
    table['text'] = table['text'].replace('100 | 100MB', '27.40 | 100MB').replace('200 | 20MB', '27.13 | 20MB')
    for ref, line in zip(raw['references'], table['text'].splitlines()):
        ref['quote'] = line
    assert 'PSNR下降0.27 dB' in check_numeric_claim(raw, sources)['summary']


def test_each_dataset_value_is_bound_and_shared_hardware_is_shown_once():
    raw, sources = experiment()
    second = deepcopy(raw['numericBindings'][0])
    second.update(id=2, group=1, dataset='Beta Dataset')
    raw['numericBindings'].append(second)
    raw['summary'] = '两组结果分别为⟦数值1⟧与⟦数值2⟧。'
    text = check_numeric_claim(raw, sources)['summary']
    assert 'Alpha Dataset：FPS 200' in text and 'Beta Dataset：FPS 400' in text
    assert text.count('GPU A，基线Baseline *') == 1


def test_same_experiment_shares_dataset_label_after_all_values_are_verified():
    raw, sources = experiment()
    second = deepcopy(raw['numericBindings'][0])
    second.update(id=2, metric='Size', operation='inverse_ratio')
    raw.update(kind='inference', summary='结果为⟦数值1⟧，⟦数值2⟧。',
               numericBindings=[second, raw['numericBindings'][0]])
    before = deepcopy((raw, sources))
    text = check_numeric_claim(raw, sources)['summary']
    assert text == 'Alpha Dataset：结果为FPS 200，Size压缩5.00倍。（GPU A，基线Baseline *）'
    assert text.count('Alpha Dataset') == 1
    assert (raw, sources) == before


def test_same_dataset_from_different_source_tables_keeps_local_labels():
    raw, sources = experiment()
    table = deepcopy(sources[0])
    table['sourceId'] = 'other-table'
    sources.append(table)
    second = deepcopy(raw['numericBindings'][0])
    second.update(id=2, sourceId='other-table', metric='Size')
    raw['numericBindings'].append(second)
    raw['references'].extend({'sourceId': 'other-table', 'quote': line} for line in table['text'].splitlines())
    raw['summary'] = '结果为⟦数值1⟧与⟦数值2⟧。'
    text = check_numeric_claim(raw, sources)['summary']
    assert 'Alpha Dataset：FPS 200' in text and 'Alpha Dataset：Size 20 MB' in text
    assert text.count('Alpha Dataset') == 2


@pytest.mark.parametrize('mutation', ['free_value', 'missing', 'duplicate', 'unknown', 'extra', 'mixed_contract',
                                     'wrong_dataset', 'wrong_baseline', 'foreign_hardware', 'unverified', 'reported_ratio'])
def test_binding_cannot_bypass_existing_evidence_or_identity_guards(mutation):
    raw, sources = experiment()
    if mutation == 'free_value':
        raw['summary'] += '并有999FPS。'
    elif mutation == 'missing':
        raw['summary'] = '没有占位符。'
    elif mutation == 'duplicate':
        raw['summary'] += '⟦数值1⟧'
    elif mutation == 'unknown':
        raw['summary'] = '⟦数值13⟧'
    elif mutation == 'extra':
        raw['numericBindings'].append(deepcopy(raw['numericBindings'][0]))
    elif mutation == 'mixed_contract':
        raw['measurements'] = []
    elif mutation == 'wrong_dataset':
        raw['numericBindings'][0]['dataset'] = 'Beta Dataset'
    elif mutation == 'wrong_baseline':
        raw['numericBindings'][0]['baseline'] = 'Baseline'
    elif mutation == 'foreign_hardware':
        sources[1]['pdfId'] = 'B'
    elif mutation == 'unverified':
        sources[0].pop('_verifiedTable')
    else:
        raw['numericBindings'][0]['operation'] = 'ratio'
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def test_normalization_parameter_does_not_require_experimental_hardware():
    raw, sources = literal_claim('method_parameter', 'Volume normalization uses the 90% quantile.', '90%', 'quantile')
    checked = check_numeric_claim(raw, sources)
    assert checked['summary'] == '正文定义为90%。'
    assert len(checked['references']) == 1


def test_experimental_caption_can_bind_its_explicit_setting_without_binding_a_metric_as_a_parameter():
    quote = 'With a Gaussian pruning ratio of 66% and SH\nreduced to 2 degrees, SSIM drops from 0.927 to 0.926.'
    for literal, label in [('66%', 'Gaussian pruning ratio'), ('2 degrees', 'SH reduced to')]:
        raw, sources = literal_claim('method_parameter', quote, literal, label)
        assert literal in check_numeric_claim(raw, sources)['summary']
    raw, sources = literal_claim('method_parameter', quote, '0.926', 'Gaussian pruning ratio')
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def test_scientific_method_parameter_is_preserved_without_inventing_units():
    raw, sources = literal_claim('method_parameter', 'The learning rate parameter is set to 1e-4.', '1e-4', 'learning rate')
    assert check_numeric_claim(raw, sources)['summary'] == '正文定义为1e-4。'
    raw['numericBindings'][0]['literal'] = '0.0001'
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def test_bare_method_scalar_cannot_drop_the_original_percent_unit():
    raw, sources = literal_claim('method_parameter', 'Volume normalization uses the 90% quantile.', '90', 'quantile')
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


@pytest.mark.parametrize('mutation', ['number', 'name', 'quote', 'performance_as_parameter'])
def test_method_parameters_require_literal_definition_and_cannot_hide_performance(mutation):
    raw, sources = literal_claim('method_parameter', 'Volume normalization uses the 90% quantile.', '90%', 'quantile')
    if mutation == 'number':
        raw['numericBindings'][0]['literal'] = '95%'
    elif mutation == 'name':
        raw['numericBindings'][0]['label'] = 'unknown'
    elif mutation == 'quote':
        raw['numericBindings'][0]['quote'] = 'Another normalization uses 90% quantile.'
    else:
        quote = 'The threshold improves FPS by 90%.'
        raw, sources = literal_claim('method_parameter', quote, '90%', 'threshold')
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def author_report():
    raw, sources = literal_claim('author_report', 'We report ≥30fps at 1080p resolution.', '≥30fps')
    raw['numericBindings'].append({**raw['numericBindings'][0], 'id': 2, 'literal': '1080p'})
    raw['summary'] = '作者报告在⟦数值2⟧下达到⟦数值1⟧。'
    return raw, sources


def test_author_claim_preserves_comparator_and_resolution_without_fake_experimental_conditions():
    raw, sources = author_report()
    text = check_numeric_claim(raw, sources)['summary']
    assert '1080p下达到≥30fps' in text and '作者报告，未作同条件比较' in text


@pytest.mark.parametrize('mutation', ['drop_comparator', 'drop_resolution', 'rank', 'inference', 'table'])
def test_author_report_cannot_omit_qualifiers_or_become_a_comparison(mutation):
    raw, sources = author_report()
    if mutation == 'drop_comparator':
        raw['numericBindings'][0]['literal'] = '30fps'
    elif mutation == 'drop_resolution':
        raw['numericBindings'].pop()
        raw['summary'] = '作者报告⟦数值1⟧。'
    elif mutation == 'rank':
        raw['summary'] += '因此比其他方法更快。'
    elif mutation == 'inference':
        raw['kind'] = 'inference'
    else:
        sources[0]['metadata'] = {'evidence_kind': 'table'}
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def test_catalog_selection_resolves_bindings_without_mutating_generated_json():
    raw, sources = literal_claim('method_parameter', 'Volume normalization uses the 90% quantile.', '90%', 'quantile')
    _, validation, catalog = prepare_quote_sources(sources)
    qid = next(iter(catalog['p']))
    raw['references'] = [{'sourceId': 'p', 'quoteId': qid}]
    raw['numericBindings'][0].pop('quote')
    raw['numericBindings'][0]['quoteId'] = qid
    before = deepcopy(raw)
    selected = resolve_references(raw, catalog, require_selection=True)
    assert '90%' in check_numeric_claim(selected, validation)['summary']
    assert raw == before
    raw['numericBindings'][0]['quoteId'] = 'wrong'
    with pytest.raises(ValueError, match='摘录选择不存在'):
        resolve_references(raw, catalog, require_selection=True)


def test_quote_only_parameter_binding_restores_source_for_both_binding_and_claim():
    raw, sources = literal_claim('method_parameter', 'Volume normalization uses the 90% quantile.', '90%', 'quantile')
    _, validation, catalog = prepare_quote_sources(sources)
    qid = next(iter(catalog['p']))
    raw['references'] = [{'quoteId': qid}]
    binding = raw['numericBindings'][0]
    binding.pop('sourceId')
    binding.pop('quote')
    binding['quoteId'] = qid
    before = deepcopy(raw)
    selected = resolve_references(raw, catalog, require_selection=True)
    result = check_numeric_claim(selected, validation)
    assert result['summary'] == '正文定义为90%。'
    assert result['references'][0]['sourceId'] == 'p'
    assert selected['numericBindings'][0]['sourceId'] == 'p'
    assert raw == before


def test_token_without_bindings_never_leaks_to_published_output():
    raw, sources = experiment()
    raw.pop('numericBindings')
    with pytest.raises(ValueError, match='缺少绑定'):
        check_numeric_claim(raw, sources)


def test_new_contract_is_used_in_actual_critique_synthesis_entry_with_mocked_provider():
    import json
    from unittest.mock import patch
    from services.grounded_critique import synthesize_critique

    raw, sources = experiment('inverse_ratio', 'Size')
    _, _, catalog = prepare_quote_sources(sources)
    for ref in [*raw['references'], *raw['numericBindings'][0]['conditionReferences']]:
        quote = ref.pop('quote')
        ref['quoteId'] = next(qid for qid, text in catalog[ref['sourceId']].items() if text == quote)
    raw['section'] = 'contribution'
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps({'findings': [raw]})) as model:
        result = synthesize_critique('压缩效果', sources)
    assert model.call_count == 1
    assert '5.00倍' in result['message'] and '⟦数值' not in result['message']
    assert 'numericBindings' in model.call_args.args[0]
    issue = result['critique']['issues'][0]
    assert issue['conclusionClaimId'] in {claim['id'] for claim in result['critique']['claims']}
    assert all(claim['references'] for claim in result['critique']['claims'])


def test_new_contract_is_used_in_actual_comparison_entry_with_mocked_provider():
    import json
    from unittest.mock import patch
    from services.grounded_comparison import synthesize_comparison

    raw, sources = experiment()
    sources.append({'sourceId': 'b', 'pdfId': 'B', 'text': 'The second method uses an alternative representation.'})
    _, _, catalog = prepare_quote_sources(sources)
    for ref in [*raw['references'], *raw['numericBindings'][0]['conditionReferences']]:
        quote = ref.pop('quote')
        ref['quoteId'] = next(qid for qid, text in catalog[ref['sourceId']].items() if text == quote)
    raw['paperId'] = 'A'
    other = {'paperId': 'B', 'kind': 'reported', 'summary': '作者使用另一种表示。',
             'references': [{'sourceId': 'b', 'quoteId': next(iter(catalog['b']))}]}
    payload = {'claims': [], 'dimensions': [{'label': '实现', 'cells': [raw, other]}]}
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(payload)) as model:
        result = synthesize_comparison('比较实现', sources, ['A', 'B'])
    assert model.call_count == 1
    assert 'Alpha Dataset：FPS 200' in result['message'] and '⟦数值' not in result['message']
    assert result['comparisonTable'][0]['cells'][0]['references'][-1]['sourceId'] == 'h'
