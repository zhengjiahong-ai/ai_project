"""
LangGraph-based agent orchestrator with human-in-the-loop support.

Replaces the current sequential pipeline (execute_run -> plan_review -> execute
-> final_review) with a StateGraph that has explicit interrupt nodes for
plan review and final review.

Usage:
    from services.agent_langgraph import run_agent_graph

    graph = build_agent_graph()
    # Initial run: stops at plan_review for human approval
    state = graph.invoke({"prompt": "...", "paper_ids": [...]})
    # After human approves plan:
    state = graph.invoke(Command(resume={"plan_approved": True, ...}), config)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from services.evidence_credibility import enrich_evidence_with_credibility

_logger = logging.getLogger(__name__)

# ── State ────────────────────────────────────────────────────────────────────


class AgentGraphState(TypedDict, total=False):
    # Input
    prompt: str
    paper_ids: List[str]
    constraints: str
    allow_external_search: bool
    allow_web_search: bool
    allow_iterative_search: bool
    domain: str

    # Plan review (human-in-the-loop #1)
    plan_items: List[Dict[str, Any]]
    plan_approved: bool
    plan_review_notes: str

    # Execution
    paper_contexts: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    evidence_items: List[Dict[str, Any]]
    research_timeline: List[Dict[str, Any]]

    # Evidence weighing (14-1)
    weighted_evidence: List[Dict[str, Any]]

    # Cross-paper reasoning (14-1)
    cross_paper_insights: Dict[str, Any]

    # Synthesis
    findings: List[Dict[str, Any]]
    comparison_table: Dict[str, Any]
    conflicts: List[Dict[str, Any]]
    open_questions: List[str]

    # Conflict resolution (14-1)
    resolved_conflicts: List[Dict[str, Any]]
    unresolved_conflicts: List[Dict[str, Any]]

    # Final review (human-in-the-loop #2)
    draft_report: str
    review_risks: List[Dict[str, Any]]
    final_approved: bool
    final_review_notes: str

    # Flow control
    follow_up_count: int
    max_follow_up: int
    error: str
    status: str

    # Observability
    timeline: List[Dict[str, Any]]
    started_at: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _record(state: AgentGraphState, node: str, summary: str) -> None:
    tl = state.get("timeline") or []
    tl.append({"node": node, "summary": summary, "timestamp": _now()})
    state["timeline"] = tl


# ── Nodes ────────────────────────────────────────────────────────────────────


def init_node(state: AgentGraphState) -> AgentGraphState:
    """Initialize state and generate research plan."""
    state["follow_up_count"] = 0
    state["max_follow_up"] = state.get("max_follow_up", 2)
    state["started_at"] = _now()

    try:
        from services.agent_orchestrator import build_plan_items

        paper_ids = state.get("paper_ids", [])
        plan = build_plan_items(paper_ids)
        state["plan_items"] = plan
    except Exception as exc:
        _logger.warning("Plan generation failed: %s", exc)
        state["plan_items"] = [
            {"id": "retrieve", "label": "Collect evidence", "detail": "Auto-generated fallback plan.", "status": "pending"}
        ]
    return state


def plan_review_node(state: AgentGraphState) -> AgentGraphState:
    """Interrupt for human plan review.

    NOTE: LangGraph's ``interrupt()`` rolls back state changes made before the
    interrupt.  All state mutations happen AFTER the resume value is received.

    The caller must resume with:
        Command(resume={"plan_approved": True, "plan_review_notes": "...",
              "plan_items": [...], "allow_external_search": True/False})
    """
    # Interrupt with plan data. The resume value is returned on the second invocation.
    resume: Dict[str, Any] = interrupt({
        "type": "plan_review",
        "plan_items": state.get("plan_items", []),
        "message": "Please review and approve the research plan.",
    })

    # All state changes happen AFTER resume (state before interrupt is rolled back)
    state["status"] = "planning"  # plan was approved, moving forward
    state["plan_approved"] = resume.get("plan_approved", False)
    state["plan_review_notes"] = str(resume.get("plan_review_notes", ""))
    if resume.get("allow_external_search") is not None:
        state["allow_external_search"] = resume["allow_external_search"]

    # Apply any plan item edits from the reviewer
    edited_plan = resume.get("plan_items")
    if edited_plan is not None:
        state["plan_items"] = edited_plan

    _record(state, "plan_review",
            f"Plan {'approved' if state['plan_approved'] else 'rejected'}")
    return state


def plan_decision(state: AgentGraphState) -> str:
    """After plan review: continue if approved, end if rejected."""
    if not state.get("plan_approved"):
        return "rejected"
    return "execute"


def plan_rejected_node(state: AgentGraphState) -> AgentGraphState:
    """Handle rejected plan."""
    state["status"] = "cancelled"
    state["error"] = "Research plan was not approved."
    _record(state, "decision", "Plan rejected → end")
    return state


def execute_node(state: AgentGraphState) -> AgentGraphState:
    """Collect evidence using the existing evidence collector.

    Tracks follow-up rounds: the first entry after plan approval is the main
    execution (round 0); every re-entry via the follow-up loop increments
    ``follow_up_count``.
    """
    # ── follow-up round tracking ──────────────────────────────────────
    # ``_execute_entry_count`` is an internal flag; 0 means first entry.
    entry_count: int = state.get("_execute_entry_count", 0)  # type: ignore[typeddict-item]
    if entry_count > 0:
        state["follow_up_count"] = state.get("follow_up_count", 0) + 1
    state["_execute_entry_count"] = entry_count + 1  # type: ignore[typeddict-item]

    state["status"] = "running"
    _record(state, "execute",
            f"Collecting evidence across papers (round {state.get('follow_up_count', 0)})")

    try:
        from services.agent_evidence_collector import collect_project_evidence

        paper_contexts, tool_calls, evidence_items, research_timeline = (
            collect_project_evidence(
                state["prompt"],
                state.get("paper_ids", []),
                allow_external_search=state.get("allow_external_search", False),
                allow_web_search=state.get("allow_web_search", False),
                allow_iterative_search=state.get("allow_iterative_search", False),
                domain_config=_build_domain_config(state.get("domain", "")),
            )
        )
        state["paper_contexts"] = paper_contexts
        state["tool_calls"] = tool_calls
        state["evidence_items"] = evidence_items
        if research_timeline:
            state["research_timeline"] = research_timeline
        _record(state, "execute",
                f"Collected {len(evidence_items)} evidence items, {len(tool_calls)} tool calls")
    except Exception as exc:
        _logger.exception("Evidence collection failed")
        state["paper_contexts"] = []
        state["tool_calls"] = []
        state["evidence_items"] = []
        _record(state, "execute", f"Evidence collection error: {exc}")
    return state


def synthesize_node(state: AgentGraphState) -> AgentGraphState:
    """Synthesize findings, conflicts, and comparison."""
    _record(state, "synthesize", "Building agent outputs")

    try:
        from services.agent_orchestrator import build_agent_outputs

        finding, comparison_table, conflicts, open_questions = build_agent_outputs(
            state["prompt"],
            state.get("paper_contexts", []),
            state.get("evidence_items", []),
        )
        state["findings"] = [finding] if not isinstance(finding, list) else finding
        state["comparison_table"] = comparison_table or {}
        state["conflicts"] = conflicts or []
        state["open_questions"] = open_questions or []
        _record(state, "synthesize",
                f"{len(state['findings'])} findings, {len(state['conflicts'])} conflicts, "
                f"{len(state['open_questions'])} open questions")
    except Exception as exc:
        _logger.exception("Synthesis failed")
        state["findings"] = []
        state["comparison_table"] = {}
        state["conflicts"] = []
        state["open_questions"] = [f"Synthesis error: {exc}"]
    return state


# ── 14-1/14-2 Reasoning Nodes ─────────────────────────────────────────────────


def evidence_weighing_node(state: AgentGraphState) -> AgentGraphState:
    """Compute structured credibility scores for every evidence item.

    Delegates to the shared ``evidence_credibility`` module (14-2) so the
    same weights and formula are used by both the LangGraph and classic
    ``execute_run`` paths.
    """
    evidence_items: List[Dict[str, Any]] = state.get("evidence_items", [])
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
    weighted: List[Dict[str, Any]] = state.get("weighted_evidence", [])
    paper_ids: List[str] = state.get("paper_ids", [])
    _record(state, "cross_paper_reasoning",
            f"Reasoning across {len(paper_ids)} papers with {len(weighted)} weighted evidence items")

    insights: Dict[str, Any] = {
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
    # Group evidence by paper.
    by_paper: Dict[str, List[Dict[str, Any]]] = {}
    for item in weighted:
        pid = str(item.get("pdfId") or "unknown")
        by_paper.setdefault(pid, []).append(item)

    # Find high-credibility claims per paper.
    HIGH_THRESHOLD = 0.60
    paper_claims: Dict[str, List[str]] = {}
    for pid, items in by_paper.items():
        high_cred = [it for it in items if it.get("credibility", {}).get("score", 0) >= HIGH_THRESHOLD]
        if high_cred:
            paper_claims[pid] = [
                str(it.get("text") or "")[:200]
                for it in sorted(high_cred, key=lambda x: x.get("credibility", {}).get("score", 0), reverse=True)[:6]
            ]

    paper_list = list(paper_claims.keys())

    # Consensus: topics where ≥2 papers have high-cred evidence with overlapping keywords.
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

    # Complementary: papers with different but non-overlapping high-cred evidence.
    covered_topics: Dict[str, set] = {}
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

    # Contradictory: low-cred items that conflict with high-cred items from other papers.
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
                # Simple keyword overlap detection for potential contradiction.
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

    # Gaps: papers with no high-credibility evidence.
    for pid in paper_ids:
        if pid not in paper_claims or len(paper_claims.get(pid, [])) == 0:
            insights["gaps"].append({
                "paper_id": pid,
                "description": f"No high-credibility evidence (≥{HIGH_THRESHOLD}) found for this paper.",
                "severity": "high",
            })

    # LLM enrichment is deferred to 14-2 (evidence credibility model).
    # The deterministic grouping above already produces useful insights.
    insights["llm_enriched"] = False

    # Deduplicate consensus entries.
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
    """
    conflicts: List[Dict[str, Any]] = state.get("conflicts", [])
    weighted: List[Dict[str, Any]] = state.get("weighted_evidence", [])
    _record(state, "conflict_resolution", f"Resolving {len(conflicts)} conflicts")

    resolved: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []

    # Build a lookup: sourceId → credibility score.
    cred_by_source: Dict[str, float] = {}
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

        # Compute average credibility per side.
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
    _record(state, "conflict_resolution",
            f"{len(resolved)} resolved, {len(unresolved)} need manual review")
    return state


