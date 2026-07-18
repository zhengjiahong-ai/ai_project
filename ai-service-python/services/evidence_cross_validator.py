"""Multi-source evidence cross-validation.

Supports two modes:
- LLM-based: extracts claims via flash LLM → clusters → scores agreement
- Rule-based: keyword extraction → overlap clustering → polarity-based contradiction detection

Agreement levels:
  confirmed    (>=3 distinct source types)
  supported    (2 distinct source types)
  single_source (1 source only)
  contradicted (opposing polarity detected)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List


def cross_validate_evidence(
    evidence_items: list,
    *,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Cross-validate evidence across multiple sources.

    Extracts claims, clusters them by topic, and scores agreement level
    based on the number and types of supporting sources.

    Args:
        evidence_items: List of evidence dicts with sourceId, sourceType, text.
        use_llm: If True, attempt LLM-based extraction; fall back to rules on failure.

    Returns:
        {"claims": [...], "summary": {...}}
    """
    items = [item for item in (evidence_items or []) if isinstance(item, dict) and item.get("text")]

    if not items:
        return _empty_result()

    if use_llm:
        try:
            return _llm_cross_validate(items)
        except Exception:
            pass

    return _rule_based_cross_validate(items)


# ── LLM path ──────────────────────────────────────────────────────────


def _llm_cross_validate(items: list) -> Dict[str, Any]:
    """Extract claims via LLM, then cluster and score."""
    from llm.client import get_llm

    prompt = _build_claim_extraction_prompt(items)
    try:
        response = get_llm()._call(prompt)
        llm_claims = _parse_llm_claims(response)
    except Exception:
        return _rule_based_cross_validate(items)

    if not llm_claims:
        return _rule_based_cross_validate(items)

    return _cluster_and_score(llm_claims, items)


def _cluster_and_score(llm_claims: list, items: list) -> dict:
    """Cluster LLM-extracted claims by topic overlap and score agreement."""
    item_map = {}
    for item in items:
        sid = item.get("sourceId", "")
        if sid:
            item_map[sid] = item

    enriched = []
    for claim in llm_claims:
        if not isinstance(claim, dict):
            continue
        source_ids = claim.get("sourceIds") or []
        sources = [item_map[s] for s in source_ids if s in item_map]
        source_types = sorted(set(s.get("sourceType", "unknown") for s in sources))
        source_count = len(source_types)
        if source_count >= 3:
            agreement_level = "confirmed"
        elif source_count >= 2:
            agreement_level = "supported"
        elif source_count >= 1:
            agreement_level = "single_source"
        else:
            agreement_level = "single_source"
        enriched.append({
            "claimId": claim.get("claimId", f"c-{len(enriched) + 1}"),
            "claim": claim.get("claim", "")[:200],
            "sourceIds": source_ids,
            "sourceTypes": source_types,
            "agreementLevel": agreement_level,
            "sourceCount": len(sources),
        })

    total_claims = len(enriched)
    confirmed = sum(1 for c in enriched if c["agreementLevel"] == "confirmed")
    supported = sum(1 for c in enriched if c["agreementLevel"] == "supported")
    single = sum(1 for c in enriched if c["agreementLevel"] == "single_source")
    contradicted = sum(1 for c in enriched if c["agreementLevel"] == "contradicted")

    return {
        "claims": enriched,
        "summary": {
            "totalClaims": total_claims,
            "confirmedCount": confirmed,
            "supportedCount": supported,
            "singleSourceCount": single,
            "contradictedCount": contradicted,
            "agreementRate": round((confirmed + supported) / max(total_claims, 1), 2),
            "method": "llm",
        },
    }


def _build_claim_extraction_prompt(items: list) -> str:
    """Build prompt for LLM claim extraction."""
    evidence_texts = []
    for i, item in enumerate(items):
        source_id = item.get("sourceId", f"unknown-{i}")
        source_type = item.get("sourceType", "unknown")
        text = item.get("text", "")[:400]
        evidence_texts.append(f"[{i}] {source_id} ({source_type}): {text}")

    joined = "\n".join(evidence_texts)
    return (
        "Extract 3-8 factual claims from the evidence below. Each claim must be a concise statement "
        "(<=200 chars) that can be verified across sources. Return JSON only:\n"
        '{"claims":[{"claim":"text","sourceIds":["source-id"],"claimId":"c-1"}]}\n\n'
        "Evidence:\n" + joined
    )


def _parse_llm_claims(response: str) -> list:
    """Parse LLM JSON response into claim list."""
    text = str(response or "").strip()
    # Try direct JSON
    try:
        data = json.loads(text)
        return list(data.get("claims") or [])
    except (json.JSONDecodeError, TypeError):
        pass
    # Try fenced JSON
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            data = json.loads(match.group(0))
            return list(data.get("claims") or [])
        except (json.JSONDecodeError, TypeError):
            pass
    return []


# ── Rule-based path ────────────────────────────────────────────────────


