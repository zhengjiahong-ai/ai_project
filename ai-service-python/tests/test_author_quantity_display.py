from copy import deepcopy

import pytest

from services.grounded_numeric_rendering import check_numeric_claim
from test_grounded_numeric_rendering import literal_claim
from test_numeric_phrase_context import dataset_report


def test_real_duplicate_metric_phrase_becomes_concise_without_changing_source():
    raw, sources = dataset_report()
    raw['summary'] = '作者报告从⟦数值1⟧，在Mip-NeRF 360上SSIM下降仅⟦数值2⟧。'
    before = deepcopy((raw, sources))
    text = check_numeric_claim(raw, sources)['summary']
    assert 'SSIM仅下降0.007。' in text
    assert '作者报告从782MB到45MB' in text
    assert 'SSIM decrease' not in text and text.count('Mip-NeRF 360') == 1
    assert (raw, sources) == before


@pytest.mark.parametrize('prefix', ['SSIM提升仅', 'LPIPS下降仅'])
def test_wrong_metric_or_direction_is_rejected_instead_of_repaired(prefix):
    raw, sources = dataset_report()
    raw['summary'] = 'Mip-NeRF 360上⟦数值1⟧，' + prefix + '⟦数值2⟧。'
    with pytest.raises(ValueError, match='指标或变化方向'):
        check_numeric_claim(raw, sources)


@pytest.mark.parametrize('literal,prefix,expected', [
    ('over 200 FPS', '超过', '超过200 FPS'),
    ('≥30fps', '至少', '≥30fps'),
    ('at most 45MB', '不超过', '不超过45MB'),
    ('about 45MB', '约', '约45MB'),
])
def test_comparator_is_rendered_once_and_not_lost(literal, prefix, expected):
    raw, sources = literal_claim('author_report', 'We report ' + literal + '.', literal)
    raw['summary'] = '作者报告' + prefix + '⟦数值1⟧。'
    assert '作者报告' + expected + '。' in check_numeric_claim(raw, sources)['summary']


@pytest.mark.parametrize('literal,prefix', [('over 200 FPS', '至少'), ('≥30fps', '超过'), ('30fps', '超过'),
                                          ('at most 45MB', '至少'), ('about 45MB', '超过')])
def test_template_cannot_change_strictness_or_add_an_unsupported_bound(literal, prefix):
    raw, sources = literal_claim('author_report', 'We report ' + literal + '.', literal)
    raw['summary'] = '作者报告' + prefix + '⟦数值1⟧。'
    with pytest.raises(ValueError, match='数量上下界'):
        check_numeric_claim(raw, sources)


def test_metric_only_is_not_invented_and_db_not_dropped():
    literal = 'PSNR increase of 0.27 dB'
    raw, sources = literal_claim('author_report', 'We report ' + literal + '.', literal)
    assert 'PSNR上升0.27 dB' in check_numeric_claim(raw, sources)['summary']
    raw['summary'] = 'PSNR上升仅⟦数值1⟧。'
    with pytest.raises(ValueError, match='未提供的限定词'):
        check_numeric_claim(raw, sources)


def test_unknown_phrase_is_verbatim_and_never_translated_by_guessing():
    literal = 'from 782MB to 45MB after a specific pipeline'
    raw, sources = literal_claim('author_report', 'We report ' + literal + '.', literal)
    text = check_numeric_claim(raw, sources)['summary']
    assert f'原文「{literal}」' in text


def test_neutral_change_prefix_and_spaced_dataset_are_rendered_once():
    raw, sources = dataset_report()
    raw['summary'] = '在 Mip-NeRF 360 上 SSIM 变化为⟦数值2⟧，表示规模变化为⟦数值1⟧。'
    text = check_numeric_claim(raw, sources)['summary']
    assert '上 SSIM仅下降0.007，表示规模从782MB到45MB。' in text
    assert text.count('SSIM') == text.count('Mip-NeRF 360') == 1


def test_neutral_change_cannot_change_the_verified_metric():
    raw, sources = dataset_report()
    raw['summary'] = 'Mip-NeRF 360上⟦数值1⟧，LPIPS变化为⟦数值2⟧。'
    with pytest.raises(ValueError, match='指标或变化方向'):
        check_numeric_claim(raw, sources)


@pytest.mark.parametrize('prefix,expected', [
    ('渲染速度为', '渲染速度为超过200 FPS（复杂场景）'),
    ('复杂场景渲染速度为', '复杂场景渲染速度为超过200 FPS'),
])
def test_exact_complex_scene_condition_is_preserved_without_duplication(prefix, expected):
    literal = 'over 200 FPS on complex scenes'
    raw, sources = literal_claim('author_report', 'We report ' + literal + '.', literal)
    raw['summary'] = prefix + '⟦数值1⟧。'
    before = deepcopy((raw, sources))
    assert expected + '。' in check_numeric_claim(raw, sources)['summary']
    assert (raw, sources) == before


def test_complex_scene_report_cannot_change_the_comparator():
    literal = 'over 200 FPS on complex scenes'
    raw, sources = literal_claim('author_report', 'We report ' + literal + '.', literal)
    raw['summary'] = '复杂场景至少⟦数值1⟧。'
    with pytest.raises(ValueError, match='数量上下界'):
        check_numeric_claim(raw, sources)
