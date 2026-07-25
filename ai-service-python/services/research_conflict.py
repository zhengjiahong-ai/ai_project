"""Research conflict detection and evidence comparison."""

import re
from typing import Any


def _detect_research_conflicts(findings):
    from services.research_task_service import MAX_RESEARCH_CONFLICTS, _coerce_float

    evidence_items = _collect_conflict_evidence(findings)
    conflicts: list[dict[str, Any]] = []
    seen = set()

    numeric_claims = []
    for item in evidence_items:
        numeric_claims.extend(_extract_numeric_claims(item))

    by_topic: dict[str, list[dict[str, Any]]] = {}
    for claim in numeric_claims:
        by_topic.setdefault(str(claim.get("topic") or ""), []).append(claim)

    for topic, claims in by_topic.items():
        if not topic or len(claims) < 2:
            continue
        for left_index, left in enumerate(claims):
            for right in claims[left_index + 1:]:
                if left.get("sourceId") == right.get("sourceId"):
                    continue
                left_value = _coerce_float(left.get("value"), 0.0)
                right_value = _coerce_float(right.get("value"), 0.0)
                if abs(left_value - right_value) < 0.1:
                    continue
                key = ("numeric_mismatch", topic, tuple(sorted([str(left.get("sourceId")), str(right.get("sourceId"))])))
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(_build_numeric_conflict(len(conflicts) + 1, topic, left, right))
                if len(conflicts) >= MAX_RESEARCH_CONFLICTS:
                    return conflicts

    polarized = [item for item in evidence_items if _evidence_polarity(item.get("text"))]
    for left_index, left in enumerate(polarized):
        for right in polarized[left_index + 1:]:
            if left.get("sourceId") == right.get("sourceId"):
                continue
            left_polarity = _evidence_polarity(left.get("text"))
            right_polarity = _evidence_polarity(right.get("text"))
            if left_polarity == right_polarity:
                continue
            topic = _shared_conflict_topic(left.get("text"), right.get("text"))
            if not topic:
                continue
            key = ("opposing_conclusion", topic, tuple(sorted([str(left.get("sourceId")), str(right.get("sourceId"))])))
            if key in seen:
                continue
            seen.add(key)
            conflicts.append(_build_opposing_conflict(len(conflicts) + 1, topic, left, right))
            if len(conflicts) >= MAX_RESEARCH_CONFLICTS:
                return conflicts

    return conflicts


def _collect_conflict_evidence(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from services.evidence_service import normalize_evidence_items
    from services.research_task_service import _clean_text

    collected: list[dict[str, Any]] = []
    seen = set()
    for finding in findings or []:
        sources = finding.get("sources") if isinstance(finding, dict) else []
        for item in normalize_evidence_items(sources, max_text_chars=700):
            source_id = str(item.get("sourceId") or "")
            text = _clean_text(item.get("text"))
            if not source_id or not text:
                continue
            key = (source_id, text[:180])
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)
    return collected


def _extract_numeric_claims(item: dict[str, Any]) -> list[dict[str, Any]]:
    text = str(item.get("text") or "")
    claims = []
    pattern = r"(?P<metric>accuracy|acc|f1|precision|recall|auc|bleu|rouge|map|ndcg|score|准确率|精度|召回率|得分|指标)[^。\n.;,，]{0,48}?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|分|倍)?"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        topic = _normalize_conflict_topic(match.group("metric"))
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


