"""
Structured evidence credibility model (14-2).

Provides a single, configurable credibility computation used by:
- ``agent_langgraph.evidence_weighing_node`` (LangGraph path)
- ``agent_evidence_collector`` (classic ``execute_run`` path)
- ``retrieval_judge_service`` (judge score weight allocation)
- ``agent_orchestrator`` (report synthesis)

Source-type trust weights are managed via ``core.config.Settings`` and can be
overridden through environment variables (e.g. ``PIXIU_CREDIBILITY_CURRENT_PAPER_WEIGHT=1.0``).
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_source_trust_weights() -> Dict[str, float]:
    """Return the current source-type → trust-weight mapping.

    Reads from the centralised ``Settings`` object so that weights can be
    tuned via environment variables without code changes.
    """
    try:
        from core.config import settings

        return {
            "current_paper": float(settings.pixiu_credibility_current_paper_weight),
            "library": float(settings.pixiu_credibility_library_weight),
            "external_academic": float(settings.pixiu_credibility_external_academic_weight),
            "web_search": float(settings.pixiu_credibility_web_search_weight),
            "web_page": float(settings.pixiu_credibility_web_page_weight),
        }
    except Exception:
        pass
    # Fallback defaults (kept in sync with core/config.py).
    return {
        "current_paper": 1.0,
        "library": 0.85,
        "external_academic": 0.65,
        "knowledge_graph": 0.60,  # 16-2: local knowledge graph derivation
        "chart_analysis": 0.55,   # 16-3: VLM chart data extraction
        "image_analysis": 0.50,   # 16-3: VLM image description
        "web_search": 0.45,
        "web_page": 0.40,
    }


def get_source_trust_default() -> float:
    """Return the default trust weight for unknown source types."""
    try:
        from core.config import settings

        return float(settings.pixiu_credibility_default_weight)
    except Exception:
        pass
    return 0.30


def compute_credibility(
    evidence: Dict[str, Any],
    all_evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute structured credibility score for a single evidence item.

    Deterministic weighting; does **not** call an LLM.

    Returns a dict with:
    * ``score`` — 0.0–1.0 composite credibility.
    * ``factors`` — sub-scores that contributed to the composite.
    * ``calibration_note`` — ``high`` / ``medium`` / ``low`` / ``insufficient``.
    """
    source_weights = get_source_trust_weights()
    default_weight = get_source_trust_default()

    source_type = str(evidence.get("sourceType") or evidence.get("source_type") or "unknown")
    source_weight = source_weights.get(source_type, default_weight)

    # Page anchor: items with a page index are more trustworthy.
    has_page = evidence.get("pageIndex") is not None
    page_factor = 1.0 if has_page else 0.65

    # Cross-source agreement: how many *other* evidence items share keywords.
    text = str(evidence.get("text") or "")
    keywords = set(text.lower().split()) if text else set()
    if keywords:
        other_texts = [
            str(e.get("text") or "")
            for e in all_evidence
            if e is not evidence
        ]
        agreement_hits = sum(
            1 for ot in other_texts
            if ot and len(keywords & set(ot.lower().split())) >= 3
        )
        cross_agreement = min(1.0, agreement_hits / max(1, len(other_texts)) * 3)
    else:
        cross_agreement = 0.0

    # Judge score (if present on the evidence item).
    judge_score = float(evidence.get("judgeScore") or evidence.get("score") or 0.5)
    judge_score = max(0.0, min(1.0, judge_score / 100.0 if judge_score > 1.0 else judge_score))

    # Composite score: weighted average.
    score = round(
        source_weight * 0.35
        + page_factor * 0.20
        + cross_agreement * 0.20
        + judge_score * 0.25,
        3,
    )

    return {
        "score": score,
        "factors": {
            "source_type_weight": source_weight,
            "page_anchor_coverage": page_factor,
            "cross_source_agreement": round(cross_agreement, 3),
            "judge_score": round(judge_score, 3),
        },
        "calibration_note": (
            "high" if score >= 0.75
            else "medium" if score >= 0.50
            else "low" if score >= 0.30
            else "insufficient"
        ),
    }


def enrich_evidence_with_credibility(
    evidence_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return a new list where every evidence item carries a ``credibility`` field."""
    weighted: List[Dict[str, Any]] = []
    for item in evidence_items:
        enriched = dict(item)
        enriched["credibility"] = compute_credibility(item, evidence_items)
        weighted.append(enriched)
    return weighted
