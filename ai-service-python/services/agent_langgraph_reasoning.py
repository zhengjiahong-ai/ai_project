"""
Reasoning nodes for the LangGraph agent (14-1/14-2/14-3).

Extracted from ``agent_langgraph.py`` (19-2) to keep the main module under
500 lines.  The three nodes are registered on the graph in
``agent_langgraph.build_agent_graph()``.

* ``evidence_weighing_node`` — deterministic credibility scoring.
* ``cross_paper_reasoning_node`` — cross-paper consensus/complement/
  contradictory/gap detection.
* ``conflict_resolution_node`` — auto-adjudication + follow-up counting
  + information-gain tracking.
"""

from __future__ import annotations

from typing import Any

from services.agent_langgraph import AgentGraphState, _record
from services.evidence_credibility import enrich_evidence_with_credibility


def evidence_weighing_node(state: AgentGraphState) -> AgentGraphState:
    """Compute structured credibility scores for every evidence item.

    Delegates to the shared ``evidence_credibility`` module (14-2) so the
    same weights and formula are used by both the LangGraph and classic
    ``execute_run`` paths.
    """
    evidence_items: list[dict[str, Any]] = state.get("evidence_items", [])
    _record(state, "evidence_weighing", f"Weighing {len(evidence_items)} evidence items")

    weighted = enrich_evidence_with_credibility(evidence_items)
    state["weighted_evidence"] = weighted
    _record(state, "evidence_weighing",
            f"Weighed {len(weighted)} items; "
            f"avg score={sum(e['credibility']['score'] for e in weighted) / max(1, len(weighted)):.2f}")
    return state


