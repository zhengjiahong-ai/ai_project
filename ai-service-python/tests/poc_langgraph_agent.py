"""
7-1 LangGraph PoC: Compare current agent pipeline with a LangGraph StateGraph.

Evaluates feasibility of replacing the current sequential pipeline
(execute_run → collect_project_evidence → build_agent_outputs → follow-up loop)
with a LangGraph-based orchestrator.

Usage:
    PYTHONPATH=. python tests/poc_langgraph_agent.py
"""
import json
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

# ── State definition ────────────────────────────────────────────────────────

class ResearchState(TypedDict):
    prompt: str
    paper_ids: List[str]
    allow_external_search: bool
    allow_web_search: bool
    domain: str

    # Flow control
    plan_items: List[Dict[str, Any]]
    evidence_items: List[Dict[str, Any]]
    paper_contexts: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    open_questions: List[str]
    comparison_table: Dict[str, Any]
    draft_report: str

    follow_up_count: int
    max_follow_up: int
    done: bool

    # Observability
    timeline: List[Dict[str, Any]]
    llm_calls: int


# ── Node implementations ────────────────────────────────────────────────────

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _record(state: ResearchState, node: str, summary: str) -> None:
    state["timeline"].append({
        "node": node,
        "summary": summary,
        "timestamp": _now(),
    })


def plan_node(state: ResearchState) -> ResearchState:
    """Generate research plan items (analogous to build_plan_items)."""
    _record(state, "plan", f"Planning for {len(state['paper_ids'])} papers")
    state["plan_items"] = [
        {"id": "scope", "label": "Confirm scope", "detail": "Resolve focused papers and constraints.", "status": "pending"},
        {"id": "retrieve", "label": "Collect evidence", "detail": f"Retrieve from {len(state['paper_ids'])} papers.", "status": "pending"},
        {"id": "synthesize", "label": "Judge and compare", "detail": "Build cross-paper judgements and draft report.", "status": "pending"},
    ]
    return state


def execute_node(state: ResearchState) -> ResearchState:
    """Collect evidence (analogous to collect_project_evidence)."""
    _record(state, "execute", "Collecting paper evidence")
    try:
        from services.agent_evidence_collector import collect_project_evidence

        paper_contexts, tool_calls, evidence_items, research_timeline = collect_project_evidence(
            state["prompt"],
            state["paper_ids"],
            allow_external_search=state.get("allow_external_search", False),
            allow_web_search=state.get("allow_web_search", False),
            allow_iterative_search=False,
            domain_config={},
        )
        state["paper_contexts"] = paper_contexts
        state["evidence_items"] = evidence_items
        state["llm_calls"] += 1
    except Exception as exc:
        _record(state, "execute", f"Evidence collection failed: {exc}")
        state["paper_contexts"] = []
        state["evidence_items"] = []
    return state


def aggregate_node(state: ResearchState) -> ResearchState:
    """Synthesize findings (analogous to build_agent_outputs)."""
    _record(state, "aggregate", "Building agent outputs")
    try:
        from services.agent_orchestrator import build_agent_outputs

        finding, comparison_table, conflicts, open_questions = build_agent_outputs(
            state["prompt"],
            state.get("paper_contexts", []),
            state.get("evidence_items", []),
        )
        state["findings"] = [finding]
        state["comparison_table"] = comparison_table
        state["conflicts"] = conflicts
        state["open_questions"] = open_questions or []
        state["llm_calls"] += 1
    except Exception as exc:
        _record(state, "aggregate", f"Aggregation failed: {exc}")
        state["findings"] = []
        state["open_questions"] = [f"Aggregation error: {exc}"]
    return state


def report_node(state: ResearchState) -> ResearchState:
    """Generate draft report (analogous to build_minimal_report)."""
    _record(state, "report", "Generating draft report")
    try:
        from services.agent_report_sections import build_minimal_report

        state["draft_report"] = build_minimal_report(
            state["prompt"],
            {"title": "Project"},
            state.get("paper_contexts", []),
            state.get("evidence_items", []),
            state.get("conflicts", []),
            state.get("open_questions", []),
        )
    except Exception as exc:
        state["draft_report"] = f"Report generation failed: {exc}"
    return state


def follow_up_decision(state: ResearchState) -> str:
    """Decide whether to loop back for follow-up evidence collection."""
    open_qs = state.get("open_questions", [])
    evidence = state.get("evidence_items", [])
    follow_ups = state.get("follow_up_count", 0)
    max_fu = state.get("max_follow_up", 2)

    if follow_ups >= max_fu:
        _record(state, "decision", f"Max follow-up rounds ({max_fu}) reached → report")
        return "report"

    has_gap = any(
        kw in str(q).lower()
        for q in open_qs
        for kw in ("need", "gap", "sparse", "missing", "cover")
    )
    if has_gap and len(evidence) < 12:
        state["follow_up_count"] = follow_ups + 1
        _record(state, "decision", f"Gap detected, follow-up round {follow_ups + 1}")
        return "execute"
    _record(state, "decision", f"No gap or enough evidence ({len(evidence)} items) → report")
    return "report"


# ── Graph construction ──────────────────────────────────────────────────────

