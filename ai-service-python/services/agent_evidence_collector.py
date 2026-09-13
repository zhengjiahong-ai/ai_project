"""
Evidence collection functions for the Agent orchestrator.

Extracted from agent_orchestrator.py to keep each module ≤800 lines.
Handles external academic search, web search, and per-paper evidence
collection with progress reporting and cancellation support.
"""

import copy
import re
from collections.abc import Callable
from typing import Any

from services.evidence_service import normalize_evidence_items
from services.external_evidence import normalize_external_evidence_items
from services.external_query_planner import build_external_academic_queries
from services.safety_service import external_search_degradation_reason
from services.trace_service import record_counter, sanitize_text, trace_step

ProgressCallback = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], float, str], None]
CancelCheck = Callable[[], bool]

PROJECT_EVIDENCE_ASPECTS = (
    "dynamic scene method architecture representation deformation training strategy incremental frame",
    "experiments quantitative results efficiency speed memory storage",
    "challenges limitations future work bottlenecks failure cases assumptions",
)
PROJECT_EVIDENCE_PER_QUERY = 2
PROJECT_EVIDENCE_PER_PAPER = 6


def _get_tool_registry():
    from services.tool_registry import get_tool_registry as _get_tool_registry_inner

    return _get_tool_registry_inner()