def cross_paper_reasoning_node(state: AgentGraphState) -> AgentGraphState:
    """Analyse weighted evidence across papers to surface insights.

    Outputs ``cross_paper_insights`` with four sub-lists:

    * **consensus** — claims independently supported by ≥2 papers.
    * **complementary** — papers contribute disjoint but compatible evidence.
    * **contradictory** — evidence from different papers points in opposite directions.
    * **gaps** — topics with little or no evidence.

    Uses lightweight deterministic grouping + LLM flash-model call for
    semantic judgement (fails gracefully to rule-based fallback).
    """
    weighted: list[dict[str, Any]] = state.get("weighted_evidence", [])
    paper_ids: list[str] = state.get("paper_ids", [])
    _record(state, "cross_paper_reasoning",
            f"Reasoning across {len(paper_ids)} papers with {len(weighted)} weighted evidence items")

    insights: dict[str, Any] = {
        "consensus": [],
        "complementary": [],
        "contradictory": [],
        "gaps": [],
    }

    if not weighted:
        insights["gaps"].append({
            "description": "No evidence collected; unable to perform cross-paper reasoning.",
            "severity": "critical",
        })
        state["cross_paper_insights"] = insights
        _record(state, "cross_paper_reasoning", "No evidence → all gaps")
        return state

    # ── Deterministic grouping ────────────────────────────────────────────
    by_paper: dict[str, list[dict[str, Any]]] = {}
    for item in weighted:
        pid = str(item.get("pdfId") or "unknown")
        by_paper.setdefault(pid, []).append(item)

    HIGH_THRESHOLD = 0.60
    paper_claims: dict[str, list[str]] = {}
    for pid, items in by_paper.items():
        high_cred = [it for it in items if it.get("credibility", {}).get("score", 0) >= HIGH_THRESHOLD]
        if high_cred:
            paper_claims[pid] = [
                str(it.get("text") or "")[:200]
                for it in sorted(high_cred, key=lambda x: x.get("credibility", {}).get("score", 0), reverse=True)[:6]
            ]

    paper_list = list(paper_claims.keys())

    for i in range(len(paper_list)):
        for j in range(i + 1, len(paper_list)):
            p1, p2 = paper_list[i], paper_list[j]
            for c1 in paper_claims.get(p1, []):
                k1 = set(c1.lower().split())
                for c2 in paper_claims.get(p2, []):
                    k2 = set(c2.lower().split())
                    overlap = len(k1 & k2)
                    if overlap >= 4:
                        insights["consensus"].append({
                            "papers": [p1, p2],
                            "shared_terms": sorted(k1 & k2)[:10],
                            "claim_a": c1[:150],
                            "claim_b": c2[:150],
                        })

    covered_topics: dict[str, set] = {}
    for pid, claims in paper_claims.items():
        covered_topics[pid] = set()
        for c in claims:
            covered_topics[pid] |= set(c.lower().split())
    for i in range(len(paper_list)):
        for j in range(i + 1, len(paper_list)):
            p1, p2 = paper_list[i], paper_list[j]
            t1, t2 = covered_topics.get(p1, set()), covered_topics.get(p2, set())
            if t1 and t2 and len(t1 & t2) < 3:
                insights["complementary"].append({
                    "papers": [p1, p2],
                    "paper_a_topics": sorted(t1 - t2)[:8],
                    "paper_b_topics": sorted(t2 - t1)[:8],
                })

    LOW_THRESHOLD = 0.35
    for pid, items in by_paper.items():
        low_items = [it for it in items if it.get("credibility", {}).get("score", 0) <= LOW_THRESHOLD]
        other_high = []
        for opid, oitems in by_paper.items():
            if opid != pid:
                other_high.extend([
                    it for it in oitems
                    if it.get("credibility", {}).get("score", 0) >= HIGH_THRESHOLD
                ])
        for low in low_items[:3]:
            low_text = str(low.get("text") or "")[:100]
            for oh in other_high[:5]:
                oh_text = str(oh.get("text") or "")[:100]
                lk = set(low_text.lower().split())
                ok = set(oh_text.lower().split())
                shared = lk & ok
                if len(shared) >= 3:
                    insights["contradictory"].append({
                        "low_credibility_paper": pid,
                        "high_credibility_paper": oh.get("pdfId"),
                        "shared_topic": sorted(shared)[:8],
                        "low_credibility_claim": low_text,
                        "high_credibility_claim": oh_text,
                    })

    for pid in paper_ids:
        if pid not in paper_claims or len(paper_claims.get(pid, [])) == 0:
            insights["gaps"].append({
                "paper_id": pid,
                "description": f"No high-credibility evidence (≥{HIGH_THRESHOLD}) found for this paper.",
                "severity": "high",
            })

    insights["llm_enriched"] = False

    seen_consensus = set()
    unique_consensus = []
    for entry in insights["consensus"]:
        key = tuple(sorted(entry.get("papers", [])))
        if key not in seen_consensus:
            seen_consensus.add(key)
            unique_consensus.append(entry)
    insights["consensus"] = unique_consensus[:8]

    state["cross_paper_insights"] = insights
    _record(state, "cross_paper_reasoning",
            f"consensus={len(insights['consensus'])}, "
            f"complementary={len(insights['complementary'])}, "
            f"contradictory={len(insights['contradictory'])}, "
            f"gaps={len(insights['gaps'])}")
    return state


