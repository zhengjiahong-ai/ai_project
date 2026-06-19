import re
from typing import Any, Dict, List

from services.evidence_service import normalize_evidence_items
from services.knowledge_graph_store import enrich_conflicts_with_graph_context


MAX_RESEARCH_CONFLICTS = 5


def build_research_report(
    question: str,
    brief: str,
    plan_items: List[Any],
    findings: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]] | None = None,
) -> str:
    lines = [
        "## 研究 brief",
        brief,
        "",
        "## 子问题结论",
    ]

    for index, finding in enumerate(findings, start=1):
        lines.extend([
            f"### {index}. {finding.get('subQuestion')}",
            f"- 结论：{finding.get('summary')}",
            f"- 证据判断：{finding.get('verdict')}",
            f"- 证据来源：{', '.join(finding.get('sourceIds') or []) or '未检索到稳定证据来源'}",
        ])
        if finding.get("missingAspects"):
            lines.append(f"- 缺失点：{', '.join(finding.get('missingAspects') or [])}")
        lines.append("")

    normalized_conflicts = conflicts if isinstance(conflicts, list) else []
    if normalized_conflicts:
        lines.append("## 证据冲突/需人工核查")
        for index, conflict in enumerate(normalized_conflicts[:MAX_RESEARCH_CONFLICTS], start=1):
            source_ids = conflict.get("sourceIds") if isinstance(conflict.get("sourceIds"), list) else []
            lines.extend([
                f"### {index}. {conflict.get('claim') or conflict.get('topic') or '跨源证据冲突'}",
                f"- 类型：{conflict.get('conflictType') or 'unknown'}",
                f"- 严重度：{conflict.get('severity') or 'medium'}",
                f"- 摘要：{conflict.get('summary') or '不同来源存在需要人工核查的矛盾线索。'}",
                f"- 冲突来源：{', '.join(str(item) for item in source_ids if item) or '未绑定稳定来源'}",
            ])
            graph_context = conflict.get("graphContext") if isinstance(conflict.get("graphContext"), dict) else {}
            if graph_context:
                lines.append(
                    f"- 图谱上下文：{graph_context.get('status') or 'unavailable'}，"
                    f"命中 {len(graph_context.get('nodes') or [])} 个节点；本冲突未自动裁决，仍需人工核查。"
                )
            lines.append("")

    lines.extend([
        "## 综合判断",
        overall_assessment(question, findings, planned_count=len(plan_items)),
        "",
        "## 证据不足与后续建议",
        next_steps(findings),
    ])
    return "\n".join(line for line in lines if line is not None).strip()