def invoke_agent_tool(name: str, payload: dict[str, Any], fallback: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    record_counter("retrievalCalls")
    registry = _get_tool_registry()
    definition = registry.get(name)
    audit_meta = {
        "version": definition.version,
        "safetyScope": copy.deepcopy(definition.safetyScope),
    }
    try:
        response = registry.invoke(name, payload)
        normalized = response if isinstance(response, dict) else {}
        return normalized, {"name": name, "status": "succeeded", "meta": {}, **audit_meta}
    except Exception as error:
        return fallback, {
            "name": name,
            "status": "fallback",
            "meta": {"reason": sanitize_text(error, max_chars=180)},
            **audit_meta,
        }


def fallback_tool_result(pdf_id: str) -> dict[str, Any]:
    return {"items": [], "status": "failed", "reason": "indexed_retrieval_unavailable"}


def _build_project_evidence_queries(prompt: str) -> list[str]:
    question = str(prompt or "").strip()
    # The current embedding model is English-first. A long Chinese question can
    # dominate the embedding and push exact method/results sections behind the
    # references. For Chinese questions, use stable English aspect queries; the
    # per-paper filter already provides the document context.
    if re.search(r"[\u3400-\u9fff]", question):
        return list(PROJECT_EVIDENCE_ASPECTS)
    return [f"{question} {aspect}".strip() for aspect in PROJECT_EVIDENCE_ASPECTS]


def _deduplicate_evidence(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("sourceId") or "").strip()
        if not key:
            key = "|".join(
                str(item.get(field) if item.get(field) is not None else "")
                for field in ("pdfId", "pageIndex", "chunkIndex", "text")
            )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def should_try_external_search(
    paper_contexts: list[dict[str, Any]],
    allow_external_search: bool,
) -> bool:
    if not allow_external_search:
        return False
    if not paper_contexts:
        return False
    any_sparse = any(int(item.get("evidenceCount") or 0) <= 1 for item in paper_contexts)
    any_fallback = any(str(item.get("status") or "") == "fallback" for item in paper_contexts)
    return any_sparse or any_fallback


def build_external_search_queries(
    prompt: str,
    paper_contexts: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
) -> list[str]:
    # Lazy import to avoid circular dependency at module level.
    from services.agent_reasoning import clean_text

    sparse_papers = [
        item for item in paper_contexts
        if int(item.get("evidenceCount") or 0) <= 1 or str(item.get("status") or "") == "fallback"
    ]
    if not sparse_papers:
        return []

    missing_aspects = []
    for item in sparse_papers:
        pdf_id = clean_text(item.get("pdfId")) or "unknown-paper"
        missing_aspects.append(f"evidence gap for {pdf_id}")

    # Try LLM-driven query generation first; fall back to rule-based
    try:
        from services.external_query_planner import build_llm_academic_queries
        llm_queries = build_llm_academic_queries(
            research_question=prompt,
            evidence_gaps=missing_aspects,
        )
        if llm_queries:
            return llm_queries
    except Exception:
        pass

    sub_questions = []
    seen_ids = set()
    for item in paper_contexts:
        pdf_id = clean_text(item.get("pdfId"))
        if pdf_id and pdf_id not in seen_ids:
            seen_ids.add(pdf_id)
            sub_questions.append(pdf_id)

    return build_external_academic_queries(
        research_question=prompt,
        planner_sub_questions=sub_questions,
        missing_aspects=missing_aspects,
    )


def retrieve_external_agent_evidence(
    queries: list[str],
    limit_per_query: int = 3,
) -> dict[str, Any]:
    if not queries:
        return {"status": "no_queries", "provider": "disabled", "items": [], "degradation": "", "external_tool_calls": []}

    all_items: list = []
    final_status = "success"
    provider = "disabled"
    degradation = ""
    external_tool_calls: list = []

    for query_index, query in enumerate(queries):
        try:
            result, tool_call = invoke_agent_tool(
                "retrieve_external_academic",
                {"query": query, "limit": limit_per_query},
                fallback={"status": "failed", "provider": "disabled", "items": []},
            )
        except Exception:
            final_status = "failed"
            degradation = external_search_degradation_reason(final_status)
            break

        if tool_call.get("status") == "fallback":
            tool_call = copy.deepcopy(tool_call)
            tool_call["meta"] = {**(tool_call.get("meta") or {}), "reason": "tool_invocation_error"}

        external_tool_calls.append({
            "id": f"retrieve-external-academic-{query_index + 1}",
            **tool_call,
        })

        status = str(result.get("status") or "failed")
        if status == "success":
            provider = str(result.get("provider") or "unknown")
            items = list(result.get("items") or [])
            all_items.extend(items)
        elif status == "disabled":
            final_status = "disabled"
            degradation = external_search_degradation_reason(status, result.get("reason"))
            break
        elif status == "budget_exceeded":
            final_status = "budget_exceeded"
            degradation = external_search_degradation_reason(status, result.get("reason"))
            break
        else:
            final_status = status
            degradation = external_search_degradation_reason(status, result.get("reason"))
            break

    normalized_items = normalize_external_evidence_items(all_items, limit=12)

    return {
        "status": final_status,
        "provider": provider,
        "items": normalized_items,
        "degradation": degradation,
        "external_tool_calls": external_tool_calls,
    }


def should_try_web_search_agent(
    paper_contexts: list[dict[str, Any]],
    allow_web_search: bool,
) -> bool:
    if not allow_web_search:
        return False
    if not paper_contexts:
        return False
    any_sparse = any(int(item.get("evidenceCount") or 0) <= 1 for item in paper_contexts)
    any_fallback = any(str(item.get("status") or "") == "fallback" for item in paper_contexts)
    return any_sparse or any_fallback


def build_web_search_queries_agent(
    prompt: str,
    paper_contexts: list[dict[str, Any]],
) -> list[str]:
    # Lazy import to avoid circular dependency at module level.
    from services.agent_reasoning import clean_text
    from services.external_query_planner import (
        build_web_search_queries as _build_web_search_queries,
    )
    from services.external_query_planner import refine_search_queries

    sparse_papers = [
        item for item in paper_contexts
        if int(item.get("evidenceCount") or 0) <= 1 or str(item.get("status") or "") == "fallback"
    ]
    if not sparse_papers:
        return []

    missing_aspects = []
    for item in sparse_papers:
        pdf_id = clean_text(item.get("pdfId")) or "unknown-paper"
        missing_aspects.append(f"supplementary evidence for {pdf_id}")

    # Try LLM-driven query refinement first; fall back to rule-based
    try:
        llm_queries = refine_search_queries(
            research_question=prompt,
            previous_results=[],
            missing_aspects=missing_aspects,
        )
        if llm_queries:
            return llm_queries
    except Exception:
        pass

    return _build_web_search_queries(
        research_question=prompt,
        missing_aspects=missing_aspects,
    )


def retrieve_web_agent_evidence(
    queries: list[str],
    limit_per_query: int = 4,
) -> dict[str, Any]:
    if not queries:
        return {"status": "no_queries", "provider": "disabled", "items": [], "degradation": "", "web_tool_calls": []}

    all_items: list = []
    final_status = "success"
    provider = "disabled"
    degradation = ""
    web_tool_calls: list = []

    for query_index, query in enumerate(queries):
        try:
            result, tool_call = invoke_agent_tool(
                "search_web",
                {"query": query, "limit": limit_per_query},
                fallback={"status": "failed", "provider": "disabled", "items": []},
            )
        except Exception:
            final_status = "failed"
            degradation = external_search_degradation_reason(final_status)
            break

        if tool_call.get("status") == "fallback":
            tool_call = copy.deepcopy(tool_call)
            tool_call["meta"] = {**(tool_call.get("meta") or {}), "reason": "tool_invocation_error"}

        web_tool_calls.append({
            "id": f"search-web-{query_index + 1}",
            **tool_call,
        })

        status = str(result.get("status") or "failed")
        if status == "success":
            provider = str(result.get("provider") or "unknown")
            items = list(result.get("items") or [])
            all_items.extend(items)
        elif status in ("disabled", "budget_exceeded"):
            final_status = status
            degradation = external_search_degradation_reason(status, result.get("reason"))
            break
        else:
            final_status = status
            degradation = external_search_degradation_reason(status, result.get("reason"))
            break

    normalized_items = normalize_external_evidence_items(all_items, limit=12)

    return {
        "status": final_status,
        "provider": provider,
        "items": normalized_items,
        "degradation": degradation,
        "web_tool_calls": web_tool_calls,
    }


def collect_project_evidence(
    prompt: str,
    paper_ids: list[str],
    *,
    allow_external_search: bool = False,
    allow_web_search: bool = False,
    allow_iterative_search: bool = False,
    allow_knowledge_graph: bool = True,  # 17-2
    should_cancel: CancelCheck | None = None,
    on_progress: ProgressCallback | None = None,
    domain_config: dict | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    # Lazy imports to avoid circular dependency with agent_orchestrator.
    from services.agent_orchestrator import _timeline_step
    from services.agent_reasoning import clean_text
    from services.agent_report_sections import evidence_preview, stabilize_source_ids

    paper_contexts: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    research_timeline: list[dict[str, Any]] = []

    # Apply domain-specific search queries if available
    domain_queries = (domain_config or {}).get("searchQueries") or []
    if domain_queries and should_cancel is None:
        research_timeline.append(_timeline_step(
            "domain_activated",
            f"Domain specialist activated: {(domain_config or {}).get('domain', '')}",
            f"Tools: {', '.join((domain_config or {}).get('tools', [])[:8])}",
        ))

    for index, pdf_id in enumerate(paper_ids):
        if should_cancel and should_cancel():
            break
        with trace_step(
            "agent_collect_paper_evidence",
            input_size=len(prompt),
            meta={"pdfId": sanitize_text(pdf_id, max_chars=80)},
        ) as step:
            query_calls: list[dict[str, Any]] = []
            candidate_items: list[dict[str, Any]] = []
            for query in _build_project_evidence_queries(prompt):
                tool_result, query_call = invoke_agent_tool(
                    "retrieve_current_paper",
                    {
                        "pdfId": pdf_id,
                        "query": query,
                        "topK": 8,
                        "limit": PROJECT_EVIDENCE_PER_QUERY,
                        "maxTextChars": 700,
                    },
                    fallback=fallback_tool_result(pdf_id),
                )
                query_calls.append(query_call)
                candidate_items.extend(normalize_evidence_items(
                    tool_result.get("items") or [],
                    source_type="current_paper",
                    pdf_id=pdf_id,
                    limit=PROJECT_EVIDENCE_PER_QUERY,
                    max_text_chars=700,
                ))
            items = stabilize_source_ids(
                _deduplicate_evidence(candidate_items, PROJECT_EVIDENCE_PER_PAPER),
                fallback_prefix=pdf_id,
            )
            succeeded_calls = [call for call in query_calls if call.get("status") != "fallback"]
            tool_call = copy.deepcopy(succeeded_calls[0] if succeeded_calls else query_calls[0])
            tool_call["meta"] = {
                **(tool_call.get("meta") or {}),
                "queryCount": len(query_calls),
                "failedQueryCount": sum(call.get("status") == "fallback" for call in query_calls),
            }
            evidence_items.extend(items)
            paper_contexts.append(
                {
                    "pdfId": pdf_id,
                    "evidenceCount": len(items),
                    "sourceIds": [item.get("sourceId") for item in items if item.get("sourceId")],
                    "preview": evidence_preview(items),
                    "status": tool_call["status"],
                }
            )
            tool_calls.append(
                {
                    **tool_call,
                    "id": f"retrieve-current-paper-{index + 1}",
                    "target": pdf_id,
                    "result": f"Collected {len(items)} evidence items for {pdf_id}.",
                }
            )
            step["outputSize"] = len(items)
        progress = 0.45 + (0.22 * ((index + 1) / max(1, len(paper_ids))))
        if on_progress:
            on_progress(
                copy.deepcopy(tool_calls),
                copy.deepcopy(evidence_items[:12]),
                copy.deepcopy(paper_contexts),
                round(progress, 2),
                pdf_id,
            )

    # Add paper retrieval summary step
    papers_with_evidence = sum(1 for c in paper_contexts if int(c.get("evidenceCount") or 0) > 0)
    research_timeline.append(_timeline_step(
        "retrieve",
        f"从 {len(paper_ids)} 篇项目论文中检索证据",
        f"{papers_with_evidence}/{len(paper_ids)} 篇论文返回证据片段，共收集 {len(evidence_items)} 条",
        "success",
    ))

    if should_try_external_search(paper_contexts, allow_external_search):
        if not (should_cancel and should_cancel()):
            with trace_step(
                "agent_external_search",
                input_size=len(prompt),
                meta={"sparsePaperCount": sum(1 for item in paper_contexts if int(item.get("evidenceCount") or 0) <= 1)},
            ) as ext_step:
                queries = build_external_search_queries(prompt, paper_contexts, evidence_items)
                ext_result = retrieve_external_agent_evidence(queries)
                external_evidence = ext_result.get("items") or []
                external_tool_calls = ext_result.get("external_tool_calls") or []
                ext_step["outputSize"] = len(external_evidence)
                ext_step["meta"] = {
                    **ext_step.get("meta", {}),
                    "status": ext_result.get("status"),
                    "provider": ext_result.get("provider"),
                    "degradation": ext_result.get("degradation"),
                }

                if external_evidence:
                    evidence_items.extend(external_evidence)
                    evidence_items = evidence_items[:24]
                if external_tool_calls:
                    tool_calls.extend(external_tool_calls)

                if on_progress:
                    on_progress(
                        copy.deepcopy(tool_calls),
                        copy.deepcopy(evidence_items[:12]),
                        copy.deepcopy(paper_contexts),
                        0.69,
                        "external_academic",
                    )

                research_timeline.append(_timeline_step(
                    "search",
                    "外部学术检索",
                    f"Provider: {ext_result.get('provider', 'unknown')}, 状态: {ext_result.get('status', 'unknown')}, 获得 {len(external_evidence)} 条证据",
                    "success" if external_evidence else "error",
                ))

    if should_try_web_search_agent(paper_contexts, allow_web_search):
        if not (should_cancel and should_cancel()):
            if allow_iterative_search:
                # Iterative search loop: search → fetch → judge → repeat
                with trace_step(
                    "agent_iterative_search",
                    input_size=len(prompt),
                    meta={"sparsePaperCount": sum(1 for item in paper_contexts if int(item.get("evidenceCount") or 0) <= 1), "mode": "iterative"},
                ) as loop_step:
                    sparse_papers = [
                        item for item in paper_contexts
                        if int(item.get("evidenceCount") or 0) <= 1 or str(item.get("status") or "") == "fallback"
                    ]
                    missing_aspects = [
                        f"supplementary evidence for {clean_text(item.get('pdfId')) or 'unknown-paper'}"
                        for item in sparse_papers
                    ]
                    sub_question = "supplementary web evidence for project papers"
                    query_plan = {"keywords": [clean_text(prompt)[:80]], "paperIds": paper_ids}

                    def _iter_on_progress(iteration, pages_fetched, confidence):
                        if on_progress:
                            on_progress(
                                copy.deepcopy(tool_calls),
                                copy.deepcopy(evidence_items[:12]),
                                copy.deepcopy(paper_contexts),
                                0.69 + (0.03 * min(iteration, 3)),
                                "web_search_iterative",
                            )

                    from services.agentic_search_loop import run_agentic_search_loop

                    loop_result = run_agentic_search_loop(
                        question=prompt,
                        sub_question=sub_question,
                        missing_aspects=missing_aspects,
                        query_plan=query_plan,
                        should_cancel=should_cancel,
                        on_progress=_iter_on_progress,
                    )
                    loop_evidence = loop_result.get("evidence_items") or []
                    loop_step["outputSize"] = len(loop_evidence)
                    loop_step["meta"] = {
                        **loop_step.get("meta", {}),
                        "iterations": loop_result.get("iterations", 0),
                        "verdict": loop_result.get("verdict"),
                        "web_search_used": loop_result.get("web_search_used"),
                        "pages_fetched": loop_result.get("pages_fetched"),
                        "status": "success" if loop_evidence else "no_results",
                    }

                    if loop_evidence:
                        evidence_items.extend(loop_evidence)
                        evidence_items = evidence_items[:24]

                    if on_progress:
                        on_progress(
                            copy.deepcopy(tool_calls),
                            copy.deepcopy(evidence_items[:12]),
                            copy.deepcopy(paper_contexts),
                            0.72,
                            "web_search_iterative",
                        )

                    research_timeline.append(_timeline_step(
                        "search",
                        "迭代 Web 搜索完成",
                        f"{loop_result.get('iterations', 0)} 轮迭代, {loop_result.get('pages_fetched', 0)} 页抓取, verdict: {loop_result.get('verdict', 'unknown')}",
                        "success" if loop_evidence else "error",
                    ))
            else:
                # Simple single-pass web search (existing behavior)
                with trace_step(
                    "agent_web_search",
                    input_size=len(prompt),
                    meta={"sparsePaperCount": sum(1 for item in paper_contexts if int(item.get("evidenceCount") or 0) <= 1)},
                ) as web_step:
                    web_queries = build_web_search_queries_agent(prompt, paper_contexts)
                    web_result = retrieve_web_agent_evidence(web_queries)
                    web_evidence = web_result.get("items") or []
                    web_tool_calls = web_result.get("web_tool_calls") or []
                    web_step["outputSize"] = len(web_evidence)
                    web_step["meta"] = {
                        **web_step.get("meta", {}),
                        "status": web_result.get("status"),
                        "provider": web_result.get("provider"),
                        "degradation": web_result.get("degradation"),
                    }

                    if web_evidence:
                        evidence_items.extend(web_evidence)
                        evidence_items = evidence_items[:24]
                    if web_tool_calls:
                        tool_calls.extend(web_tool_calls)

                    if on_progress:
                        on_progress(
                            copy.deepcopy(tool_calls),
                            copy.deepcopy(evidence_items[:12]),
                            copy.deepcopy(paper_contexts),
                            0.72,
                            "web_search",
                        )

                    research_timeline.append(_timeline_step(
                        "search",
                        "Web 搜索完成",
                        f"Provider: {web_result.get('provider', 'unknown')}, 获得 {len(web_evidence)} 条证据",
                        "success" if web_evidence else "error",
                    ))

    # 16-2/17-2: supplement sparse papers with knowledge-graph neighbourhood.
    if allow_knowledge_graph:
        try:
            sparse_ids = [
                ctx.get("pdfId") for ctx in paper_contexts
                if int(ctx.get("evidenceCount") or 0) <= 1 and ctx.get("pdfId")
            ]
            if sparse_ids:
                from services.knowledge_graph_store import read_graph_neighborhood

                kg_result = read_graph_neighborhood({
                    "paperIds": sparse_ids,
                    "seedTerms": [],
                    "sourceIds": [],
                    "maxNodes": 6,
                    "maxEdges": 8,
                })
                kg_nodes = kg_result.get("nodes") or []
                if kg_nodes:
                    kg_evidence = [
                        {
                            "sourceId": f"kg-{n.get('node_id', '?')}",
                            "text": f"[图谱推导] {n.get('label', '')} ({n.get('node_type', 'concept')})",
                            "sourceType": "knowledge_graph",
                            "pdfId": sparse_ids[0] if len(sparse_ids) == 1 else "",
                            "pageIndex": None,
                            "metadata": {"graph_derived": True, "confidence": n.get("confidence", 0.5)},
                        }
                        for n in kg_nodes[:4]
                    ]
                    evidence_items.extend(kg_evidence)
                    research_timeline.append(_timeline_step(
                        "knowledge_graph",
                        "图谱补充",
                        f"从知识图谱补充 {len(kg_evidence)} 条邻域证据 (papers: {', '.join(sparse_ids[:3])})",
                        "success" if kg_evidence else "warning",
                    ))
        except Exception:
            pass  # graph lookup is best-effort

    # 14-2: enrich final evidence list with structured credibility scores.
    enriched = evidence_items[:12]
    try:
        from services.evidence_credibility import enrich_evidence_with_credibility

        enriched = enrich_evidence_with_credibility(enriched)
    except Exception:
        pass  # credibility enrichment is best-effort; never blocks evidence return

    return paper_contexts, tool_calls, enriched, research_timeline