def conflict_resolution_node(state: AgentGraphState) -> AgentGraphState:
    """Attempt automatic conflict adjudication.

    A conflict can be auto-resolved when:

    * The evidence weight difference between the two sides is ≥ 0.4, AND
    * The high-weight side has source credibility ≥ 0.8.

    All other conflicts are marked ``needs_manual_review`` with a reason.
    Also handles follow-up counter increment and information-gain tracking
    (14-3) — these MUST live in a real LangGraph *node* (not a conditional
    edge function) for state mutations to be persisted.
    """
    conflicts: list[dict[str, Any]] = state.get("conflicts", [])
    weighted: list[dict[str, Any]] = state.get("weighted_evidence", [])
    _record(state, "conflict_resolution", f"Resolving {len(conflicts)} conflicts")

    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    cred_by_source: dict[str, float] = {}
    for item in weighted:
        sid = str(item.get("sourceId") or "")
        if sid:
            cred_by_source[sid] = item.get("credibility", {}).get("score", 0.5)

    for conflict in conflicts:
        source_ids = list(conflict.get("sourceIds", []) or [])
        if not source_ids:
            unresolved.append({
                **conflict,
                "resolution_status": "needs_manual_review",
                "resolution_reason": "No source IDs to evaluate evidence weight.",
            })
            continue

        scores = [cred_by_source.get(str(sid), 0.5) for sid in source_ids]
        if len(scores) < 2:
            unresolved.append({
                **conflict,
                "resolution_status": "needs_manual_review",
                "resolution_reason": "Single-source conflict; cannot auto-adjudicate.",
            })
            continue

        max_score = max(scores)
        min_score = min(scores)
        weight_diff = max_score - min_score

        if weight_diff >= 0.4 and max_score >= 0.8:
            resolved.append({
                **conflict,
                "resolution_status": "auto_resolved",
                "resolution_direction": f"Favouring higher-credibility evidence (score={max_score:.2f} vs {min_score:.2f})",
                "resolution_confidence": round(weight_diff, 2),
                "winning_source_ids": [
                    str(sid) for sid in source_ids
                    if cred_by_source.get(str(sid), 0.5) == max_score
                ][:3],
            })
        else:
            reason_parts = []
            if weight_diff < 0.4:
                reason_parts.append(
                    f"evidence weight difference ({weight_diff:.2f}) below 0.4 threshold"
                )
            if max_score < 0.8:
                reason_parts.append(
                    f"highest credibility ({max_score:.2f}) below 0.8 threshold"
                )
            unresolved.append({
                **conflict,
                "resolution_status": "needs_manual_review",
                "resolution_reason": "; ".join(reason_parts) + ".",
                "weight_diff": round(weight_diff, 2),
                "max_credibility": round(max_score, 2),
            })

    state["resolved_conflicts"] = resolved
    state["unresolved_conflicts"] = unresolved

    # ── pre-increment follow-up counter + gain tracking (14-1/14-3) ─
    current_fu: int = state.get("follow_up_count", 0)
    max_fu: int = state.get("max_follow_up", 5)

    evidence = state.get("evidence_items", [])
    curr_count: int = len(evidence)
    prev_count: int = state.get("_prev_evidence_count", 0)  # type: ignore[typeddict-item]
    gain_rate: float = 0.0
    if prev_count > 0:
        gain_rate = (curr_count - prev_count) / max(prev_count, 1)
    state["_prev_evidence_count"] = curr_count  # type: ignore[typeddict-item]

    low_gain: int = state.get("_low_gain_count", 0)  # type: ignore[typeddict-item]
    if curr_count > 0 and gain_rate < 0.10:
        low_gain += 1
    else:
        low_gain = 0
    state["_low_gain_count"] = low_gain  # type: ignore[typeddict-item]

    if current_fu < max_fu and low_gain < 2:
        open_qs = state.get("open_questions", [])
        insights = state.get("cross_paper_insights", {})
        insight_gaps = insights.get("gaps", []) if isinstance(insights, dict) else []
        has_gaps = (
            any(
                kw in str(q).lower()
                for q in open_qs
                for kw in ("missing", "gap", "sparse", "need", "insufficient")
            )
            or len(insight_gaps) > 0
        )
        if has_gaps and curr_count < 12:
            state["follow_up_count"] = current_fu + 1

    _record(state, "conflict_resolution",
            f"{len(resolved)} resolved, {len(unresolved)} need manual review")
    return state


# ── Adversarial Verification Node (20-2) ─────────────────────────────


