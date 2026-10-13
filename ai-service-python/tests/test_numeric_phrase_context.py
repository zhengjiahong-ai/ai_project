from copy import deepcopy

import pytest

from services.grounded_numeric_rendering import check_numeric_claim
from test_grounded_numeric_rendering import literal_claim, author_report


def dataset_report():
    quote = 'We reduce storage from 782MB to 45MB with SSIM decrease of only 0.007 on Mip-NeRF 360.'
    raw, sources = literal_claim('author_report', quote, 'from 782MB to 45MB')
    raw['numericBindings'].append({**raw['numericBindings'][0], 'id': 2,
                                   'literal': 'SSIM decrease of only 0.007 on Mip-NeRF 360'})
    raw['summary'] = 'Mip-NeRF 360上，作者报告⟦数值1⟧，且⟦数值2⟧。'
    sources.append({'sourceId': 'table', 'pdfId': 'A', 'text': 'Verified table',
                    '_verifiedTable': {'groups': [('Mip-NeRF 360 Datasets', ['SSIM'])]}})
    return raw, sources


def test_contiguous_multi_quantity_report_preserves_values_and_source_phrase_and_dataset_identity():
    raw, sources = dataset_report()
    before = deepcopy((raw, sources))
    result = check_numeric_claim(raw, sources)
    assert '从782MB到45MB' in result['summary']
    assert 'SSIM仅下降0.007' in result['summary']
    assert result['references'][0]['quote'] == before[0]['references'][0]['quote']
    assert result['summary'].endswith('（作者报告，未作同条件比较）')
    assert (raw, sources) == before


@pytest.mark.parametrize('change', ['foreign_table', 'wrong_name', 'missing_prose_name', 'free_performance'])
def test_identifier_exception_never_licenses_new_numbers_or_foreign_names(change):
    raw, sources = dataset_report()
    if change == 'foreign_table':
        sources[-1]['pdfId'] = 'B'
    elif change == 'wrong_name':
        raw['summary'] = raw['summary'].replace('360', '361')
    elif change == 'missing_prose_name':
        raw['references'][0]['quote'] = raw['references'][0]['quote'].replace('Mip-NeRF 360', 'another benchmark')
        sources[0]['text'] = raw['references'][0]['quote']
        for binding in raw['numericBindings']:
            binding['quote'] = sources[0]['text']
    else:
        raw['summary'] += '速度360 FPS。'
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


@pytest.mark.parametrize('literal', ['782', '782MB', '782MB to 45', 'from 782MB to 46MB'])
def test_shortening_or_changing_quantities_cannot_hide_missing_report_context(literal):
    raw, sources = dataset_report()
    raw['numericBindings'][0]['literal'] = literal
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def test_a_quality_report_does_not_repeat_independent_storage_numbers_from_same_excerpt():
    raw, sources = dataset_report()
    raw['numericBindings'] = [{**raw['numericBindings'][1], 'id': 1}]
    raw['summary'] = '在Mip-NeRF 360上，作者报告⟦数值1⟧。'
    result = check_numeric_claim(raw, sources)
    assert '0.007' in result['summary'] and '782MB' not in result['summary']


def test_dataset_identity_in_referenced_verified_table_header_is_not_a_measurement():
    from test_grounded_numeric_rendering import experiment
    raw, sources = experiment()
    sources[0]['_verifiedTable']['groups'][0][0] = 'Mip-NeRF 360 Datasets'
    raw['numericBindings'][0]['dataset'] = 'Mip-NeRF 360 Datasets'
    raw['summary'] = 'Mip-NeRF 360上，⟦数值1⟧。'
    assert 'Mip-NeRF 360' in check_numeric_claim(raw, sources)['summary']


def test_renderer_does_not_repeat_server_supplied_ratio_unit():
    from test_grounded_numeric_rendering import experiment
    raw, sources = experiment('inverse_ratio', 'Size')
    raw['summary'] = '压缩约⟦数值1⟧倍。'
    text = check_numeric_claim(raw, sources)['summary']
    assert '5.00倍' in text and '倍倍' not in text


def test_author_report_accepts_explicit_source_resolution_in_chinese_template():
    raw, sources = author_report()
    raw['numericBindings'].pop()
    raw['summary'] = '作者报告在1080p分辨率下达到⟦数值1⟧。'
    assert '1080p分辨率下达到≥30fps' in check_numeric_claim(raw, sources)['summary']
    raw['summary'] = raw['summary'].replace('1080p', '2160p')
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


def test_resolution_cannot_be_taken_from_uncited_or_unrelated_performance_prose():
    raw, sources = literal_claim('author_report', 'We report ≥30fps.', '≥30fps')
    raw['summary'] = '作者报告1080p下达到⟦数值1⟧。'
    sources.append({'sourceId': 'other', 'pdfId': 'A', 'text': '1080p resolution.'})
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)
    quote = 'We report 1080p and ≥30fps.'
    raw['references'][0]['quote'] = sources[0]['text'] = raw['numericBindings'][0]['quote'] = quote
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)


@pytest.mark.parametrize('literal', ['30fps', 'from 30fps to 60fps'])
def test_phrase_cannot_drop_comparator_or_range_endpoints(literal):
    raw, sources = literal_claim('author_report', 'We report ≥30fps to 60fps at 1080p resolution.', literal)
    with pytest.raises(ValueError):
        check_numeric_claim(raw, sources)
