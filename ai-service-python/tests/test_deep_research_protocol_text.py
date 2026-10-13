from copy import deepcopy

import pytest

from services.deep_research.protocol_text import render_execution_spec


def data_spec():
    return {'dataset': 'Example dataset', 'scenes': {'mode': 'named', 'names': ['scene-a', 'scene-b']},
        'split': {'mode': 'every_nth', 'order': '文件名字典序', 'stride': 8, 'offset': 0},
        'seeds': [3, 7], 'independentUnit': '场景', 'replication': {'mode': 'fixed_checkpoint'}}


def analysis_spec():
    return {'effects': {'条件效应': 'L10 - L00', '交互效应': 'L11 - L10 - L01 + L00'},
        'uncertainty': {'mode': 'paired_cluster_bootstrap', 'unit': '场景',
                        'repetitions': 999, 'confidence': 0.95, 'seed': 7},
        'decision': {'mode': 'interval_excludes_zero'}}


def test_data_fields_are_visible_without_changing_choices():
    spec = data_spec()
    text = render_execution_spec('data', spec)
    for expected in ['Example dataset', 'scene-a、scene-b', '文件名字典序', '编号除以8的余数为0',
                     '其余为训练集', '3、7', '场景', '固定检查点', '尚未执行']:
        assert expected in text
    assert 'analysis' not in text and 'executionSpec' not in text


def test_sorted_selection_does_not_silently_reduce_unverified_scene_count():
    spec = data_spec()
    spec['scenes'] = {'mode': 'sorted_first', 'count': 5, 'order': '场景名称字典序'}
    text = render_execution_spec('data', spec)
    assert '前5个' in text and '场景名称字典序' in text
    assert '前2个' not in text  # Feasibility is reviewed separately, not fabricated.


def test_explicit_split_and_retraining_per_seed():
    spec = data_spec()
    spec['split'] = {'mode': 'explicit', 'train': ['view-a', 'view-b'], 'evaluation': ['view-c']}
    spec['replication'] = {'mode': 'retrained_per_seed'}
    text = render_execution_spec('data', spec)
    assert 'view-a、view-b' in text and 'view-c' in text
    assert '每个种子重新训练基线' in text


def test_seeded_fraction_retains_fraction_and_distinct_split_seed():
    spec = data_spec()
    spec['split'] = {'mode': 'seeded_fraction', 'evaluationFraction': 0.125, 'seed': 19}
    text = render_execution_spec('data', spec)
    assert '12.5%' in text and '种子19' in text and '3、7' in text


def test_analysis_is_a_separate_role_and_preserves_every_formula():
    spec = analysis_spec()
    text = render_execution_spec('analysis', spec)
    for expected in [*spec['effects'].values(), '999', '95%', '种子7', '场景', '不能证明独立或等价']:
        assert expected in text
    assert '数据集' not in text and 'executionSpec' not in text
    assert text.index('L10 - L00') < text.index('L11 - L10 - L01 + L00')


def test_confidence_is_not_rounded_to_certainty():
    spec = analysis_spec()
    spec['uncertainty']['confidence'] = 0.999999999
    text = render_execution_spec('analysis', spec)
    assert '99.9999999%' in text and '100%' not in text


def test_analytic_uncertainty_and_equivalence_tolerances():
    spec = analysis_spec()
    spec['uncertainty'] = {'mode': 'analytic', 'method': '配对t区间',
                           'assumptions': ['场景独立', '效应分布近似正态'], 'confidence': 0.90}
    spec['decision'] = {'mode': 'equivalence', 'tolerances': {'PSNR': 0.1, 'LPIPS': 0.005}}
    text = render_execution_spec('analysis', spec)
    for expected in ['配对t区间', '场景独立', '近似正态', '90%', 'PSNR ±0.1', 'LPIPS ±0.005', '完整不确定区间']:
        assert expected in text


def test_descriptive_boundary_does_not_invent_confidence_intervals():
    spec = analysis_spec()
    spec['uncertainty'] = {'mode': 'descriptive', 'boundary': '仅描述这一个场景'}
    spec['decision'] = {'mode': 'descriptive', 'boundary': '不作总体推断'}
    text = render_execution_spec('analysis', spec)
    assert '仅描述这一个场景' in text and '不作总体推断' in text
    assert '95%' not in text and '自助法' not in text


@pytest.mark.parametrize('role,spec', [('data', None), ('analysis', True), ('data', []),
    ('analysis', {}), ('researcher', data_spec()), ([], data_spec()), (None, analysis_spec())])
def test_invalid_or_unsupported_input_returns_empty(role, spec):
    assert render_execution_spec(role, spec) == ''


def test_invalid_numeric_fields_are_not_rendered():
    spec = data_spec()
    spec['split']['stride'] = True
    assert render_execution_spec('data', spec) == ''
    spec = analysis_spec()
    spec['uncertainty']['confidence'] = float('nan')
    assert render_execution_spec('analysis', spec) == ''


@pytest.mark.parametrize('role,spec', [('data', data_spec()), ('analysis', analysis_spec())])
def test_input_not_mutated(role, spec):
    before = deepcopy(spec)
    render_execution_spec(role, spec)
    assert spec == before