def report_node(state: AgentGraphState) -> AgentGraphState:
    """Generate draft report and review risks."""
    _record(state, "report", "Generating draft report and risks")

    try:
        from services.agent_report_sections import build_minimal_report

        state["draft_report"] = build_minimal_report(
            state["prompt"],
            {"title": "Agent Research"},
            state.get("paper_contexts", []),
            state.get("evidence_items", []),
            state.get("conflicts", []),
            state.get("open_questions", []),
        )
    except Exception as exc:
        state["draft_report"] = f"Report generation failed: {exc}"

    # Build review risks
    risks: List[Dict[str, Any]] = []
    for i, c in enumerate(state.get("conflicts", [])[:5]):
        risks.append({
            "riskId": f"conflict:{i}",
            "type": "conflict",
            "label": str(c.get("label", c.get("type", f"Conflict {i+1}")))[:80],
            "detail": str(c.get("detail", ""))[:200],
            "sourceIds": list(c.get("sourceIds", []) or [])[:4],
            "reviewStatus": "pending",
        })
    for i, q in enumerate(state.get("open_questions", [])[:5]):
        risks.append({
            "riskId": f"open:{i}",
            "type": "open_question",
            "label": str(q)[:80],
            "detail": "",
            "sourceIds": [],
            "reviewStatus": "pending",
        })
    state["review_risks"] = risks
    _record(state, "report", f"Draft report + {len(risks)} review risks")
    return state


