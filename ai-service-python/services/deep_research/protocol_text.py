"""Faithfully render proposed settings; scientific validity is checked separately."""
from decimal import Decimal

from services.deep_research.execution_spec import execution_spec_errors


def _pct(fraction):
    # Avoid rounding 0.99999999 to an apparent 100% confidence level.
    return format((Decimal(str(fraction)) * Decimal(100)).normalize(), 'f') + '%'


def render_execution_spec(role, spec):
    if role == 'groups':
        from services.deep_research.group_spec import render_group_spec
        return render_group_spec(spec)
    if role not in ('data', 'analysis') or execution_spec_errors(role, spec):
        return ''
    return _render_data(spec) if role == 'data' else _render_analysis(spec)


def _render_data(spec):
    lines = ['拟议配置（尚未执行）：']
    lines.append(f"数据集：{spec['dataset']}")

    sc = spec["scenes"]
    if sc['mode'] == 'all':
        lines.append(f"场景选择：使用上述数据范围内的全部{sc['count']}个场景")
    elif sc["mode"] == "named":
        lines.append(f"场景选择：指定场景 {'、'.join(sc['names'])}")
    else:
        lines.append(f"场景选择：按{sc['order']}排序后取前{sc['count']}个")

    sp = spec["split"]
    if sp["mode"] == "every_nth":
        lines.append(
            f"数据划分：按{sp['order']}排列，"
            f"样本从0开始编号，编号除以{sp['stride']}的余数为{sp['offset']}时划入评估集，其余为训练集"
        )
    elif sp["mode"] == "explicit":
        lines.append(
            f"数据划分：训练集 {'、'.join(sp['train'])}；"
            f"评估集 {'、'.join(sp['evaluation'])}"
        )
    else:
        lines.append(
            f"数据划分：以种子{sp['seed']}随机划分，评估比例{_pct(sp['evaluationFraction'])}"
        )

    lines.append(f"随机种子：{'、'.join(str(s) for s in spec['seeds'])}")
    lines.append(f"独立单元：{spec['independentUnit']}")

    rp = spec["replication"]
    if rp["mode"] == "fixed_checkpoint":
        lines.append("基线：使用固定检查点")
    else:
        lines.append("基线：每个种子重新训练基线")

    return lines[0] + '\n\n' + '\n'.join('- ' + line for line in lines[1:])


def _render_analysis(spec):
    lines = ['拟议配置（尚未执行）：', '']
    if spec["effects"]:
        lines.extend(["效应定义：", ""])
        for label, formula in spec["effects"].items():
            names = {"A_cond_B0": "B=0时A的条件效应", "A_cond_B1": "B=1时A的条件效应",
                     "B_cond_A0": "A=0时B的条件效应", "B_cond_A1": "A=1时B的条件效应",
                     "A_main": "A的平均主效应", "B_main": "B的平均主效应"}
            lines.append(f"- {names.get(label, label)}：{formula}")

    lines.append("")
    unc = spec["uncertainty"]
    if unc["mode"] == "descriptive":
        lines.append(f"不确定性：描述性分析，边界为{unc['boundary']}")
    elif unc["mode"] == "paired_cluster_bootstrap":
        lines.append(
            f"不确定性：配对聚类自助法，聚类单元{unc['unit']}，"
            f"重复{unc['repetitions']}次，置信水平{_pct(unc['confidence'])}，种子{unc['seed']}"
        )
    else:
        lines.append(
            f"不确定性：解析方法「{unc['method']}」，"
            f"置信水平{_pct(unc['confidence'])}，假设：{'；'.join(unc['assumptions'])}"
        )

    lines.append("")
    dec = spec["decision"]
    if dec["mode"] == "descriptive":
        lines.append(f"判定逻辑：描述性判断，边界为{dec['boundary']}")
    elif dec["mode"] == "interval_excludes_zero":
        lines.append(
            "判定逻辑：置信区间不包含零时，按预定置信水平拒绝零效应假设；"
            "区间包含零时不能证明独立或等价"
        )
    else:
        parts = [f"{m} ±{v}" for m, v in dec["tolerances"].items()]
        lines.append(
            f"判定逻辑：等价性判定，要求完整不确定区间落在容差内"
            f"（{'；'.join(parts)}）；不预设结论"
        )

    return '\n'.join(lines)