def detect_research_conflicts(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence_items = collect_conflict_evidence(findings)
    conflicts: List[Dict[str, Any]] = []
    seen = set()

    numeric_claims = []
    for item in evidence_items:
        numeric_claims.extend(extract_numeric_claims(item))

    by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for claim in numeric_claims:
        by_topic.setdefault(str(claim.get("topic") or ""), []).append(claim)

    for topic, claims in by_topic.items():
        if not topic or len(claims) < 2:
            continue
        for left_index, left in enumerate(claims):
            for right in claims[left_index + 1:]:
                if left.get("sourceId") == right.get("sourceId"):
                    continue
                left_value = coerce_float(left.get("value"), 0.0)
                right_value = coerce_float(right.get("value"), 0.0)
                if abs(left_value - right_value) < 0.1:
                    continue
                key = ("numeric_mismatch", topic, tuple(sorted([str(left.get("sourceId")), str(right.get("sourceId"))])))
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(build_numeric_conflict(len(conflicts) + 1, topic, left, right))
                if len(conflicts) >= MAX_RESEARCH_CONFLICTS:
                    return conflicts

    polarized = [item for item in evidence_items if evidence_polarity(item.get("text"))]
    for left_index, left in enumerate(polarized):
        for right in polarized[left_index + 1:]:
            if left.get("sourceId") == right.get("sourceId"):
                continue
            left_polarity = evidence_polarity(left.get("text"))
            right_polarity = evidence_polarity(right.get("text"))
            if left_polarity == right_polarity:
                continue
            topic = shared_conflict_topic(left.get("text"), right.get("text"))
            if not topic:
                continue
            key = ("opposing_conclusion", topic, tuple(sorted([str(left.get("sourceId")), str(right.get("sourceId"))])))
            if key in seen:
                continue
            seen.add(key)
            conflicts.append(build_opposing_conflict(len(conflicts) + 1, topic, left, right))
            if len(conflicts) >= MAX_RESEARCH_CONFLICTS:
                return conflicts

    return conflicts


def enrich_research_conflicts(conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return enrich_conflicts_with_graph_context(conflicts)


def build_judge_trace_summary(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    scores = [
        item.get("judgeScore")
        for item in findings
        if isinstance(item.get("judgeScore"), int)
    ]
    return {
        "averageJudgeScore": round(sum(scores) / len(scores), 1) if scores else None,
        "retryFindingCount": sum(1 for item in findings if clean_text(item.get("retryReason"))),
        "insufficientFindingCount": sum(1 for item in findings if str(item.get("verdict") or "") == "INCORRECT"),
    }


def collect_conflict_evidence(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    seen = set()
    for finding in findings or []:
        sources = finding.get("sources") if isinstance(finding, dict) else []
        for item in normalize_evidence_items(sources, max_text_chars=700):
            source_id = str(item.get("sourceId") or "")
            text = clean_text(item.get("text"))
            if not source_id or not text:
                continue
            key = (source_id, text[:180])
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)
    return collected


def extract_numeric_claims(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = str(item.get("text") or "")
    claims = []
    pattern = r"(?P<metric>accuracy|acc|f1|precision|recall|auc|bleu|rouge|map|ndcg|score|准确率|精度|召回率|得分|指标)[^。\n.;,，]{0,48}?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|分|倍)?"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        topic = normalize_conflict_topic(match.group("metric"))
        if not topic:
            continue
        claims.append({
            "topic": topic,
            "value": float(match.group("value")),
            "unit": "%" if (match.group("unit") or "").lower() in {"%", "percent"} else (match.group("unit") or ""),
            "sourceId": item.get("sourceId"),
            "source": item,
        })
    return claims


def build_numeric_conflict(index: int, topic: str, left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_value = format_conflict_value(left)
    right_value = format_conflict_value(right)
    left_source = left.get("source") if isinstance(left.get("source"), dict) else {}
    right_source = right.get("source") if isinstance(right.get("source"), dict) else {}
    source_ids = [str(left_source.get("sourceId") or ""), str(right_source.get("sourceId") or "")]
    return {
        "id": f"conflict-{index}",
        "topic": topic,
        "claim": f"{topic} 相关数值存在差异",
        "conflictType": "numeric_mismatch",
        "severity": "high" if abs(coerce_float(left.get("value"), 0.0) - coerce_float(right.get("value"), 0.0)) >= 2 else "medium",
        "summary": f"不同来源对 {topic} 给出 {left_value} 与 {right_value}，需要人工核查实验设置、数据集或指标定义是否一致。",
        "sourceIds": [item for item in source_ids if item],
        "sources": [left_source, right_source],
    }


def build_opposing_conflict(index: int, topic: str, left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    source_ids = [str(left.get("sourceId") or ""), str(right.get("sourceId") or "")]
    return {
        "id": f"conflict-{index}",
        "topic": topic,
        "claim": f"{topic} 相关结论存在相反表述",
        "conflictType": "opposing_conclusion",
        "severity": "medium",
        "summary": f"不同来源围绕 {topic} 出现正反结论，需要人工核查上下文、实验条件和适用范围。",
        "sourceIds": [item for item in source_ids if item],
        "sources": [left, right],
    }


def format_conflict_value(claim: Dict[str, Any]) -> str:
    value = coerce_float(claim.get("value"), 0.0)
    formatted = str(int(value)) if value.is_integer() else f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{formatted}{claim.get('unit') or ''}"


def normalize_conflict_topic(value: Any) -> str:
    text = clean_text(value).lower()
    aliases = {
        "acc": "accuracy",
        "准确率": "accuracy",
        "精度": "precision",
        "召回率": "recall",
        "得分": "score",
        "指标": "score",
    }
    return aliases.get(text, text)


def evidence_polarity(text: Any) -> str:
    value = str(text or "").lower()
    negative_patterns = [
        "no improvement",
        "not improve",
        "does not improve",
        "fails to improve",
        "worse",
        "decrease",
        "降低",
        "没有提升",
        "无提升",
        "不显著",
    ]
    positive_patterns = [
        "improves",
        "improved",
        "improvement",
        "outperforms",
        "better",
        "increase",
        "提升",
        "显著提升",
        "优于",
    ]
    if any(pattern in value for pattern in negative_patterns):
        return "negative"
    if any(pattern in value for pattern in positive_patterns):
        return "positive"
    return ""


def shared_conflict_topic(left_text: Any, right_text: Any) -> str:
    left_keywords = set(extract_conflict_keywords(left_text))
    right_keywords = set(extract_conflict_keywords(right_text))
    shared = [item for item in left_keywords.intersection(right_keywords) if item]
    if not shared:
        return ""
    return sorted(shared)[0]


def extract_conflict_keywords(text: Any) -> List[str]:
    value = str(text or "").lower()
    aliases = {
        "retrieval": "retrieval",
        "accuracy": "accuracy",
        "method": "method",
        "quality": "quality",
        "performance": "performance",
        "效果": "performance",
        "方法": "method",
        "检索": "retrieval",
    }
    found = []
    for token, normalized in aliases.items():
        if token in value and normalized not in found:
            found.append(normalized)
    return found


def overall_assessment(question: str, findings: List[Dict[str, Any]], planned_count: int) -> str:
    supported = [item for item in findings if str(item.get("verdict") or "") == "CORRECT"]
    partial = [item for item in findings if str(item.get("verdict") or "") == "AMBIGUOUS"]
    insufficient = [item for item in findings if str(item.get("verdict") or "") == "INCORRECT"]
    return (
        f"围绕“{question}”，本次任务共规划 {planned_count} 个子问题，"
        f"其中证据充足 {len(supported)} 项，部分相关 {len(partial)} 项，证据不足 {len(insufficient)} 项。"
        " 当前结论优先依据当前论文，必要时参考了内部文献库补充线索；对证据不足的部分不应当作论文已经证明的事实。"
    )


def next_steps(findings: List[Dict[str, Any]]) -> str:
    missing_lines = []
    for finding in findings:
        missing = normalize_missing_aspects(finding.get("missingAspects"))
        if not missing:
            continue
        missing_lines.append(f"- {finding.get('subQuestion')}：优先补查 {', '.join(missing[:3])}")

    if not missing_lines:
        return "- 当前主要子问题都已形成可追溯结论；后续可在模块 8B 中直接展示这些 findings 与报告。"

    missing_lines.append("- 如果后续需要更完整的研究报告，可在模块 8B 增加任务面板并展示逐项 findings。")
    return "\n".join(missing_lines)


def normalize_missing_aspects(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items = []
    seen = set()
    for raw_item in value:
        text = clean_text(raw_item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text[:80])
        if len(items) >= 5:
            break
    return items


def coerce_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())
