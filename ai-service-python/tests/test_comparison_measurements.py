from copy import deepcopy
import json

import pytest

from services.comparison_measurements import bounded_table_body, validate_numeric_comparison
from services.research_synthesis import validate_claim


PACKET = {'groups': [['Alpha Dataset', ['FPS', 'Size']], ['Beta Dataset', ['FPS', 'Size']]],
          'rows': [[2, 'Baseline *', ['100', '100MB', '300', '90MB']],
                   [3, 'Ours', ['200', '20MB', '400', '30MB']]]}
BASE = 'Table row 2: Baseline * | 100 | 100MB | 300 | 90MB'
OURS = 'Table row 3: Ours | 200 | 20MB | 400 | 30MB'


def fixture():
    table = {'sourceId': 't', 'pdfId': 'A', 'text': BASE + '\n' + OURS,
             'metadata': {'evidence_kind': 'table', 'table_verified_data': json.dumps(PACKET)},
             '_verifiedTable': deepcopy(PACKET)}
    hardware = {'sourceId': 'h', 'pdfId': 'A', 'text': 'All measurements were performed on GPU A.'}
    measurement = {'sourceId': 't', 'row': 3, 'group': 0, 'metric': 'FPS', 'value': '200',
                   'baselineRow': 2, 'dataset': 'Alpha Dataset', 'hardware': 'GPU A', 'baseline': 'Baseline *',
                   'conditionReferences': [{'sourceId': 'h', 'quote': hardware['text']}]}
    raw = {'summary': 'Alpha（GPU A，Baseline *）中，Ours 为200 FPS。', 'kind': 'reported',
           'references': [{'sourceId': 't', 'quote': BASE}, {'sourceId': 't', 'quote': OURS}],
           'measurements': [measurement]}
    return raw, {'t': table, 'h': hardware}


def check(raw, sources):
    checked = validate_claim(raw, list(sources.values()))
    validate_numeric_comparison(raw, checked, sources)
    return checked


@pytest.mark.parametrize('summary', [
    'Ours的PSNR/SSIM略低于3D-GS*，LPIPS略高。',
    'SSIM优于3DGS，PSNR接近3D-GS。',
    'PSNR低于3D-GS，LPIPS高于3D-GS*。',
])
def test_qualitative_metric_comparison_does_not_parse_method_name_as_value(summary):
    raw, sources = fixture()
    raw.pop('measurements')
    raw['summary'] = summary
    assert check(raw, sources)['summary'] == summary


@pytest.mark.parametrize('summary', [
    'SSIM为0.806。', 'PSNR下降0.27。', 'LPIPS 0.237.',
    'PSNR 27.13，SSIM为0.806。', '3D-GS的SSIM为0.813。',
    '体积以90%分位数归一化。',
])
def test_real_unbound_values_still_require_measurement_evidence(summary):
    raw, sources = fixture()
    raw.pop('measurements')
    raw['summary'] = summary
    with pytest.raises(ValueError, match='缺少逐项实验条件'):
        check(raw, sources)


def test_metric_parser_does_not_backtrack_into_a_partial_identifier():
    from services.comparison_measurements import MENTION
    assert MENTION.search('SSIM略低于27.13D-GS') is None
    assert MENTION.search('PSNR 27.13.').group('score') == '27.13'


def test_numeric_cell_keeps_its_dataset_hardware_baseline_and_same_paper_sources():
    raw, sources = fixture()
    checked = check(raw, sources)
    assert {ref['sourceId'] for ref in checked['references']} == {'t', 'h'}
    assert 'measurements' not in checked  # Existing public claim contract.


def test_legacy_measurement_cannot_publish_a_distorted_rounded_ratio():
    raw, sources = fixture()
    raw['kind'] = 'inference'
    raw['summary'] = 'Alpha（GPU A，Baseline *）中，Ours占基线的0.1倍。'
    raw['measurements'][0].update(metric='Size', operation='ratio', value='0.1')
    table = sources['t']
    table['_verifiedTable']['rows'][0][2][1] = '782MB'
    table['_verifiedTable']['rows'][1][2][1] = '45MB'
    table['text'] = table['text'].replace('100MB', '782MB').replace('20MB', '45MB')
    for ref, line in zip(raw['references'], table['text'].splitlines()):
        ref['quote'] = line
    with pytest.raises(ValueError, match='比值精度会扭曲'):
        check(raw, sources)
    raw['summary'] = raw['summary'].replace('0.1倍', '0.058倍')
    raw['measurements'][0]['value'] = '0.058'
    assert '0.058倍' in check(raw, sources)['summary']


