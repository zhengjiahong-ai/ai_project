"""Standalone experimental group-spec validation and rendering.

This module implements a design protocol only: it checks and renders
group specifications for experiments. It does not execute anything and
does not produce or claim paper evidence.

Public API:
    validate_group_spec(spec) -> list[str]   (empty list when valid)
    render_group_spec(spec) -> str           (empty string when invalid)
"""

from __future__ import annotations

import json
import math

__all__ = ["validate_group_spec", "render_group_spec"]

_SPEC_KEYS = frozenset({"factors"})
_FACTOR_KEYS = frozenset({"name", "control", "treatment"})
_OPERATION_KEYS = frozenset({"action", "parameters"})
_PARAMETER_KEYS = frozenset({"name", "type", "value"})
_ALLOWED_PARAM_TYPES = frozenset({"number", "choice"})


def _is_nonblank_str(value):
    return isinstance(value, str) and value.strip() != ""


def _is_finite_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        try:
            json.dumps(value)
        except (ValueError, OverflowError):
            return False
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _check_exact_keys(mapping, expected, label, errors):
    keys = set(mapping.keys())
    for key in sorted(expected - keys):
        errors.append(f"{label}: 缺少键 {key!r}")
    for key in sorted(keys - expected):
        errors.append(f"{label}: 存在多余键 {key!r}")


def _validate_parameter(param, label, errors):
    if not isinstance(param, dict):
        errors.append(f"{label}: 参数必须是对象")
        return
    _check_exact_keys(param, _PARAMETER_KEYS, label, errors)
    if not _is_nonblank_str(param.get("name")):
        errors.append(f"{label}: 参数 name 必须是非空字符串")
    ptype = param.get("type")
    if ptype not in _ALLOWED_PARAM_TYPES:
        errors.append(f"{label}: 参数 type 必须是 'number' 或 'choice'")
    elif ptype == "number":
        if not _is_finite_number(param.get("value")):
            errors.append(
                f"{label}: number 值必须是有限的非布尔 int/float，"
                "不允许符号字符串"
            )
    else:
        if not _is_nonblank_str(param.get("value")):
            errors.append(f"{label}: choice 值必须是非空字符串")


def _validate_operation(op, label, errors):
    if not isinstance(op, dict):
        errors.append(f"{label}: 操作必须是对象")
        return
    _check_exact_keys(op, _OPERATION_KEYS, label, errors)
    if not _is_nonblank_str(op.get("action")):
        errors.append(f"{label}: action 必须是非空字符串")
    parameters = op.get("parameters")
    if not isinstance(parameters, list):
        errors.append(f"{label}: parameters 必须是列表")
        return
    seen = set()
    for index, param in enumerate(parameters):
        plabel = f"{label} 参数[{index}]"
        _validate_parameter(param, plabel, errors)
        if isinstance(param, dict):
            pname = param.get("name")
            if _is_nonblank_str(pname):
                if pname in seen:
                    errors.append(f"{label}: 参数名重复 {pname!r}")
                seen.add(pname)


def _validate_factor(factor, index, errors):
    label = f"factors[{index}]"
    if not isinstance(factor, dict):
        errors.append(f"{label}: 因素必须是对象")
        return None
    _check_exact_keys(factor, _FACTOR_KEYS, label, errors)
    name = factor.get("name")
    if not _is_nonblank_str(name):
        errors.append(f"{label}: 因素 name 必须是非空字符串")
        return None
    for role in ("control", "treatment"):
        _validate_operation(factor.get(role), f"{label}.{role}", errors)
    return name


def _validate_spec(spec, errors):
    if not isinstance(spec, dict):
        errors.append("spec 必须是对象")
        return
    _check_exact_keys(spec, _SPEC_KEYS, "spec", errors)
    factors = spec.get("factors")
    if not isinstance(factors, list):
        errors.append("spec.factors 必须是列表")
        return
    if not factors:
        errors.append("spec.factors 不能为空")
        return
    seen = set()
    for index, factor in enumerate(factors):
        name = _validate_factor(factor, index, errors)
        if name is not None:
            if name in seen:
                errors.append(f"因素名重复 {name!r}")
            seen.add(name)


def validate_group_spec(spec):
    """Validate a group spec; return a list of error strings (empty if valid).

    Never raises: malformed input fails closed. Does not mutate the input.
    """
    errors = []
    try:
        _validate_spec(spec, errors)
    except Exception:
        return ["spec 校验失败（按无效处理）"]
    return errors


def _escape(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _render_operation(op, role_label, lines):
    lines.append(f"  - {role_label}操作：{_escape(op['action'])}")
    parameters = op["parameters"]
    if not parameters:
        lines.append(
            "    - 参数：未设置"
        )
        return
    lines.append("    - 参数：")
    for param in parameters:
        lines.append(
            f"      - {_escape(param['name'])}（{'数值' if param['type'] == 'number' else '选项'}）："
            f"{_escape(param['value'])}"
        )


def render_group_spec(spec):
    """Render a valid group spec as readable Chinese bullets.

    Returns an empty string when the spec is invalid. Never raises and
    never mutates the input. Rendered text describes the design only and
    makes no claims about performed results.
    """
    try:
        if validate_group_spec(spec):
            return ""
        lines = ["拟议分组（尚未执行）："]
        for factor in spec["factors"]:
            lines.append(f"- 因素：{_escape(factor['name'])}")
            _render_operation(factor["control"], "对照组", lines)
            _render_operation(factor["treatment"], "实验组", lines)
        return "\n".join(lines)
    except Exception:
        return ""
