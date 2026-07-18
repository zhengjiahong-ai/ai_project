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
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

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

    # Synthesis
    findings: List[Dict[str, Any]]
    comparison_table: Dict[str, Any]
    conflicts: List[Dict[str, Any]]
    open_questions: List[str]

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
    """Collect evidence using the existing evidence collector."""
    state["status"] = "running"
    _record(state, "execute", "Collecting evidence across papers")

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


def report_node(state: AgentGraphState) -> AgentGraphState:
    """Generate draft report and review risks."""
    _record(state, "report", "Generating draft report and risks")

    try:
        from services.agent_orchestrator import build_agent_outputs as _outputs
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
    """Decide: need more evidence (loop) or go to final review?"""
    open_qs = state.get("open_questions", [])
    evidence = state.get("evidence_items", [])
    follow_ups = state.get("follow_up_count", 0)
    max_fu = state.get("max_follow_up", 2)

    if follow_ups >= max_fu:
        _record(state, "decision", f"Max follow-up ({max_fu}) → final review")
        return "final_review"

    gap_signals = sum(
        1 for q in open_qs
        for kw in ("missing", "gap", "sparse", "need", "insufficient")
        if kw in str(q).lower()
    )
    if gap_signals > 0 and len(evidence) < 12:
        state["follow_up_count"] = follow_ups + 1
        _record(state, "decision", f"Gap detected → follow-up round {follow_ups + 1}")
        return "execute"
    _record(state, "decision", f"No gap or sufficient evidence → final review")
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

    Graph structure:
        init → plan_review (INTERRUPT) → execute → synthesize
        → follow_up_decision → (loop to execute or) → report
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
    graph.add_node("synthesize", synthesize_node)
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

    # execute → synthesize → follow_up decision → (loop or) → report
    graph.add_edge("execute", "synthesize")
    graph.add_conditional_edges(
        "synthesize",
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
        "findings": [],
        "comparison_table": {},
        "conflicts": [],
        "open_questions": [],
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

    config: Dict[str, Any] = {}
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
    config = {"configurable": {"thread_id": thread_id}}
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
        "findings": state.get("findings", []),
        "comparisonTable": state.get("comparison_table", {}),
        "conflicts": state.get("conflicts", []),
        "openQuestions": state.get("open_questions", []),
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
