"""Pytest tests for the standalone group_spec module."""

import copy

import pytest

from services.deep_research.group_spec import render_group_spec, validate_group_spec


def make_param(name="反馈时长秒", ptype="number", value=5):
    return {"name": name, "type": ptype, "value": value}


def make_operation(action, parameters):
    return {"action": action, "parameters": [copy.deepcopy(p) for p in parameters]}


def default_control():
    return make_operation("给予口头反馈", [make_param(value=5)])


def default_treatment():
    return make_operation(
        "给予书面反馈",
        [make_param(value=10), make_param("反馈形式", "choice", "表格")],
    )


def make_factor(name="反馈方式", control=None, treatment=None):
    return {
        "name": name,
        "control": default_control() if control is None else control,
        "treatment": default_treatment() if treatment is None else treatment,
    }


def make_spec(factors=None):
    return {"factors": [make_factor()] if factors is None else factors}


def test_valid_numeric_and_choice_spec():
    assert validate_group_spec(make_spec()) == []
    assert render_group_spec(make_spec()) != ""


def test_zero_and_negative_numeric_values_are_valid():
    spec = make_spec([make_factor(
        control=make_operation("A", [make_param(value=0)]),
        treatment=make_operation("B", [make_param(value=-3.5)]),
    )])
    assert validate_group_spec(spec) == []
    text = render_group_spec(spec)
    assert "0" in text
    assert "-3.5" in text


def test_empty_parameters_allowed():
    spec = make_spec([make_factor(
        control=make_operation("静息", []),
        treatment=make_operation("静息", []),
    )])
    assert validate_group_spec(spec) == []
    assert "参数：未设置" in render_group_spec(spec)


def test_bool_value_rejected():
    spec = make_spec([make_factor(
        control=make_operation("A", [make_param(value=True)]),
    )])
    assert validate_group_spec(spec) != []
    assert render_group_spec(spec) == ""


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_infinity_rejected(bad):
    spec = make_spec([make_factor(
        treatment=make_operation("B", [make_param(value=bad)]),
    )])
    assert validate_group_spec(spec) != []
    assert render_group_spec(spec) == ""


def test_symbolic_string_rejected_for_number():
    spec = make_spec([make_factor(
        treatment=make_operation("B", [make_param(value="x + 1")]),
    )])
    assert validate_group_spec(spec) != []


def test_blank_strings_rejected():
    mutations = (
        lambda s: s["factors"][0].__setitem__("name", "   "),
        lambda s: s["factors"][0]["control"].__setitem__("action", ""),
        lambda s: s["factors"][0]["control"]["parameters"][0].__setitem__("name", " "),
        lambda s: s["factors"][0]["treatment"]["parameters"][1].__setitem__("value", ""),
        lambda s: s["factors"][0]["treatment"]["parameters"][1].__setitem__("value", "   "),
    )
    for mutate in mutations:
        spec = make_spec()
        mutate(spec)
        assert validate_group_spec(spec) != []


def test_duplicate_factor_names_rejected():
    spec = make_spec([make_factor(name="F"), make_factor(name="F")])
    assert validate_group_spec(spec) != []


def test_duplicate_parameter_names_within_operation_rejected():
    spec = make_spec([make_factor(control=make_operation(
        "A", [make_param(name="t", value=1), make_param(name="t", value=2)],
    ))])
    assert validate_group_spec(spec) != []


def test_parameter_names_may_repeat_across_operations():
    # Default spec reuses 反馈时长秒 in control and treatment.
    assert validate_group_spec(make_spec()) == []


def test_missing_keys_rejected():
    factor = make_factor()
    del factor["treatment"]
    assert validate_group_spec(make_spec([factor])) != []

    op = make_operation("A", [])
    del op["parameters"]
    assert validate_group_spec(make_spec([make_factor(control=op)])) != []

    param = make_param()
    del param["value"]
    assert validate_group_spec(
        make_spec([make_factor(control=make_operation("A", [param]))])
    ) != []

    spec = make_spec()
    del spec["factors"]
    assert validate_group_spec(spec) != []


def test_extra_keys_rejected():
    spec = make_spec()
    spec["extra"] = 1
    assert validate_group_spec(spec) != []

    factor = make_factor()
    factor["note"] = "x"
    assert validate_group_spec(make_spec([factor])) != []

    op = make_operation("A", [make_param()])
    op["when"] = "pre"
    assert validate_group_spec(make_spec([make_factor(control=op)])) != []

    param = make_param()
    param["unit"] = "s"
    assert validate_group_spec(
        make_spec([make_factor(control=make_operation("A", [param]))])
    ) != []


def test_wrong_container_types_rejected():
    assert validate_group_spec({"factors": {"name": "F"}}) != []
    assert validate_group_spec([make_factor()]) != []
    assert validate_group_spec("spec") != []
    assert validate_group_spec(
        make_spec([make_factor(control="not-an-operation")])
    ) != []
    bad_op = {"action": "A", "parameters": {"name": "t", "type": "number", "value": 1}}
    assert validate_group_spec(make_spec([make_factor(control=bad_op)])) != []
    bad_param_op = {"action": "A", "parameters": ["not-a-dict"]}
    assert validate_group_spec(make_spec([make_factor(control=bad_param_op)])) != []


def test_empty_factors_rejected():
    assert validate_group_spec({"factors": []}) != []
    assert render_group_spec({"factors": []}) == ""


def test_huge_int_does_not_overflow():
    big = 10 ** 400
    spec = make_spec([make_factor(
        control=make_operation("A", [make_param(value=big)]),
    )])
    assert validate_group_spec(spec) == []
    assert str(big) in render_group_spec(spec)


def test_source_not_mutated():
    spec = make_spec()
    snapshot = copy.deepcopy(spec)
    validate_group_spec(spec)
    render_group_spec(spec)
    assert spec == snapshot


def test_render_contains_all_declared_values_and_roles():
    spec = make_spec()
    text = render_group_spec(spec)
    assert "对照组" in text
    assert "实验组" in text
    assert '"反馈方式"' in text
    assert '"给予口头反馈"' in text
    assert '"给予书面反馈"' in text
    assert '"反馈时长秒"' in text
    assert "5" in text
    assert "10" in text
    assert '"表格"' in text
    assert "数值" in text
    assert "选项" in text


def test_render_invalid_spec_is_empty():
    bad = make_spec()
    del bad["factors"][0]["control"]
    assert render_group_spec(bad) == ""


@pytest.mark.parametrize("garbage", [
    None, 0, 3.5, "spec", [], (), {}, {"factors": None}, object(), b"",
])
def test_fail_closed_without_exceptions(garbage):
    errors = validate_group_spec(garbage)
    assert isinstance(errors, list)
    assert errors != []
    assert render_group_spec(garbage) == ""


def test_validate_returns_fresh_error_list():
    errors = validate_group_spec(make_spec())
    errors.append("junk")
    assert validate_group_spec(make_spec()) == []
