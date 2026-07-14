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
    trace_summary: Dict[str, Any] | None = None,
) -> str:
    lines = [
        "## 研究 brief",
        brief,
        "",
        "## 子问题结论",
    ]

    for index, finding in enumerate(findings, start=1):
        coverage = finding.get("coverage") if isinstance(finding.get("coverage"), dict) else {}
        judge_score = finding.get("judgeScore")
        source_types_list = coverage.get("sourceTypes") or []
        diversity = coverage.get("sourceDiversityScore")
        trust = coverage.get("sourceTrustWeightedScore")
        cross_agreement = coverage.get("crossSourceAgreement")

        lines.extend([
            f"### {index}. {finding.get('subQuestion')}",
            f"- 结论：{finding.get('summary')}",
            f"- 证据判断：{finding.get('verdict')}",
            f"- 证据来源：{_format_source_line(finding)}",
        ])
        if judge_score is not None:
            score_parts = [f"JUDGE评分: {judge_score}/100"]
            cov_score = coverage.get("score")
            if cov_score is not None:
                score_parts.append(f"覆盖: {int(cov_score * 100)}%")
            if diversity is not None:
                score_parts.append(f"多样性: {int(diversity * 100)}%")
            if trust is not None:
                score_parts.append(f"可信度: {int(trust * 100)}%")
            lines.append(f"- {' · '.join(score_parts)}")

        if source_types_list:
            type_counts = _count_source_types(finding.get("sources") or [])
            counts_str = ", ".join(
                f"{st}({type_counts.get(st, 0)})" for st in source_types_list
            )
            lines.append(f"- 来源分布: {counts_str}")

        if cross_agreement is not None:
            lines.append(f"- 跨源一致性: {int(cross_agreement * 100)}%")
        elif source_types_list:
            lines.append("- 跨源一致性: 无法评估")

        if finding.get("missingAspects"):
            lines.append(f"- 缺失点：{', '.join(finding.get('missingAspects') or [])}")
        lines.append("")

    # P6-21: evidence collection summary
    lines.extend(_build_evidence_summary(findings))

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

    # P6-18: multi-source evidence cross-validation
    cv_result: Dict[str, Any] | None = None
    try:
        from services.evidence_cross_validator import cross_validate_evidence

        all_evidence = collect_conflict_evidence(findings)
        cv_result = cross_validate_evidence(all_evidence, use_llm=False)
        cv_claims = cv_result.get("claims") or []
        cv_summary = cv_result.get("summary") or {}
        if cv_claims:
            lines.append("## 多源证据交叉验证")
            lines.append(f"跨源验证 {cv_summary.get('total_claims', 0)} 条声明："
                         f"{cv_summary.get('confirmed', 0)} 已确认、"
                         f"{cv_summary.get('supported', 0)} 有支撑、"
                         f"{cv_summary.get('single_source', 0)} 单一来源、"
                         f"{cv_summary.get('contradicted', 0)} 矛盾。")
            lines.append("")
            for claim in cv_claims:
                level = claim.get("agreement_level", "unknown")
                label = {"confirmed": "✓", "supported": "~", "single_source": "?", "contradicted": "✗"}.get(level, "?")
                sources_str = ", ".join(claim.get("source_types", []))
                lines.append(f"- {label} [{level}] {claim.get('claim', '')[:200]} (来源: {sources_str})")
                if claim.get("needs_more_evidence"):
                    lines.append("  ⚠ 需更多证据 — 仅单一来源支持")
                if claim.get("needs_manual_review"):
                    lines.append("  ⚠ 需人工核查 — 存在矛盾声明")
            lines.append("")
    except Exception:
        pass  # cross-validation is optional; never blocks report generation

    # P6-19: source provenance
    provenance_lines = _build_provenance_section(findings)
    if provenance_lines:
        lines.extend(provenance_lines)

    lines.extend([
        "## 综合判断",
        overall_assessment(question, findings, planned_count=len(plan_items)),
        "",
        "## 证据不足与后续建议",
        next_steps(findings),
    ])

    # 3-2: executive summary (LLM-generated with rule fallback)
    exec_summary = _build_executive_summary(question, findings, normalized_conflicts)
    if exec_summary:
        lines.append(exec_summary)

    # 3-2: evidence comparison table
    comparison = _build_evidence_comparison_table(findings)
    if comparison:
        lines.append(comparison)

    # 3-2: dispute map
    dispute = _build_dispute_map(normalized_conflicts, cv_result)
    if dispute:
        lines.append(dispute)

    # 3-2: hierarchical citations
    citations = _build_hierarchical_citations(findings)
    if citations:
        lines.append(citations)

    # P6-21: execution statistics
    if isinstance(trace_summary, dict):
        lines.extend(_build_exec_stats(trace_summary))

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
        "externalSearchDegradationCount": sum(1 for item in findings if clean_text(item.get("externalSearchDegradation"))),
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
    has_external = _any_external_source(findings)
    external_clause = "，并在证据不足时参考了外部学术来源补充线索" if has_external else ""
    return (
        "围绕"" + question + ""，本次任务共规划 " + str(planned_count) + " 个子问题，"
        "其中证据充足 " + str(len(supported)) + " 项，部分相关 " + str(len(partial)) + " 项，证据不足 " + str(len(insufficient)) + " 项。"
        " 当前结论优先依据当前论文，必要时参考了内部文献库补充线索" + external_clause + "；对证据不足的部分不应当作论文已经证明的事实。"
    )