def follow_up_decision(state: AgentGraphState) -> str:
    """Decide: need more evidence (loop) or go to final review?

    Considers open_questions, cross_paper_insights gaps, and evidence
    count to determine whether another round of evidence collection
    (looping back to execute, which re-collects evidence and then
    flows through evidence_weighing → cross_paper_reasoning → ...)
    is warranted.
    """
    open_qs = state.get("open_questions", [])
    evidence = state.get("evidence_items", [])
    follow_ups = state.get("follow_up_count", 0)
    max_fu = state.get("max_follow_up", 2)

    # Also check cross_paper_insights gaps (14-1).
    insights = state.get("cross_paper_insights", {})
    insight_gaps = insights.get("gaps", []) if isinstance(insights, dict) else []
    high_severity_gaps = [g for g in insight_gaps if g.get("severity") in ("critical", "high")]

    if follow_ups >= max_fu:
        _record(state, "decision", f"Max follow-up ({max_fu}) → final review")
        return "final_review"

    gap_signals = sum(
        1 for q in open_qs
        for kw in ("missing", "gap", "sparse", "need", "insufficient")
        if kw in str(q).lower()
    )
    # Boost gap signals with cross-paper insight gaps.
    gap_signals += len(high_severity_gaps)

    if gap_signals > 0 and len(evidence) < 12:
        _record(state, "decision", f"Gap detected → follow-up round {follow_ups + 1}")
        return "execute"
    _record(state, "decision", "No gap or sufficient evidence → final review")
    return "final_review"


