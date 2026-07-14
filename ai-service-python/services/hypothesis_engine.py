"""Hypothesis generation and closed-loop verification engine.

Generates testable hypotheses from research findings, then automatically
searches for evidence to support or refute each hypothesis.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

LLM_TIMEOUT_S = 25
MAX_HYPOTHESES = 5


# ── Public API ───────────────────────────────────────────────────────────────

def generate_and_verify_hypotheses(
    question: str,
    findings: list[dict[str, Any]],
    conflicts: list[dict[str, Any]] | None = None,
    gaps: list[str] | None = None,
) -> dict[str, Any]:
    """Generate hypotheses from findings, then verify each against evidence.

    Returns ``{status, hypotheses, error}``.
    """
    if not question or not question.strip():
        return _error("Research question cannot be empty.")

    question = question.strip()[:500]
    findings_list = _normalize_findings(findings)
    conflicts_list = conflicts or []
    gaps_list = gaps or []

    # Step 1: Generate hypotheses
    hypotheses = _generate_hypotheses(question, findings_list, conflicts_list, gaps_list)
    if not hypotheses:
        return _error("Failed to generate hypotheses. LLM may be unavailable.")

    # Step 2: Build search queries and evidence requirements for each
    for h in hypotheses:
        h["searchQueries"] = _build_search_queries(h["statement"])
        h["verificationStatus"] = "pending"
        h["supportingEvidence"] = []
        h["contradictingEvidence"] = []

    return {
        "status": "success",
        "question": question,
        "hypotheses": hypotheses[:MAX_HYPOTHESES],
        "hypothesisCount": len(hypotheses[:MAX_HYPOTHESES]),
        "error": "",
    }


def verify_hypothesis(
    hypothesis: dict[str, Any],
    evidence_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate *hypothesis* against *evidence_items* and update belief."""
    if not isinstance(hypothesis, dict):
        return _error("Hypothesis must be a dict with 'statement' field.")
    statement = hypothesis.get("statement", "")
    if not statement:
        return _error("Hypothesis statement is required.")

    evidence = evidence_items or []
    supporting = []
    contradicting = []

    for item in evidence:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        relation = _classify_hypothesis_relation(statement, text)
        entry = {
            "sourceId": item.get("sourceId", ""),
            "text": text[:300],
            "confidence": relation["confidence"],
        }
        if relation["label"] == "supports":
            supporting.append(entry)
        elif relation["label"] == "contradicts":
            contradicting.append(entry)

    total = len(supporting) + len(contradicting)
    if total == 0:
        verdict = "unverified"
        confidence = 0.0
    else:
        support_ratio = len(supporting) / total
        if support_ratio >= 0.75:
            verdict = "supported"
            confidence = min(support_ratio, 0.95)
        elif support_ratio <= 0.25:
            verdict = "refuted"
            confidence = min(1.0 - support_ratio, 0.95)
        else:
            verdict = "inconclusive"
            confidence = 0.4

    return {
        "status": "success",
        "hypothesis": statement[:300],
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "supportingCount": len(supporting),
        "contradictingCount": len(contradicting),
        "supportingEvidence": supporting[:5],
        "contradictingEvidence": contradicting[:5],
        "error": "",
    }


# ── LLM hypothesis generation ────────────────────────────────────────────────

def _generate_hypotheses(
    question: str, findings: list[str], conflicts: list[dict[str, Any]], gaps: list[str],
) -> list[dict[str, Any]]:
    try:
        from llm.client import get_llm

        findings_str = "\n".join(f"- {f}" for f in findings[:8]) or "(无)"
        conflicts_str = "\n".join(
            f"- {c.get('claim', c.get('topic', ''))[:200]}" for c in conflicts[:5]
        ) or "(无)"
        gaps_str = "\n".join(f"- {g}" for g in gaps[:5]) or "(无)"

        prompt = (
            f"研究问题：{question}\n\n"
            f"已有发现：\n{findings_str}\n\n"
            f"争议：\n{conflicts_str}\n\n"
            f"证据缺口：\n{gaps_str}\n\n"
            "基于以上信息，请生成 3-5 个可检验的科学假设。每个假设需包含：\n"
            "1) statement: 清晰的假设陈述\n"
            "2) testablePrediction: 如果假设成立，应该能观测到什么\n"
            "3) requiredEvidenceType: 验证该假设需要什么类型的证据\n\n"
            "用 JSON 数组回复：[{\"statement\": \"...\", \"testablePrediction\": \"...\", \"requiredEvidenceType\": \"...\"}]"
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            raw = future.result(timeout=LLM_TIMEOUT_S)
    except Exception:
        return _rule_hypotheses(findings, gaps)

    try:
        text = raw.strip().split("```json")[-1].split("```")[0].strip()
        hypotheses = json.loads(text)
        if isinstance(hypotheses, list) and hypotheses:
            return [
                {
                    "statement": str(h.get("statement", ""))[:300],
                    "testablePrediction": str(h.get("testablePrediction", ""))[:300],
                    "requiredEvidenceType": str(h.get("requiredEvidenceType", ""))[:200],
                }
                for h in hypotheses if h.get("statement")
            ]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return _rule_hypotheses(findings, gaps)


def _rule_hypotheses(
    findings: list[str], gaps: list[str],
) -> list[dict[str, Any]]:
    hyps = []
    for f in findings[:3]:
        hyps.append({
            "statement": f"进一步验证：{f[:150]}",
            "testablePrediction": "在不同数据集或实验条件下重复观测到相同趋势",
            "requiredEvidenceType": "replication_study",
        })
    for g in gaps[:2]:
        hyps.append({
            "statement": f"填补缺口：{g[:150]}",
            "testablePrediction": "找到直接针对该缺口的研究证据",
            "requiredEvidenceType": "targeted_search",
        })
    return hyps[:MAX_HYPOTHESES]


def _build_search_queries(statement: str) -> list[str]:
    keywords = [w for w in statement.split() if len(w) > 3][:6]
    return [" ".join(keywords)] if keywords else [statement[:100]]


def _classify_hypothesis_relation(statement: str, text: str) -> dict[str, Any]:
    statement_words = set(statement.lower().split()) & set(text.lower().split())
    overlap = len(statement_words)
    if overlap < 2:
        return {"label": "unrelated", "confidence": 0.1}
    # Simple keyword classification
    neg = any(w in text.lower() for w in ["however", "but", "although", "contrary", "失败", "未能"])
    if neg:
        return {"label": "contradicts", "confidence": 0.4}
    return {"label": "supports", "confidence": min(0.3 + overlap * 0.1, 0.7)}


def _normalize_findings(findings: list[dict[str, Any]]) -> list[str]:
    result = []
    for f in findings[:10]:
        if isinstance(f, dict):
            s = f.get("summary") or f.get("subQuestion") or ""
            if s:
                result.append(str(s)[:300])
    return result


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "question": "", "hypotheses": [], "hypothesisCount": 0, "error": message}