def accelerator_fixture():
    raw, sources = fixture()
    raw['measurements'][0]['hardware'] = 'NVIDIA A6000 GPU'
    sources['h']['text'] = 'All measurements were performed on NVIDIA A6000 GPU.'
    raw['measurements'][0]['conditionReferences'] = [{'sourceId': 'h', 'quote': sources['h']['text']}]
    return raw, sources


def test_specific_hardware_model_may_be_displayed_without_vendor_and_gpu_suffix():
    raw, sources = accelerator_fixture()
    raw['summary'] = 'Alpha（A6000平台，Baseline *）：Ours为200 FPS。'
    checked = check(raw, sources)
    assert checked['summary'] == raw['summary']
    assert any('NVIDIA A6000 GPU' in ref['quote'] for ref in checked['references'])


@pytest.mark.parametrize('display', ['A600', 'A60000', 'A6000Ada', 'RTXA6000', 'AMD A6000', 'CPU A6000', 'AMD GPU A6000', 'CPU NVIDIA A6000', '另一块GPU'])
def test_hardware_shortening_cannot_change_model_vendor_or_device_type(display):
    raw, sources = accelerator_fixture()
    raw['summary'] = f'Alpha（{display}，Baseline *）：Ours为200 FPS。'
    with pytest.raises(ValueError, match='本条结果'):
        check(raw, sources)


def test_hardware_shortening_does_not_remove_same_paper_literal_condition_proof():
    raw, sources = accelerator_fixture()
    raw['summary'] = 'Alpha（A6000，Baseline *）：Ours为200 FPS。'
    sources['h']['text'] = 'All measurements were performed on NVIDIA A5000 GPU.'
    raw['measurements'][0]['conditionReferences'] = [{'sourceId': 'h', 'quote': sources['h']['text']}]
    with pytest.raises(ValueError, match='硬件没有原文依据'):
        check(raw, sources)


def test_dataset_conjunction_can_use_ampersand_without_changing_group():
    raw, sources = fixture()
    sources['t']['_verifiedTable']['groups'][0][0] = 'Red and Blue Dataset'
    raw['measurements'][0]['dataset'] = 'Red and Blue Dataset'
    raw['summary'] = 'Red&Blue（GPU A，Baseline *）：Ours为200 FPS。'
    check(raw, sources)
    raw['summary'] = 'Red&Green（GPU A，Baseline *）：Ours为200 FPS。'
    with pytest.raises(ValueError, match='本条结果'):
        check(raw, sources)


def test_generic_hardware_label_still_requires_complete_label_not_single_letter():
    raw, sources = fixture()
    raw['summary'] = 'Alpha（A，Baseline *）：Ours为200 FPS。'
    with pytest.raises(ValueError, match='本条结果'):
        check(raw, sources)


@pytest.mark.parametrize('change', ['missing', 'wrong_group', 'wrong_value', 'wrong_baseline', 'foreign_hardware', 'hidden_conditions', 'extra_number', 'unverified_table'])
def test_mixed_or_uncovered_experiment_numbers_are_rejected(change):
    raw, sources = fixture()
    if change == 'missing':
        raw.pop('measurements')
    elif change == 'wrong_group':
        raw['measurements'][0]['group'] = 1
    elif change == 'wrong_value':
        raw['measurements'][0]['value'] = '237'
    elif change == 'wrong_baseline':
        raw['measurements'][0]['baseline'] = 'Baseline'
    elif change == 'foreign_hardware':
        sources['h']['pdfId'] = 'B'
    elif change == 'hidden_conditions':
        raw['summary'] = 'Ours为200 FPS。'
    elif change == 'extra_number':
        raw['summary'] += '并为25 MB。'
    else:
        sources['t'].pop('_verifiedTable')
    with pytest.raises(ValueError):
        check(raw, sources)


@pytest.mark.parametrize('operation,metric,value,summary', [
    ('difference', 'FPS', '100', '差值100 FPS'),
    ('ratio', 'FPS', '2.00', '速度为2倍'),
    ('inverse_ratio', 'Size', '5', '存储压缩5倍')])
def test_derived_metrics_use_the_same_dataset_and_explicit_baseline(operation, metric, value, summary):
    raw, sources = fixture()
    raw['summary'] = 'Alpha（GPU A，Baseline *）：' + summary
    raw['kind'] = 'inference'
    raw['measurements'][0].update(operation=operation, metric=metric, value=value)
    check(raw, sources)


def test_false_compression_ratio_is_rejected():
    raw, sources = fixture()
    raw['summary'] = 'Alpha（GPU A，Baseline *）：存储压缩15倍。'
    raw['kind'] = 'inference'
    raw['measurements'][0].update(operation='inverse_ratio', metric='Size', value='15')
    with pytest.raises(ValueError, match='单元不一致'):
        check(raw, sources)