def _build_numeric_conflict(index: int, topic: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    from services.research_task_service import _coerce_float

    left_value = _format_conflict_value(left)
    right_value = _format_conflict_value(right)
    left_source = left.get("source") if isinstance(left.get("source"), dict) else {}
    right_source = right.get("source") if isinstance(right.get("source"), dict) else {}
    source_ids = [str(left_source.get("sourceId") or ""), str(right_source.get("sourceId") or "")]
    return {
        "id": f"conflict-{index}",
        "topic": topic,
        "claim": f"{topic} 相关数值存在差异",
        "conflictType": "numeric_mismatch",
        "severity": "high" if abs(_coerce_float(left.get("value"), 0.0) - _coerce_float(right.get("value"), 0.0)) >= 2 else "medium",
        "summary": f"不同来源对 {topic} 给出 {left_value} 与 {right_value}，需要人工核查实验设置、数据集或指标定义是否一致。",
        "sourceIds": [item for item in source_ids if item],
        "sources": [left_source, right_source],
    }


def _build_opposing_conflict(index: int, topic: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
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


def _format_conflict_value(claim: dict[str, Any]) -> str:
    from services.research_task_service import _coerce_float

    value = _coerce_float(claim.get("value"), 0.0)
    formatted = str(int(value)) if value.is_integer() else f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{formatted}{claim.get('unit') or ''}"


def _normalize_conflict_topic(value: Any) -> str:
    from services.research_task_service import _clean_text

    text = _clean_text(value).lower()
    aliases = {
        "acc": "accuracy",
        "准确率": "accuracy",
        "精度": "precision",
        "召回率": "recall",
        "得分": "score",
        "指标": "score",
    }
    return aliases.get(text, text)


def _evidence_polarity(text: Any) -> str:
    value = str(text or "").lower()
    negative_patterns = [
        "no improvement", "not improve", "does not improve", "failed to improve",
        "decrease", "decreased", "worse", "negative", "unsupported",
        "没有提升", "未提升", "无提升", "下降", "降低", "无效", "不支持",
    ]
    positive_patterns = [
        "significantly improves", "improves", "improved", "improvement", "increase", "increased",
        "effective", "supports", "supported", "positive",
        "显著提升", "提升", "提高", "有效", "支持",
    ]
    if any(pattern in value for pattern in negative_patterns):
        return "negative"
    if any(pattern in value for pattern in positive_patterns):
        return "positive"
    return ""


def _shared_conflict_topic(left: Any, right: Any) -> str:
    left_terms = _extract_conflict_terms(left)
    right_terms = _extract_conflict_terms(right)
    shared = [term for term in left_terms if term in right_terms]
    return shared[0] if shared else ""


def _extract_conflict_terms(text: Any) -> list[str]:
    value = str(text or "").lower()
    stopwords = {
        "the", "and", "for", "with", "that", "this", "shows", "show", "method",
        "proposed", "significantly", "improves", "improvement", "quality", "replication",
        "没有", "提升", "显著", "方法", "复现实验", "显示",
    }
    terms = []
    seen = set()
    for token in re.findall(r"[a-z][a-z0-9_-]{2,}", value):
        if token in stopwords:
            continue
        if token not in seen:
            seen.add(token)
            terms.append(token)
    for segment in re.findall(r"[一-鿿]{2,}", value):
        if segment in stopwords:
            continue
        if segment not in seen:
            seen.add(segment)
            terms.append(segment)
    return terms[:12]


def _build_research_review_risks(findings: list[dict[str, Any]], conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from services.research_task_service import _clean_text, _normalize_missing_aspects

    risks = [{"riskId": f"conflict:{item.get('id') or index}", "type": "conflict", "label": "证据冲突", "detail": _clean_text(item.get("claim") or item.get("summary")), "sourceIds": list(item.get("sourceIds") or []), "reviewStatus": "pending"} for index, item in enumerate(conflicts, 1)]
    for index, finding in enumerate(findings, 1):
        missing = _normalize_missing_aspects(finding.get("missingAspects"))
        if missing:
            risks.append({"riskId": f"missing:{finding.get('id') or index}", "type": "missing_evidence", "label": "缺失证据", "detail": "、".join(missing), "sourceIds": list(finding.get("sourceIds") or []), "reviewStatus": "pending"})
    return risks


def _validate_risk_reviews(risks: list[dict[str, Any]], reviews: list[Any]) -> list[dict[str, Any]]:
    from services.research_task_service import _clean_text

    allowed = {str(item.get("riskId") or "") for item in risks}
    normalized = []
    for item in reviews:
        risk_id = _clean_text(getattr(item, "riskId", ""))
        status = _clean_text(getattr(item, "reviewStatus", ""))
        if risk_id not in allowed or status not in {"reviewed", "needs_follow_up"}:
            raise ValueError("Invalid risk review.")
        normalized.append({"riskId": risk_id, "reviewStatus": status})
    return normalized


def _overall_assessment(question: str, findings: list[dict[str, Any]], planned_count: int) -> str:
    supported = [item for item in findings if item.get("verdict") == "CORRECT"]
    partial = [item for item in findings if item.get("verdict") == "AMBIGUOUS"]
    insufficient = [item for item in findings if item.get("verdict") == "INCORRECT"]
    return (
        f"围绕'{question}'，本次任务共规划 {planned_count} 个子问题，"
        f"其中证据充足 {len(supported)} 项，部分相关 {len(partial)} 项，证据不足 {len(insufficient)} 项。"
        " 当前结论优先依据当前论文，必要时参考了内部文献库补充线索；对证据不足的部分不应当作论文已经证明的事实。"
    )


def _next_steps(findings: list[dict[str, Any]]) -> str:
    from services.research_task_service import _normalize_missing_aspects

    missing_lines = []
    for finding in findings:
        missing = _normalize_missing_aspects(finding.get("missingAspects"))
        if not missing:
            continue
        missing_lines.append(f"- {finding.get('subQuestion')}：优先补查 {', '.join(missing[:3])}")

    if not missing_lines:
        return "- 当前主要子问题都已形成可追溯结论；后续可在模块 8B 中直接展示这些 findings 与报告。"

    missing_lines.append("- 如果后续需要更完整的研究报告，可在模块 8B 增加任务面板并展示逐项 findings。")
    return "\n".join(missing_lines)