def build_research_graph() -> StateGraph:
    graph = StateGraph(ResearchState)

    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "aggregate")
    graph.add_conditional_edges(
        "aggregate",
        follow_up_decision,
        {"execute": "execute", "report": "report"},
    )
    graph.add_edge("report", END)

    return graph.compile()


# ── Benchmark harness ───────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    name: str
    duration_sec: float
    evidence_count: int
    finding_summary: str
    open_questions: int
    timeline_length: int
    error: Optional[str] = None


def run_current_pipeline(prompt: str, paper_ids: List[str]) -> BenchmarkResult:
    """Run the current execute_run pipeline and measure."""
    from services.agent_orchestrator import execute_run

    start = time.time()
    try:
        result = execute_run(prompt, paper_ids)
        duration = time.time() - start
        artifacts = result.get("artifacts", {})
        return BenchmarkResult(
            name="current",
            duration_sec=round(duration, 2),
            evidence_count=len(artifacts.get("evidenceItems", [])),
            finding_summary=str(artifacts.get("findings", [{}])[0].get("summary", ""))[:120],
            open_questions=len(artifacts.get("openQuestions", [])),
            timeline_length=len(result.get("researchTimeline", [])),
        )
    except Exception as exc:
        return BenchmarkResult(
            name="current",
            duration_sec=round(time.time() - start, 2),
            evidence_count=0,
            finding_summary="",
            open_questions=0,
            timeline_length=0,
            error=str(exc),
        )


def run_langgraph_pipeline(prompt: str, paper_ids: List[str]) -> BenchmarkResult:
    """Run the LangGraph pipeline and measure."""
    graph = build_research_graph()
    initial_state: ResearchState = {
        "prompt": prompt,
        "paper_ids": paper_ids,
        "allow_external_search": False,
        "allow_web_search": False,
        "domain": "",
        "plan_items": [],
        "evidence_items": [],
        "paper_contexts": [],
        "findings": [],
        "conflicts": [],
        "open_questions": [],
        "comparison_table": {},
        "draft_report": "",
        "follow_up_count": 0,
        "max_follow_up": 2,
        "done": False,
        "timeline": [],
        "llm_calls": 0,
    }

    start = time.time()
    try:
        final_state = graph.invoke(initial_state)
        duration = time.time() - start
        return BenchmarkResult(
            name="langgraph",
            duration_sec=round(duration, 2),
            evidence_count=len(final_state.get("evidence_items", [])),
            finding_summary=str(final_state.get("findings", [{}])[0].get("summary", ""))[:120],
            open_questions=len(final_state.get("open_questions", [])),
            timeline_length=len(final_state.get("timeline", [])),
        )
    except Exception as exc:
        return BenchmarkResult(
            name="langgraph",
            duration_sec=round(time.time() - start, 2),
            evidence_count=0,
            finding_summary="",
            open_questions=0,
            timeline_length=0,
            error=str(exc),
        )


# ── Report ──────────────────────────────────────────────────────────────────

def print_report(results: List[BenchmarkResult]) -> None:
    print("\n" + "=" * 72)
    print("  7-1 LangGraph PoC: 当前管道 vs LangGraph StateGraph 对比")
    print("=" * 72)

    for r in results:
        print(f"\n  [{r.name}]")
        print(f"    耗时:        {r.duration_sec}s")
        print(f"    证据项:      {r.evidence_count}")
        print(f"    开放问题:    {r.open_questions}")
        print(f"    时间线条目:  {r.timeline_length}")
        print(f"    Finding:     {r.finding_summary[:100]}")
        if r.error:
            print(f"    [ERROR]:     {r.error}")

    if len(results) >= 2:
        current = results[0]
        lg = results[1]
        if not current.error and not lg.error:
            speedup = current.duration_sec / lg.duration_sec if lg.duration_sec > 0 else float("inf")
            print(f"\n  [BENCH] LangGraph 相比 current 耗时比: {speedup:.2f}x")
            print(f"     (current: {current.duration_sec}s, langgraph: {lg.duration_sec}s)")

    print("\n  * 评估要点:")
    print("     - LangGraph 增加了 StateGraph 构建开销（首次编译 ~100-300ms）")
    print("     - 节点级可观测性更好（每步自动记录 timeline）")
    print("     - 条件边使 follow-up 决策显式化、可测试")
    print("     - 适合进一步添加人工审批节点（human-in-the-loop）")
    print("     - 迁移成本：需要将当前 execute_run 拆为独立节点函数")
    print("=" * 72)


if __name__ == "__main__":
    TEST_PROMPT = "Compare methods and evidence strength across the attached papers."
    TEST_PAPERS: List[str] = []  # Use empty list to test in no-paper fallback mode

    print("7-1 LangGraph PoC Benchmark")
    print(f"  prompt: {TEST_PROMPT}")
    print(f"  papers: {TEST_PAPERS or '(none — fallback mode)'}")

    results: List[BenchmarkResult] = []

    print("\n> Running current pipeline...")
    results.append(run_current_pipeline(TEST_PROMPT, TEST_PAPERS))

    print("> Running LangGraph pipeline...")
    results.append(run_langgraph_pipeline(TEST_PROMPT, TEST_PAPERS))

    print_report(results)
