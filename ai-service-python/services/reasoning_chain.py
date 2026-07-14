"""Multi-step reasoning chain builder.

Traces a scientific claim through multiple papers by following citation
links and classifying each paper's stance toward the claim.
"""

from __future__ import annotations

from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

RELATION_LABELS: frozenset[str] = frozenset({
    "supports",         # explicitly agrees with or confirms the claim
    "contradicts",      # explicitly disagrees with or refutes the claim
    "extends",          # builds upon / generalizes the claim
    "replicates",       # independently reproduces the finding
    "cites_without_engagement",  # mentions but does not substantively engage
})

LLM_TIMEOUT_S = 20


# ── Public API ───────────────────────────────────────────────────────────────

def build_reasoning_chain(
    claim: str,
    evidence_sources: list[dict[str, Any]],
    citation_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a reasoning chain for *claim* across *evidence_sources*.

    Parameters
    ----------
    claim
        The scientific claim to trace (e.g. "Method X outperforms Method Y").
    evidence_sources
        List of evidence dicts, each with ``sourceId``, ``text``, ``sourceType``,
        ``title``, and optionally ``year``.
    citation_graph
        Optional pre-built citation graph from :func:`citation_graph.traverse_citation_graph`.

    Returns
    -------
    dict with ``status``, ``claim``, ``chain`` (tree), ``summary``, ``error``.
    """
    if not claim or not claim.strip():
        return _error("Claim cannot be empty.")
    if not evidence_sources:
        return _error("At least one evidence source is required.")

    claim = claim.strip()[:500]
    chain_nodes: list[dict[str, Any]] = []

    for i, src in enumerate(evidence_sources[:20]):
        if not isinstance(src, dict):
            continue
        text = (src.get("text") or "").strip()
        title = src.get("title", "")
        src_id = src.get("sourceId", f"src-{i}")
        if not text and not title:
            continue

        relation = _classify_relation(claim, text, title)
        chain_nodes.append({
            "sourceId": src_id,
            "title": (title or "")[:200],
            "year": src.get("year"),
            "snippet": text[:300],
            "relation": relation["label"],
            "confidence": relation["confidence"],
            "rationale": relation["rationale"],
        })

    if citation_graph and isinstance(citation_graph, dict):
        # Enrich nodes with citation context if graph is available
        nodes_by_id = {
            n.get("paperId", ""): n for n in (citation_graph.get("nodes") or [])
        }
        for node in chain_nodes:
            pid = node["sourceId"]
            if pid in nodes_by_id:
                node["citationCount"] = nodes_by_id[pid].get("citationCount")

    summary = _summarize_chain(claim, chain_nodes)

    return {
        "status": "success",
        "claim": claim,
        "chain": chain_nodes,
        "summary": summary,
        "nodeCount": len(chain_nodes),
        "error": "",
    }


# ── LLM classification ──────────────────────────────────────────────────────

def _classify_relation(claim: str, text: str, title: str) -> dict[str, Any]:
    """Use LLM to classify the paper's stance toward the claim."""
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
        from llm.client import get_llm

        prompt = (
            f"科学主张：{claim}\n\n"
            f"论文标题：{title[:300]}\n"
            f"论文片段：{text[:800]}\n\n"
            "请判断这篇论文对上述主张的立场，从以下选一项：\n"
            "- supports: 明确支持或证实该主张\n"
            "- contradicts: 明确反对或反驳该主张\n"
            "- extends: 在该主张基础上扩展或推广\n"
            "- replicates: 独立复现了支持该主张的结果\n"
            "- cites_without_engagement: 提及但未实质讨论\n\n"
            "请用 JSON 回复：{\"label\": \"...\", \"confidence\": 0.0-1.0, \"rationale\": \"一句话理由\"}"
        )
        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            raw = future.result(timeout=LLM_TIMEOUT_S)
    except (FutureTimeout, Exception):
        return _rule_fallback(claim, text)

    import json
    try:
        result = json.loads(raw.strip().split("```json")[-1].split("```")[0].strip())
        label = str(result.get("label", "")).strip().lower()
        if label not in RELATION_LABELS:
            label = "cites_without_engagement"
        conf = float(result.get("confidence", 0.5))
        conf = min(max(conf, 0.0), 1.0)
        rationale = str(result.get("rationale", ""))[:200]
        return {"label": label, "confidence": conf, "rationale": rationale}
    except (json.JSONDecodeError, ValueError, TypeError):
        return _rule_fallback(claim, text)


def _rule_fallback(claim: str, text: str) -> dict[str, Any]:
    """Keyword-based fallback when LLM is unavailable."""
    text_lower = text.lower()
    claim_words = set(claim.lower().split()) & set(text_lower.split())
    overlap = len(claim_words)

    negation_words = {"however", "but", "although", "contrary", "unlike", "失败", "未能", "不如"}
    support_words = {"improves", "outperforms", "better", "effective", "提升", "优于", "证实"}

    has_negation = any(w in text_lower for w in negation_words)
    has_support = any(w in text_lower for w in support_words)

    if overlap < 3:
        return {"label": "cites_without_engagement", "confidence": 0.3, "rationale": "Low keyword overlap with claim"}
    if has_negation and not has_support:
        return {"label": "contradicts", "confidence": 0.4, "rationale": "Negation keywords detected"}
    if has_support:
        return {"label": "supports", "confidence": 0.5, "rationale": "Support keywords detected"}
    return {"label": "cites_without_engagement", "confidence": 0.35, "rationale": "No clear signal"}


def _summarize_claim(claim: str, nodes: list[dict[str, Any]]) -> str:
    supports = sum(1 for n in nodes if n["relation"] == "supports")
    contradicts = sum(1 for n in nodes if n["relation"] == "contradicts")
    extends = sum(1 for n in nodes if n["relation"] == "extends")
    replicates = sum(1 for n in nodes if n["relation"] == "replicates")
    total = len(nodes)

    parts = [f"对主张「{claim[:120]}」追踪 {total} 篇相关论文："]
    if supports:
        parts.append(f"{supports} 篇支持，")
    if contradicts:
        parts.append(f"{contradicts} 篇反对，")
    if extends:
        parts.append(f"{extends} 篇扩展，")
    if replicates:
        parts.append(f"{replicates} 篇复现，")
    without = total - supports - contradicts - extends - replicates
    if without:
        parts.append(f"{without} 篇未实质讨论。")
    else:
        parts[-1] = parts[-1].rstrip("，") + "。"
    return "".join(parts)


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "claim": "", "chain": [], "summary": "", "nodeCount": 0, "error": message}