def final_review_node(state: AgentGraphState) -> AgentGraphState:
    """Interrupt for human final review.

    NOTE: LangGraph's ``interrupt()`` rolls back state. All mutations happen
    AFTER resume.
    """
    resume: Dict[str, Any] = interrupt({
        "type": "final_review",
        "draft_report": state.get("draft_report", ""),
        "review_risks": state.get("review_risks", []),
        "message": "Please review the final research draft.",
    })

    state["final_approved"] = resume.get("final_approved", False)
    state["final_review_notes"] = str(resume.get("final_review_notes", ""))

    # Apply risk review updates
    risk_reviews: List[Dict[str, Any]] = resume.get("risk_reviews", [])
    status_by_id = {r.get("riskId"): r.get("reviewStatus", "reviewed")
                    for r in risk_reviews}
    for risk in state.get("review_risks", []):
        rid = risk.get("riskId", "")
        if rid in status_by_id:
            risk["reviewStatus"] = status_by_id[rid]

    _record(state, "final_review",
            f"Final {'approved' if state['final_approved'] else 'rejected'}")
    return state


def final_decision(state: AgentGraphState) -> str:
    """After final review: succeed or fail."""
    if not state.get("final_approved"):
        return "final_rejected"
    return "success"


def final_rejected_node(state: AgentGraphState) -> AgentGraphState:
    """Handle rejected final draft."""
    state["status"] = "cancelled"
    state["error"] = "Final draft was not approved."
    _record(state, "decision", "Final rejected → end")
    return state


def success_node(state: AgentGraphState) -> AgentGraphState:
    """Mark research as succeeded."""
    state["status"] = "succeeded"
    _record(state, "decision", "Final approved → success")
    return state


# ── Graph construction ───────────────────────────────────────────────────────


# ── Shared checkpointer (module-level, survives across invocations) ──────────
_checkpointer: Optional[MemorySaver] = None


def _get_checkpointer() -> MemorySaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer


def build_agent_graph(checkpointer: Optional[Any] = None):
    """Build the LangGraph agent research graph with human-in-the-loop.

    Graph structure (14-1 enhanced):
        init → plan_review (INTERRUPT) → execute
        → evidence_weighing → cross_paper_reasoning → synthesize
        → conflict_resolution → follow_up_decision
        → (loop to execute for re-collection or) → report
        → final_review (INTERRUPT) → end

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence.
                      Defaults to a shared module-level MemorySaver.
    """
    graph = StateGraph(AgentGraphState)

    # Add nodes
    graph.add_node("init", init_node)
    graph.add_node("plan_review", plan_review_node)
    graph.add_node("plan_rejected", plan_rejected_node)
    graph.add_node("execute", execute_node)
    graph.add_node("evidence_weighing", evidence_weighing_node)
    graph.add_node("cross_paper_reasoning", cross_paper_reasoning_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("conflict_resolution", conflict_resolution_node)
    graph.add_node("report", report_node)
    graph.add_node("final_review", final_review_node)
    graph.add_node("final_rejected", final_rejected_node)
    graph.add_node("success", success_node)

    # Entry
    graph.set_entry_point("init")

    # init → plan_review → decision (approved → execute, rejected → plan_rejected)
    graph.add_edge("init", "plan_review")
    graph.add_conditional_edges(
        "plan_review",
        plan_decision,
        {"execute": "execute", "rejected": "plan_rejected"},
    )
    graph.add_edge("plan_rejected", END)

    # execute → evidence_weighing → cross_paper_reasoning → synthesize
    # → conflict_resolution → follow_up_decision
    # → (loop to evidence_weighing or) → report
    graph.add_edge("execute", "evidence_weighing")
    graph.add_edge("evidence_weighing", "cross_paper_reasoning")
    graph.add_edge("cross_paper_reasoning", "synthesize")
    graph.add_edge("synthesize", "conflict_resolution")
    graph.add_conditional_edges(
        "conflict_resolution",
        follow_up_decision,
        {"execute": "execute", "final_review": "report"},
    )

    # report → final_review → decision (approved → success, rejected → final_rejected)
    graph.add_edge("report", "final_review")
    graph.add_conditional_edges(
        "final_review",
        final_decision,
        {"success": "success", "final_rejected": "final_rejected"},
    )
    graph.add_edge("success", END)
    graph.add_edge("final_rejected", END)

    return graph.compile(checkpointer=checkpointer or _get_checkpointer())


# ── Public API ───────────────────────────────────────────────────────────────


def _build_domain_config(domain: str) -> Dict[str, Any]:
    """Build domain-specific config for evidence collection."""
    if not domain:
        return {}
    return {"domain": domain}


def run_agent_graph(
    prompt: str,
    paper_ids: Optional[List[str]] = None,
    *,
    constraints: str = "",
    allow_external_search: bool = False,
    allow_web_search: bool = False,
    allow_iterative_search: bool = False,
    domain: str = "",
    max_follow_up: int = 2,
    thread_id: Optional[str] = None,
) -> AgentGraphState:
    """Run the agent graph and return the final state.

    If the graph interrupts at plan_review or final_review, the returned
    state will have status='awaiting_plan_review' or 'awaiting_final_review'.
    Use resume_agent_graph() to continue after human review.

    Args:
        prompt: Research prompt.
        paper_ids: List of PDF IDs to include.
        constraints: Research constraints.
        allow_external_search: Enable external academic search.
        allow_web_search: Enable web search.
        allow_iterative_search: Enable iterative search loops.
        domain: Research domain (cs/medical/bio/physics/econ).
        max_follow_up: Max follow-up evidence collection rounds.
        thread_id: Optional thread ID for checkpoint persistence.

    Returns:
        The final (or interrupted) graph state.
    """
    graph = build_agent_graph()

    initial_state: AgentGraphState = {
        "prompt": prompt,
        "paper_ids": paper_ids or [],
        "constraints": constraints,
        "allow_external_search": allow_external_search,
        "allow_web_search": allow_web_search,
        "allow_iterative_search": allow_iterative_search,
        "domain": domain,
        "max_follow_up": max_follow_up,
        "follow_up_count": 0,
        "plan_items": [],
        "paper_contexts": [],
        "tool_calls": [],
        "evidence_items": [],
        "research_timeline": [],
        "weighted_evidence": [],
        "cross_paper_insights": {},
        "findings": [],
        "comparison_table": {},
        "conflicts": [],
        "open_questions": [],
        "resolved_conflicts": [],
        "unresolved_conflicts": [],
        "draft_report": "",
        "review_risks": [],
        "plan_approved": False,
        "plan_review_notes": "",
        "final_approved": False,
        "final_review_notes": "",
        "error": "",
        "status": "pending",
        "timeline": [],
        "started_at": _now(),
    }

    config: Dict[str, Any] = {"recursion_limit": 50}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    return graph.invoke(initial_state, config)


def resume_agent_graph(
    resume_data: Dict[str, Any],
    *,
    thread_id: str,
) -> AgentGraphState:
    """Resume an interrupted agent graph after human review.

    Args:
        resume_data: Dictionary with review data. For plan review:
            {"plan_approved": True, "plan_review_notes": "...", ...}
            For final review:
            {"final_approved": True, "final_review_notes": "...", ...}
        thread_id: Thread ID from the original run_agent_graph call.

    Returns:
        The graph state after resuming (may interrupt again at next review point).
    """
    graph = build_agent_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    return graph.invoke(Command(resume=resume_data), config)


def _infer_status(state: AgentGraphState, interrupted: bool = False) -> str:
    """Infer the API status from LangGraph state.

    Because LangGraph rolls back state before ``interrupt()``, we cannot
    set ``status`` inside the node.  Instead we inspect which flags have
    been populated.
    """
    if state.get("error"):
        return "failed"
    if state.get("final_approved"):
        return "succeeded"
    if state.get("plan_approved") and not state.get("final_approved"):
        # After plan approved but before final: check if draft exists
        if state.get("draft_report"):
            return "awaiting_final_review" if not state.get("final_approved") else "succeeded"
        return "running"
    if interrupted:
        # Plan review not done yet → waiting for plan approval
        if not state.get("plan_approved"):
            return "awaiting_plan_review"
    if state.get("plan_items"):
        return "awaiting_plan_review" if not state.get("plan_approved") else "running"
    return state.get("status", "pending")


def agent_graph_state_to_response(
    state: AgentGraphState, interrupted: bool = False
) -> Dict[str, Any]:
    """Convert LangGraph state to the existing API response format.

    Args:
        state: The current graph state.
        interrupted: True if the graph is currently paused at an interrupt.
    """
    status = _infer_status(state, interrupted=interrupted)
    return {
        "prompt": state.get("prompt", ""),
        "paper_ids": state.get("paper_ids", []),
        "status": status,
        "planItems": state.get("plan_items", []),
        "paperContexts": state.get("paper_contexts", []),
        "toolCalls": state.get("tool_calls", []),
        "evidenceItems": state.get("evidence_items", []),
        "weightedEvidence": state.get("weighted_evidence", []),
        "crossPaperInsights": state.get("cross_paper_insights", {}),
        "findings": state.get("findings", []),
        "comparisonTable": state.get("comparison_table", {}),
        "conflicts": state.get("conflicts", []),
        "openQuestions": state.get("open_questions", []),
        "resolvedConflicts": state.get("resolved_conflicts", []),
        "unresolvedConflicts": state.get("unresolved_conflicts", []),
        "draftReport": state.get("draft_report", ""),
        "reviewRisks": state.get("review_risks", []),
        "humanReview": {
            "plan": {
                "status": "approved" if state.get("plan_approved")
                else "pending",
                "reviewNotes": state.get("plan_review_notes", ""),
            },
            "final": {
                "status": "approved" if state.get("final_approved")
                else "pending" if state.get("draft_report")
                else "not_started",
                "reviewNotes": state.get("final_review_notes", ""),
            },
        },
        "researchTimeline": state.get("timeline", []),
        "error": state.get("error", ""),
    }