def _generate_counter_hypotheses(
    finding_summary: str,
    timeout_seconds: int = 8,
) -> list:
    """Generate 1-2 counter-hypotheses for a finding.

    Uses the translation (cheaper) LLM. On timeout or failure,
    returns an empty list (fail-open: don't block the main pipeline).
    """
    try:
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FutureTimeout

        from llm.client import get_translation_llm
        from services.llm_cache import get_llm_cache

        cache = get_llm_cache()
        cached = cache.get(
            "adversarial-counter-hypothesis", 0.1, "",
            finding_summary[:200],
        )
        if cached is not None:
            # cached is a JSON list of hypothesis strings
            import json
            try:
                parsed = json.loads(cached)
                if isinstance(parsed, list):
                    return parsed[:2]
            except (json.JSONDecodeError, TypeError):
                pass

        prompt = (
            "You are a rigorous scientific reviewer. For the following "
            "research finding, generate 1-2 specific counter-hypotheses "
            "or potential weaknesses. Consider: sample size limitations, "
            "methodological flaws, alternative explanations, confounding "
            "variables, or generalizability concerns.\n\n"
            f"Finding: {finding_summary}\n\n"
            "Return ONLY the counter-hypotheses, one per line, "
            "prefixed with '- '. Max 2 hypotheses."
        )

        llm = get_translation_llm()

        def _call():
            return llm._call(prompt)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            result = future.result(timeout=timeout_seconds)

        hypotheses = []
        if result:
            for line in str(result).split("\n"):
                stripped = line.strip()
                if stripped.startswith("- "):
                    hypotheses.append(stripped[2:].strip())
                elif stripped.startswith("-"):
                    hypotheses.append(stripped[1:].strip())

        result_list = hypotheses[:2]

        # Cache result
        import json
        cache.put(
            "adversarial-counter-hypothesis", 0.1, "",
            finding_summary[:200],
            json.dumps(result_list),
        )

        return result_list

    except (FutureTimeout, Exception):
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Counter-hypothesis generation failed for finding: %s",
            finding_summary[:100],
        )
        return []


def adversarial_verification_node(state: dict) -> dict:
    """Adversarial verification node for the LangGraph agent pipeline.

    For each finding:
    1. Generate counter-hypotheses using cheaper LLM (8s timeout, fail-open).
    2. Check evidence items for support/contradiction.
    3. Assign status: verified | falsified | unverifiable.

    Inserted between conflict_resolution's follow_up_decision "final_review"
    path and the report node.
    """
    import logging
    logger = logging.getLogger(__name__)

    findings = state.get("findings") or []
    weighted_evidence = state.get("weighted_evidence") or []

    verification_results = []

    for finding in findings:
        finding_id = finding.get("finding_id", "")
        summary = finding.get("summary", "")
        credibility = finding.get("credibility", 0.5)

        # Generate counter-hypotheses (may use LLM or cache)
        counter_hypotheses = _generate_counter_hypotheses(summary)

        # Determine status based on evidence strength and credibility
        source_ids = set(finding.get("sourceIds") or [])
        supporting_evidence_count = 0
        for ev in weighted_evidence:
            if ev.get("sourceId") in source_ids:
                ev_cred = ev.get("credibility", 0)
                if isinstance(ev_cred, (int, float)) and ev_cred >= 0.5:
                    supporting_evidence_count += 1

        if counter_hypotheses and supporting_evidence_count == 0:
            # Counter-hypotheses exist AND no supporting evidence
            status = "unverifiable"
        elif credibility < 0.4 and supporting_evidence_count == 0:
            # Very low credibility with no supporting evidence
            status = "falsified"
        else:
            # Sufficient evidence and credibility to verify
            status = "verified"

        verification_results.append({
            "finding_id": finding_id,
            "status": status,
            "counter_hypothesis": (
                counter_hypotheses[0] if counter_hypotheses else ""
            ),
            "evidence_ref": list(source_ids),
        })

    new_state = dict(state)
    new_state["verification_results"] = verification_results

    verified_count = sum(
        1 for v in verification_results if v["status"] == "verified"
    )
    falsified_count = sum(
        1 for v in verification_results if v["status"] == "falsified"
    )
    unverifiable_count = sum(
        1 for v in verification_results if v["status"] == "unverifiable"
    )
    logger.info(
        "Adversarial verification: %d verified, %d falsified, %d unverifiable",
        verified_count,
        falsified_count,
        unverifiable_count,
    )

    return new_state