def next_steps(findings: List[Dict[str, Any]]) -> str:
    missing_lines = []
    for finding in findings:
        missing = normalize_missing_aspects(finding.get("missingAspects"))
        if missing:
            missing_lines.append(f"- {finding.get('subQuestion')}：优先补查 {', '.join(missing[:3])}")

    if any(finding.get("externalSearchDegradation") for finding in findings):
        missing_lines.append("- 外部学术补查在本次任务中受限或降级，证据缺口以内部来源为准。")

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


def _format_source_line(finding: Dict[str, Any]) -> str:
    base = ", ".join(finding.get("sourceIds") or []) or "未检索到稳定证据来源"
    has_external = any(
        isinstance(src, dict) and str(src.get("sourceType") or "") == "external_academic"
        for src in (finding.get("sources") or [])
    )
    has_web = any(
        isinstance(src, dict) and str(src.get("sourceType") or "") in ("web_search", "web_page")
        for src in (finding.get("sources") or [])
    )
    if has_external:
        base += "（含外部学术检索）"
    if has_web:
        base += "（含Web搜索）"
    degradation = finding.get("externalSearchDegradation")
    if degradation:
        base += f" [外部检索降级: {degradation}]"
    return base


def _count_source_types(sources: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for src in sources:
        if isinstance(src, dict):
            st = str(src.get("sourceType") or "unknown")
            counts[st] = counts.get(st, 0) + 1
    return counts


def _build_evidence_summary(findings: List[Dict[str, Any]]) -> List[str]:
    if not findings:
        return []
    lines = ["", "## 证据收集摘要"]
    total_evidence = 0
    all_type_counts: Dict[str, int] = {}
    diversities = []
    trusts = []
    cross_evaluable = 0

    for finding in findings:
        sources = finding.get("sources") or []
        total_evidence += len(sources)
        for src in sources:
            st = str(src.get("sourceType") or "unknown") if isinstance(src, dict) else "unknown"
            all_type_counts[st] = all_type_counts.get(st, 0) + 1
        coverage = finding.get("coverage") if isinstance(finding.get("coverage"), dict) else {}
        if coverage.get("sourceDiversityScore") is not None:
            diversities.append(coverage["sourceDiversityScore"])
        if coverage.get("sourceTrustWeightedScore") is not None:
            trusts.append(coverage["sourceTrustWeightedScore"])
        if coverage.get("crossSourceAgreement") is not None:
            cross_evaluable += 1

    lines.append(f"- 总证据条数: {total_evidence}")
    if all_type_counts:
        type_str = ", ".join(f"{k}({v})" for k, v in sorted(all_type_counts.items()))
        lines.append(f"- 来源类型分布: {type_str}")
    if diversities:
        avg_div = sum(diversities) / len(diversities)
        lines.append(f"- 平均来源多样性 (Shannon): {avg_div:.2f}")
    if trusts:
        avg_trust = sum(trusts) / len(trusts)
        lines.append(f"- 平均可信度加权: {avg_trust:.2f}")
    if findings:
        lines.append(f"- 跨源一致性可评估: {cross_evaluable}/{len(findings)} 个子问题")
    lines.append("")
    return lines


def _build_provenance_section(findings: List[Dict[str, Any]]) -> List[str]:
    provenance_items = []
    for finding in findings:
        for src in (finding.get("sources") or []):
            if not isinstance(src, dict):
                continue
            provenance = src.get("provenance")
            if not isinstance(provenance, dict):
                continue
            provenance_items.append({
                "sourceId": src.get("sourceId", ""),
                "provider": src.get("provider", ""),
                "discoveryPath": provenance.get("discoveryPath", ""),
                "searchQuery": provenance.get("searchQuery", ""),
                "searchIteration": provenance.get("searchIteration"),
                "sourceUrl": provenance.get("sourceUrl", ""),
                "retrievalTimestamp": provenance.get("retrievalTimestamp", ""),
            })

    if not provenance_items:
        return []

    seen = set()
    lines = ["", "## 来源追溯"]
    for item in provenance_items:
        key = (item["sourceId"], item["sourceUrl"])
        if key in seen:
            continue
        seen.add(key)

        parts = []
        path = item["discoveryPath"] or "unknown"
        parts.append(f"[{path}]")
        if item["provider"]:
            parts.append(item["provider"])
        if item["searchQuery"]:
            parts.append(f'查询: "{item["searchQuery"]}"')
        if isinstance(item["searchIteration"], int):
            parts.append(f"第{item['searchIteration']}轮")
        if item["sourceUrl"]:
            parts.append(item["sourceUrl"][:120])
        if item["retrievalTimestamp"]:
            parts.append(item["retrievalTimestamp"])
        lines.append(f"- {' → '.join(parts)}")
    lines.append("")
    return lines


def _build_exec_stats(trace_summary: Dict[str, Any]) -> List[str]:
    counters = trace_summary.get("counters") if isinstance(trace_summary.get("counters"), dict) else {}
    duration_ms = trace_summary.get("durationMs")

    rows = []
    stat_items = [
        ("LLM 调用", "llmCalls"),
        ("检索调用", "retrievalCalls"),
        ("外部学术搜索", "externalSearchCalls"),
        ("外部证据条数", "externalEvidenceCount"),
        ("Web 搜索", "webSearchCalls"),
        ("页面抓取", "webFetchCalls"),
        ("迭代搜索轮次", "agenticLoopIterations"),
    ]

    for label, key in stat_items:
        val = counters.get(key)
        if isinstance(val, (int, float)) and val > 0:
            rows.append((label, str(int(val))))

    # Always show LLM calls and retrieval calls even if 0
    llm_val = counters.get("llmCalls")
    if not isinstance(llm_val, (int, float)) or llm_val == 0:
        rows.insert(0, ("LLM 调用", "0"))
    ret_val = counters.get("retrievalCalls")
    if not isinstance(ret_val, (int, float)) or ret_val == 0:
        rows.insert(1, ("检索调用", "0"))

    if duration_ms is not None:
        rows.append(("总耗时", f"{duration_ms / 1000:.1f}s"))

    if not rows:
        return []

    lines = ["", "## 执行统计"]
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    for label, value in rows:
        lines.append(f"| {label} | {value} |")
    lines.append("")
    return lines


def _any_external_source(findings: List[Dict[str, Any]]) -> bool:
    return any(
        isinstance(src, dict) and str(src.get("sourceType") or "") == "external_academic"
        for finding in findings
        for src in (finding.get("sources") or [])
    )


# ── 3-2: Report depth upgrade ───────────────────────────────────────────────

def _build_hierarchical_citations(findings: List[Dict[str, Any]]) -> str:
    """Build a multi-level citation index ``[N]`` / ``[N.M]`` from findings."""
    lines: list[str] = []
    main_idx = 0
    for finding in findings:
        sources = finding.get("sources") or []
        if not sources:
            continue
        sub_q = finding.get("subQuestion", "")
        main_idx += 1
        lines.append(f"- **[{main_idx}]** {sub_q[:120]}")
        sub_idx = 0
        for src in sources:
            if not isinstance(src, dict):
                continue
            src_id = src.get("sourceId", "")
            text = (src.get("text") or "").strip()[:100]
            chunk = src.get("chunkIndex")
            if chunk is not None:
                sub_idx += 1
                lines.append(f"  - **[{main_idx}.{sub_idx}]** {src_id} (chunk {chunk}): {text}")
            else:
                lines.append(f"  - {src_id}: {text}")
    if not lines:
        return ""
    return "## 引用索引\n\n" + "\n".join(lines) + "\n"


def _build_evidence_comparison_table(findings: List[Dict[str, Any]]) -> str:
    """Build a Markdown evidence comparison table across source types."""
    source_types = ["current_paper", "library", "external_academic", "web_search", "web_page", "image_analysis"]
    type_labels = {
        "current_paper": "当前论文", "library": "内部文献库",
        "external_academic": "外部学术", "web_search": "Web搜索",
        "web_page": "网页", "image_analysis": "图片分析",
    }
    # Determine which columns actually have data
    used_types: set[str] = set()
    for finding in findings:
        for src in (finding.get("sources") or []):
            if isinstance(src, dict):
                st = str(src.get("sourceType") or "")
                if st in source_types:
                    used_types.add(st)
    ordered_types = [t for t in source_types if t in used_types]
    if not ordered_types:
        ordered_types = ["current_paper"]

    header = "| 子问题 | " + " | ".join(type_labels.get(t, t) for t in ordered_types) + " |"
    sep = "|--------|" + "|".join("------" for _ in ordered_types) + "|"
    rows = [header, sep]

    for finding in findings:
        sub_q = (finding.get("subQuestion") or "")[:60]
        by_type: dict[str, list[str]] = {}
        for src in (finding.get("sources") or []):
            if not isinstance(src, dict):
                continue
            st = str(src.get("sourceType") or "")
            text = (src.get("text") or "").strip()[:80]
            if st not in ordered_types:
                continue
            by_type.setdefault(st, []).append(text)
        cells = [sub_q] if sub_q else ["(未命名)"]
        for st in ordered_types:
            snippets = by_type.get(st, [])
            cells.append(snippets[0] if snippets else "-")
        rows.append("| " + " | ".join(cells) + " |")

    if len(rows) <= 2:
        return ""
    return "## 证据对比表\n\n" + "\n".join(rows) + "\n\n"


def _build_dispute_map(
    conflicts: List[Dict[str, Any]] | None,
    cv_result: Dict[str, Any] | None = None,
) -> str:
    """Build a dispute map with consensus / disagreement / unverified zones."""
    if not conflicts and not cv_result:
        return ""

    consensus: list[str] = []
    disagreement: list[str] = []
    unverified: list[str] = []

    # From cross-validation claims
    cv_claims = cv_result.get("claims") if isinstance(cv_result, dict) else []
    for claim in (cv_claims or []):
        level = claim.get("agreement_level", "")
        text = claim.get("claim", "")[:150]
        src_types = ", ".join(claim.get("source_types", []))
        line = f"- {text} (来源: {src_types})" if src_types else f"- {text}"
        if level in ("confirmed", "supported"):
            consensus.append(f"- [✓ {level}] {line.lstrip('- ')}")
        elif level == "contradicted":
            disagreement.append(f"- [✗ {level}] {line.lstrip('- ')}")
        else:
            unverified.append(f"- [? {level}] {line.lstrip('- ')}")

    # From conflicts
    for conflict in (conflicts or [])[:5]:
        claim = (conflict.get("claim") or conflict.get("topic") or "未命名冲突")[:120]
        severity = conflict.get("severity", "medium")
        src_ids = ", ".join(conflict.get("sourceIds") or [])
        line = f"- {claim}"
        if src_ids:
            line += f" (来源: {src_ids})"
        if severity == "high":
            line += " ⚠高严重度"
        disagreement.append(line)

    parts: list[str] = []
    if consensus:
        parts.append("### 共识区\n" + "\n".join(consensus))
    if disagreement:
        parts.append("### 分歧区\n" + "\n".join(disagreement))
    if unverified:
        parts.append("### 待验证区\n" + "\n".join(unverified))
    if not parts:
        return ""

    return "## 争议地图\n\n" + "\n\n".join(parts) + "\n\n"


def _build_executive_summary(
    question: str,
    findings: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]] | None = None,
) -> str:
    """Generate a ~500-character executive summary via LLM, falling back to rules."""
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

        from llm.client import get_llm

        finding_lines = []
        for i, f in enumerate(findings[:8], 1):
            finding_lines.append(
                f"{i}. {f.get('subQuestion', '')}: {f.get('summary', '')[:120]} "
                f"[{f.get('verdict', '?')}]"
            )
        conflict_lines = []
        for c in (conflicts or [])[:3]:
            conflict_lines.append(f"- {c.get('claim', c.get('topic', ''))[:120]}")

        prompt = (
            f"研究问题：{question}\n\n"
            f"子问题结论：\n" + "\n".join(finding_lines) + "\n\n"
            + (f"争议：\n" + "\n".join(conflict_lines) + "\n\n" if conflict_lines else "")
            + "请用中文撰写一份约500字的研究执行摘要，需包含："
            "1) 核心发现 2) 证据强度评估 3) 主要争议 4) 后续研究建议。"
            "只输出摘要正文，不加标题。"
        )

        def _call_llm():
            llm = get_llm()
            return llm._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_llm)
            result = future.result(timeout=15)
        summary = (result or "").strip()[:800]
        if len(summary) >= 80:
            return "## 执行摘要\n\n" + summary + "\n"
    except Exception:
        pass
    # Fallback: concise rule-based summary
    return "## 执行摘要\n\n" + overall_assessment(question, findings, len(findings)) + "\n"
