"""Conflict adjudicator — evaluates which side of a scientific disagreement
is more reliable based on methodology, venue, recency, and replication evidence.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

LLM_TIMEOUT_S = 25

VENUE_TIERS: dict[str, int] = {
    "nature": 5, "science": 5, "cell": 5, "pnas": 4, "neurips": 4, "icml": 4,
    "iclr": 4, "cvpr": 4, "iccv": 4, "eccv": 4, "acl": 4, "emnlp": 4,
    "aaai": 3, "ijcai": 3, "ieee": 3, "acm": 3, "springer": 3, "elsevier": 3,
    "arxiv": 2, "corr": 2,
}

CURRENT_YEAR = 2026


# ── Public API ───────────────────────────────────────────────────────────────

def adjudicate_conflict(
    claim: str,
    pro_sources: list[dict[str, Any]],
    con_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Adjudicate a scientific conflict between pro and con evidence.

    Returns ``{status, winner, confidence, reasoning, keyFactors, error}``.
    """
    if not claim or not claim.strip():
        return _error("Claim cannot be empty.")
    if not pro_sources and not con_sources:
        return _error("At least one side must have evidence.")

    claim = claim.strip()[:300]
    pro_sources = [s for s in pro_sources if isinstance(s, dict)][:10]
    con_sources = [c for c in con_sources if isinstance(c, dict)][:10]

    # Rule-based scoring
    pro_score = _score_side(pro_sources)
    con_score = _score_side(con_sources)

    # LLM analysis
    llm_analysis = _llm_adjudicate(claim, pro_sources, con_sources)

    # Combine
    rule_winner = "pro" if pro_score > con_score else ("con" if con_score > pro_score else "inconclusive")
    rule_margin = abs(pro_score - con_score)

    if llm_analysis:
        winner = llm_analysis.get("winner", rule_winner)
        confidence = float(llm_analysis.get("confidence", 0.5))
        reasoning = llm_analysis.get("reasoning", "")
        key_factors = llm_analysis.get("keyFactors", [])
    else:
        winner = rule_winner
        confidence = min(0.3 + rule_margin * 0.1, 0.7)
        reasoning = f"规则评分 — 正方 {pro_score:.1f} vs 反方 {con_score:.1f}。" + (
            "正方证据权重更高。" if winner == "pro" else
            "反方证据权重更高。" if winner == "con" else
            "双方证据权重接近，无法判定。"
        )
        key_factors = [
            f"正方 {len(pro_sources)} 条证据, 反方 {len(con_sources)} 条证据",
            f"正方最高venue: {_best_venue(pro_sources)}, 反方最高venue: {_best_venue(con_sources)}",
            f"正方最新: {_newest_year(pro_sources)}, 反方最新: {_newest_year(con_sources)}",
        ]

    return {
        "status": "success",
        "claim": claim,
        "winner": winner,
        "confidence": round(confidence, 2),
        "proScore": round(pro_score, 1),
        "conScore": round(con_score, 1),
        "reasoning": reasoning[:600],
        "keyFactors": key_factors[:8],
        "error": "",
    }


# ── Rule-based scoring ───────────────────────────────────────────────────────

def _score_side(sources: list[dict[str, Any]]) -> float:
    if not sources:
        return 0.0
    scores = []
    for src in sources:
        s = 1.0  # base
        # Venue tier
        venue = str(src.get("venue") or src.get("journal") or "").lower()
        for keyword, tier in VENUE_TIERS.items():
            if keyword in venue:
                s += tier * 0.3
                break
        # Recency
        year = _safe_int(src.get("year"))
        if year:
            age = CURRENT_YEAR - year
            if age <= 2:
                s += 1.0
            elif age <= 5:
                s += 0.5
            elif age <= 10:
                s += 0.2
        # Sample / methodology hints
        text = str(src.get("text") or "")
        if re.search(r"n\s*[=＝]\s*\d{3,}", text):
            s += 0.5  # explicit sample size
        if re.search(r"(randomized|double.?blind|controlled.?trial|RCT)", text, re.IGNORECASE):
            s += 1.0  # rigorous methodology
        # Citation count
        citations = _safe_int(src.get("citationCount"))
        if citations:
            if citations >= 100:
                s += 1.5
            elif citations >= 20:
                s += 0.8
            elif citations >= 5:
                s += 0.3
        scores.append(max(s, 0.5))
    return sum(scores) / len(scores)


def _best_venue(sources: list[dict[str, Any]]) -> str:
    best = ""
    best_tier = 0
    for src in sources:
        venue = str(src.get("venue") or src.get("journal") or "")
        for keyword, tier in VENUE_TIERS.items():
            if keyword in venue.lower() and tier > best_tier:
                best_tier = tier
                best = venue[:80]
    return best or "unknown"


def _newest_year(sources: list[dict[str, Any]]) -> str:
    years = [y for s in sources if (y := _safe_int(s.get("year")))]
    return str(max(years)) if years else "unknown"


# ── LLM analysis ─────────────────────────────────────────────────────────────

def _llm_adjudicate(
    claim: str, pro: list[dict[str, Any]], con: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        from llm.client import get_llm

        pro_text = "\n".join(
            f"- [{s.get('title','?')[:120]}] {s.get('text','')[:200]}"
            for s in pro[:5]
        ) or "(无)"
        con_text = "\n".join(
            f"- [{c.get('title','?')[:120]}] {c.get('text','')[:200]}"
            for c in con[:5]
        ) or "(无)"

        prompt = (
            f"科学争议：{claim}\n\n"
            f"正方证据（支持该主张）：\n{pro_text}\n\n"
            f"反方证据（反对或质疑该主张）：\n{con_text}\n\n"
            "请裁决哪一方更可靠。评估维度：方法论严谨度、发表venue权威性、时效性、"
            "样本量/统计方法、独立复现情况。\n"
            "用JSON回复：{\"winner\": \"pro\"|\"con\"|\"inconclusive\", "
            "\"confidence\": 0.0-1.0, \"reasoning\": \"...\", "
            "\"keyFactors\": [\"...\"]}"
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            raw = future.result(timeout=LLM_TIMEOUT_S)
    except Exception:
        return None

    try:
        result = json.loads(raw.strip().split("```json")[-1].split("```")[0].strip())
        return {
            "winner": str(result.get("winner", "inconclusive")).strip(),
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": str(result.get("reasoning", ""))[:500],
            "keyFactors": list(result.get("keyFactors", []))[:6],
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_int(value: Any) -> int | None:
    try:
        v = int(value)
        return v if 1000 <= v <= 2100 else None
    except (TypeError, ValueError):
        return None


def _error(message: str) -> dict[str, Any]:
    return {
        "status": "error", "claim": "", "winner": "", "confidence": 0.0,
        "proScore": 0.0, "conScore": 0.0, "reasoning": "", "keyFactors": [], "error": message,
    }
