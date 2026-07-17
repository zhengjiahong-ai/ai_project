"""Adversarial self-verification — agent plays "devil's advocate" reviewer.

After reaching conclusions, the agent generates counter-arguments, identifies
weaknesses, and adjusts confidence accordingly.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

LLM_TIMEOUT = 30
REVIEW_ASPECTS = [
    "single_source_risk",
    "sample_size_concern",
    "confounding_variable",
    "alternative_explanation",
    "methodology_limitation",
    "generalizability_concern",
    "publication_bias_risk",
    "temporal_validity",
]


# ── Public API ───────────────────────────────────────────────────────────────

def adversarial_review(
    question: str,
    findings: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate adversarial counter-arguments and adjust confidence.

    Returns ``{status, findings, counterArguments, adjustedConfidence, shouldSeekMoreEvidence, error}``.
    """
    if not findings:
        return _error("At least one finding is required.")

    evidence = evidence_items or []
    conflicts_list = conflicts or []  # noqa: F841
    reviewed: list[dict[str, Any]] = []
    all_counters: list[dict[str, Any]] = []
    total_adjusted = 0.0
    seek_more = False

    for finding in findings[:10]:
        summary = finding.get("summary", "")[:300]
        verdict = finding.get("verdict", "INCORRECT")
        sources = finding.get("sources") or []
        source_count = len(sources)

        # Rule-based checks
        counters = []
        if source_count <= 1:
            counters.append({
                "aspect": "single_source_risk",
                "severity": "high",
                "argument": "该结论仅基于单一来源，可能不具代表性。",
            })
        if source_count <= 2:
            counters.append({
                "aspect": "alternative_explanation",
                "severity": "medium",
                "argument": "有限来源数量下，可能存在未考虑的替代解释。",
            })

        # LLM deep review
        llm_counters = _llm_review(question, summary, sources, evidence[:5])
        counters.extend(llm_counters)

        # Calculate confidence adjustment
        adjustment = _calculate_adjustment(counters, verdict)
        confidence = finding.get("judgeScore", 70) / 100.0
        adjusted = max(0.1, min(0.95, confidence - adjustment))
        total_adjusted += adjusted

        reviewed.append({
            "subQuestion": finding.get("subQuestion", "")[:120],
            "originalConfidence": round(confidence, 2),
            "adjustedConfidence": round(adjusted, 2),
            "adjustment": round(adjustment, 2),
            "counterArguments": counters,
        })
        all_counters.extend(counters)

        if adjusted < 0.5:
            seek_more = True

    return {
        "status": "success",
        "question": question[:200],
        "reviewedFindings": reviewed,
        "counterArguments": all_counters[:15],
        "counterCount": len(all_counters),
        "overallConfidence": round(total_adjusted / max(len(reviewed), 1), 2),
        "shouldSeekMoreEvidence": seek_more,
        "error": "",
    }


# ── LLM review ───────────────────────────────────────────────────────────────

def _llm_review(
    question: str, summary: str, sources: list[dict[str, Any]], evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        from llm.client import get_llm

        src_str = "\n".join(
            f"- {s.get('sourceId','?')}: {(s.get('text') or '')[:150]}" for s in sources[:3]
        ) or "无详细来源"
        prompt = (
            f"研究问题：{question}\n"
            f"当前结论：{summary}\n"
            f"支持证据：\n{src_str}\n\n"
            "你是一位严格的同行评审人。请找出这个结论可能存在的 2-3 个弱点：\n"
            "- 是否依赖单一论文或单一方法？\n"
            "- 样本量和统计方法是否充分？\n"
            "- 是否存在未考虑的混淆变量？\n"
            "- 结论是否可以被其他解释替代？\n"
            "- 方法论是否有局限？\n"
            "用 JSON 数组回复：[{\"aspect\": \"...\", \"severity\": \"high|medium|low\", "
            "\"argument\": \"具体的批判意见\"}]"
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            raw = future.result(timeout=LLM_TIMEOUT)
        data = json.loads(raw.strip().split("```json")[-1].split("```")[0].strip())
        return [
            {
                "aspect": str(c.get("aspect", "methodology_limitation"))[:60],
                "severity": str(c.get("severity", "medium"))[:10],
                "argument": str(c.get("argument", ""))[:300],
            }
            for c in data if isinstance(c, dict) and c.get("argument")
        ][:3]
    except Exception:
        return []


def _calculate_adjustment(counters: list[dict[str, Any]], verdict: str) -> float:
    severity_map = {"high": 0.18, "medium": 0.10, "low": 0.04}
    base = sum(severity_map.get(c.get("severity", "medium"), 0.08) for c in counters)
    return min(base, 0.40)


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "question": "", "reviewedFindings": [], "counterArguments": [],
            "counterCount": 0, "overallConfidence": 0.0, "shouldSeekMoreEvidence": False, "error": message}