@pytest.mark.parametrize('claim', ['999帧/秒', '999帧每秒', '999 frames per second', '999×压缩', '999x compression', '999 MiB'])
def test_common_unit_spellings_cannot_skip_numeric_evidence_checks(claim):
    raw, sources = fixture()
    raw['summary'] = 'Alpha（GPU A，Baseline *）：' + claim
    with pytest.raises(ValueError):
        check(raw, sources)


@pytest.mark.parametrize('unit', ['帧/秒', '帧每秒', '帧/s', 'frames per second', 'frames/sec', 'FPS'])
def test_supported_frame_rate_spellings_keep_the_same_evidence_conditions(unit):
    raw, sources = fixture()
    raw['summary'] = 'Alpha（GPU A，Baseline *）：Ours 为200 ' + unit + '。'
    check(raw, sources)
    raw.pop('measurements')
    with pytest.raises(ValueError, match='缺少逐项实验条件'):
        check(raw, sources)


@pytest.mark.parametrize('unit', ['×', 'x', '倍'])
def test_compression_ratio_spellings_require_the_verified_calculation(unit):
    raw, sources = fixture()
    raw['summary'] = 'Alpha（GPU A，Baseline *）：存储压缩5' + unit + '。'
    raw['kind'] = 'inference'
    raw['measurements'][0].update(operation='inverse_ratio', metric='Size', value='5')
    check(raw, sources)


def test_matrix_dimensions_are_not_treated_as_compression_ratios():
    raw, sources = fixture()
    raw['summary'] += '采用3×3矩阵和2x3矩阵。'
    check(raw, sources)


def test_binary_storage_unit_cannot_relabel_a_decimal_storage_measurement():
    raw, sources = fixture()
    raw['summary'] = 'Alpha（GPU A，Baseline *）：存储20 MiB。'
    raw['measurements'][0].update(metric='Size', value='20MB')
    with pytest.raises(ValueError, match='未逐项核对'):
        check(raw, sources)


def test_author_frame_rate_report_accepts_equivalent_wording_without_changing_quotes():
    raw, sources = fixture()
    quote = 'On Alpha Dataset, Ours reaches 200 frames per second compared with Baseline *.'
    sources['p'] = {'sourceId': 'p', 'pdfId': 'A', 'text': quote}
    raw['references'] = [{'sourceId': 'p', 'quote': quote}]
    raw['measurements'][0].update(sourceId='p', quote=quote)
    checked = check(raw, sources)
    assert checked['references'][0]['quote'] == quote


def test_derived_value_cannot_be_published_as_an_author_report():
    raw, sources = fixture()
    raw['summary'] = 'Alpha（GPU A，Baseline *）：速度为2倍。'
    raw['measurements'][0].update(operation='ratio', value='2')
    with pytest.raises(ValueError, match='须标为推断'):
        check(raw, sources)


def test_reported_prose_retains_support_with_one_continuous_result_context():
    raw, sources = fixture()
    quote = 'On Alpha Dataset, Ours reaches 200 FPS compared with Baseline *.'
    sources['p'] = {'sourceId': 'p', 'pdfId': 'A', 'text': quote}
    raw['references'] = [{'sourceId': 'p', 'quote': quote}]
    raw['measurements'][0].update(sourceId='p', quote=quote)
    check(raw, sources)
    raw['measurements'][0]['dataset'] = 'Beta Dataset'
    with pytest.raises(ValueError):
        check(raw, sources)


def test_table_packet_and_body_share_existing_budget_and_visible_complete_rows():
    raw, sources = fixture()
    source = sources['t']
    source['text'] = 'Original header. ' * 30 + BASE + '\n' + OURS
    body, packet = bounded_table_body(source, source['text'], 500)
    assert packet['rows'] == PACKET['rows']
    assert len(body) + len(json.dumps(packet, ensure_ascii=False, separators=(',', ':'))) <= 500
    assert BASE in body and OURS in body and body in source['text']
    clipped, unavailable = bounded_table_body(source, source['text'], 30)
    assert unavailable is None


def test_critique_axis_receives_checked_columns_without_mutating_source_snapshots():
    from core.pdf_quality import _format_axis_prompt_block
    raw, sources = fixture()
    original = deepcopy(sources['t'])
    prompt = _format_axis_prompt_block({'label': '实验', 'key': 'experiments', 'evidence': [sources['t']]})
    assert 'PDF交叉核对的表格列' in prompt
    assert 'Alpha Dataset' in prompt and 'Beta Dataset' in prompt
    assert BASE in prompt and OURS in prompt
    assert sources['t'] == original
