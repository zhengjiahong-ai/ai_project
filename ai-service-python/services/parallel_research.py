"""Multi-agent parallel research — dispatches sub-questions to independent
agents, executes concurrently, then merges findings with cross-validation.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

MAX_PARALLEL_AGENTS = 6
AGENT_TIMEOUT_S = 300  # 5 min per sub-agent


# ── Public API ───────────────────────────────────────────────────────────────

def dispatch_parallel_research(
    question: str,
    sub_questions: list[str],
    max_agents: int = MAX_PARALLEL_AGENTS,
    allow_web_search: bool = True,
) -> dict[str, Any]:
    """Fan-out *sub_questions* to independent agents, then merge results.

    Returns ``{status, question, subResults, mergedFindings, crossValidation, error}``.
    """
    if not question or not question.strip():
        return _error("Research question cannot be empty.")
    if not sub_questions:
        return _error("At least one sub-question is required.")

    question = question.strip()
    sub_questions = [s.strip() for s in sub_questions[:max_agents] if s.strip()]
    max_agents = min(max_agents, len(sub_questions))

    # Execute in parallel
    sub_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_agents) as executor:
        futures = {}
        for sq in sub_questions:
            future = executor.submit(
                _execute_single_agent, question, sq, allow_web_search
            )
            futures[future] = sq

        for future in concurrent.futures.as_completed(futures, timeout=AGENT_TIMEOUT_S):
            sq = futures[future]
            try:
                result = future.result(timeout=10)
                sub_results.append(result)
            except Exception as exc:
                sub_results.append({
                    "subQuestion": sq[:120],
                    "status": "failed",
                    "summary": "",
                    "error": str(exc)[:200],
                })

    # Merge
    merged = _merge_parallel_findings(question, sub_results)

    return {
        "status": "success",
        "question": question,
        "subResults": sub_results,
        "mergedFindings": merged["findings"],
        "crossValidation": merged["crossValidation"],
        "summary": merged["summary"],
        "agentCount": len(sub_results),
        "error": "",
    }


# ── Single-agent execution ───────────────────────────────────────────────────

def _execute_single_agent(
    question: str, sub_question: str, allow_web_search: bool,
) -> dict[str, Any]:
    """Run a single sub-agent using the existing research pipeline."""
    try:
        from services.agent_orchestrator import (
            build_agent_outputs,
            collect_project_evidence,
        )

        # Minimal execution: search → evidence → judge
        paper_contexts, tool_calls, evidence_items, _ = collect_project_evidence(
            sub_question,
            paper_ids=[],  # sub-agents start without specific papers
            allow_web_search=allow_web_search,
            allow_external_search=True,
        )
        finding, _, conflicts, open_qs = build_agent_outputs(
            sub_question, paper_contexts, evidence_items,
        )
        return {
            "subQuestion": sub_question[:120],
            "status": "success",
            "summary": finding.get("summary", "")[:300],
            "verdict": finding.get("verdict", "?"),
            "evidenceCount": len(evidence_items),
            "conflicts": conflicts[:3],
            "openQuestions": open_qs[:3],
            "error": "",
        }
    except Exception as exc:
        return {
            "subQuestion": sub_question[:120],
            "status": "failed",
            "summary": "",
            "error": str(exc)[:200],
        }


# ── Merge ────────────────────────────────────────────────────────────────────

def _merge_parallel_findings(
    question: str, sub_results: list[dict[str, Any]],
) -> dict[str, Any]:
    successful = [r for r in sub_results if r.get("status") == "success"]
    if not successful:
        return {"findings": [], "crossValidation": "", "summary": "无子Agent成功返回结果。"}

    # Collect all findings
    findings = [
        {"subQuestion": r["subQuestion"], "summary": r.get("summary", ""), "verdict": r.get("verdict", "?")}
        for r in successful
    ]

    # Simple cross-validation: check for overlapping keywords across agents
    all_text = " ".join(r.get("summary", "") for r in successful)
    keywords = _extract_keywords(all_text)

    cross_lines = []
    for kw in keywords[:5]:
        agents_with_kw = [r["subQuestion"][:60] for r in successful if kw in r.get("summary", "")]
        if len(agents_with_kw) > 1:
            cross_lines.append(f"- 关键词「{kw}」出现在 {len(agents_with_kw)} 个子Agent中")

    # LLM merge
    summary = _llm_merge(question, findings)

    return {
        "findings": findings,
        "crossValidation": "\n".join(cross_lines) if cross_lines else "各子Agent探索了不同方向，未见显著重叠。",
        "summary": summary,
    }


def _llm_merge(question: str, findings: list[dict[str, Any]]) -> str:
    try:
        from concurrent.futures import ThreadPoolExecutor

        from llm.client import get_llm

        f_str = "\n".join(
            f"- {f['subQuestion'][:100]}: {f['summary'][:200]} [{f.get('verdict','?')}]"
            for f in findings[:10]
        )
        prompt = (
            f"主问题：{question}\n\n"
            f"子问题发现：\n{f_str}\n\n"
            "请用一段中文（200字以内）综合所有子问题的发现，指出共识和分歧。"
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            return (future.result(timeout=20) or "")[:400]
    except Exception:
        return f"{len(findings)} 个子Agent完成研究，详见子结果。"[:200]


def _extract_keywords(text: str) -> list[str]:
    # Simple: words > 3 chars, sorted by frequency
    words = [w.lower() for w in text.split() if len(w) > 3 and w.isalpha()]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=freq.get, reverse=True)


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "question": "", "subResults": [], "mergedFindings": [],
            "crossValidation": "", "agentCount": 0, "error": message}