def _rule_based_cross_validate(items: list) -> Dict[str, Any]:
    """Extract claims via keyword clustering and polarity detection."""
    # Extract keywords per item
    item_keywords = []
    for item in items:
        text = str(item.get("text") or "")
        keywords = _extract_keywords(text, top_n=5)
        item_keywords.append({
            "sourceId": item.get("sourceId", ""),
            "sourceType": item.get("sourceType", "unknown"),
            "text": text[:200],
            "keywords": keywords,
        })

    # Cluster items by keyword overlap
    clusters = _cluster_by_keyword_overlap(item_keywords)

    # Build claims from clusters
    claims = []
    claim_idx = 0
    for cluster in clusters:
        claim_idx += 1
        source_types = sorted(set(c.get("sourceType", "unknown") for c in cluster))
        source_count = len(cluster)
        polarity_scores = [_evidence_polarity(c["text"]) for c in cluster]
        positive_count = sum(1 for p in polarity_scores if p == "positive")
        negative_count = sum(1 for p in polarity_scores if p == "negative")

        # Determine agreement level
        if positive_count > 0 and negative_count > 0:
            agreement_level = "contradicted"
        elif source_count >= 3:
            agreement_level = "confirmed"
        elif source_count >= 2:
            agreement_level = "supported"
        else:
            agreement_level = "single_source"

        claims.append({
            "claimId": f"claim-{claim_idx}",
            "claim": _summarize_cluster(cluster),
            "source_count": source_count,
            "source_types": source_types,
            "agreement_level": agreement_level,
            "sources": [
                {"sourceId": c["sourceId"], "sourceType": c["sourceType"], "text_preview": c["text"][:120]}
                for c in cluster
            ],
            "needs_more_evidence": source_count <= 1 and agreement_level == "single_source",
            "needs_manual_review": agreement_level == "contradicted",
        })

    # Also handle items that didn't cluster with anything (single-source)
    # These are already handled if a cluster has only 1 item

    summary = _build_summary(claims)
    return {"claims": claims, "summary": summary}


def _extract_keywords(text: str, top_n: int = 5) -> List[str]:
    """Extract top-N keywords from text by TF (simple word frequency)."""
    words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    stopwords = {"the", "and", "for", "that", "this", "with", "from", "was", "are",
                 "not", "but", "have", "has", "had", "its", "can", "all", "been",
                 "which", "will", "also", "more", "than", "over", "about", "into",
                 "after", "other", "each", "only", "some", "such", "these", "when"}
    word_freq: Dict[str, int] = {}
    for w in words:
        if w not in stopwords:
            word_freq[w] = word_freq.get(w, 0) + 1
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:top_n]]


def _cluster_by_keyword_overlap(item_keywords: list) -> List[list]:
    """Cluster items by keyword Jaccard overlap."""
    if not item_keywords:
        return []
    if len(item_keywords) == 1:
        return [[item_keywords[0]]]

    # Build adjacency: two items are connected if Jaccard > 0
    n = len(item_keywords)
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            ki = set(item_keywords[i]["keywords"])
            kj = set(item_keywords[j]["keywords"])
            if not ki or not kj:
                continue
            jaccard = len(ki & kj) / len(ki | kj)
            if jaccard > 0:
                adj[i].append(j)
                adj[j].append(i)

    # Connected components
    visited = [False] * n
    clusters = []
    for i in range(n):
        if not visited[i]:
            comp = []
            stack = [i]
            while stack:
                v = stack.pop()
                if not visited[v]:
                    visited[v] = True
                    comp.append(item_keywords[v])
                    stack.extend(adj[v])
            clusters.append(comp)

    return clusters


def _evidence_polarity(text: str) -> str:
    """Detect polarity of evidence text. Returns "positive", "negative", or ""."""
    text_lower = str(text or "").lower()
    negative_patterns = [
        "no improvement", "not improve", "does not improve",
        "fails to improve", "worse", "decrease", "降低", "没有提升",
        "无提升", "不显著", "no significant", "did not improve",
    ]
    positive_patterns = [
        "improves", "improved", "improvement", "outperforms", "better",
        "increase", "提升", "显著提升", "优于", "significant improvement",
    ]
    for pat in negative_patterns:
        if pat.lower() in text_lower:
            return "negative"
    for pat in positive_patterns:
        if pat.lower() in text_lower:
            return "positive"
    return ""


def _summarize_cluster(cluster: list) -> str:
    """Create a summary claim from a cluster of evidence items."""
    if not cluster:
        return ""
    # Use the longest text preview as the summary
    longest = max(cluster, key=lambda c: len(c.get("text", "")))
    text = longest.get("text", "")
    if len(text) > 200:
        text = text[:197] + "..."
    return text


def _build_summary(claims: list) -> Dict[str, Any]:
    """Build summary statistics from claims list."""
    confirmed = sum(1 for c in claims if c["agreement_level"] == "confirmed")
    supported = sum(1 for c in claims if c["agreement_level"] == "supported")
    single_source = sum(1 for c in claims if c["agreement_level"] == "single_source")
    contradicted = sum(1 for c in claims if c["agreement_level"] == "contradicted")
    needs_manual = sum(1 for c in claims if c.get("needs_manual_review", False))
    return {
        "total_claims": len(claims),
        "confirmed": confirmed,
        "supported": supported,
        "single_source": single_source,
        "contradicted": contradicted,
        "needs_manual_review_count": needs_manual,
    }


def _empty_result() -> Dict[str, Any]:
    return {
        "claims": [],
        "summary": {
            "total_claims": 0,
            "confirmed": 0,
            "supported": 0,
            "single_source": 0,
            "contradicted": 0,
            "needs_manual_review_count": 0,
        },
    }
