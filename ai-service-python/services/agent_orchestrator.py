import copy
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.evidence_service import normalize_evidence_items
from services.external_evidence import EXTERNAL_SOURCE_TYPE, normalize_external_evidence_items
from services.external_query_planner import build_external_academic_queries
from services.knowledge_graph_store import enrich_conflicts_with_graph_context
from services.safety_service import external_search_degradation_reason
from services.trace_service import record_counter, sanitize_text, trace_step


ProgressCallback = Callable[[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], float, str], None]
CancelCheck = Callable[[], bool]


def get_tool_registry():
    from services.tool_registry import get_tool_registry as _get_tool_registry

    return _get_tool_registry()


def build_plan_items(paper_ids: List[str], active_step: str = "scope") -> List[Dict[str, Any]]:
    status_by_step = {
        "scope": "pending",
        "retrieve": "pending",
        "synthesize": "pending",
    }
    if active_step == "scope":
        status_by_step["scope"] = "running"
    elif active_step == "retrieve":
        status_by_step["scope"] = "done"
        status_by_step["retrieve"] = "running"
    elif active_step == "synthesize":
        status_by_step["scope"] = "done"
        status_by_step["retrieve"] = "done"
        status_by_step["synthesize"] = "running"
    elif active_step == "done":
        status_by_step = {key: "done" for key in status_by_step}
    return [
        _plan_item("scope", "Confirm scope", "Resolve focused papers and project constraints.", status_by_step["scope"]),
        _plan_item("retrieve", "Collect evidence", f"Retrieve reusable evidence from {len(paper_ids)} project papers.", status_by_step["retrieve"]),
        _plan_item("synthesize", "Judge and compare", "Build cross-paper judgements, conflict candidates, and a draft report.", status_by_step["synthesize"]),
    ]


def build_review_plan_items(prompt: str, paper_ids: List[str], constraints: str = "") -> List[Dict[str, Any]]:
    return normalize_review_plan_items([
        {"id": "evidence", "label": "Collect claim-level evidence", "detail": f"Retrieve evidence for: {clean_text(prompt)}"},
        {"id": "compare", "label": "Compare focused papers", "detail": f"Compare methods and results across {len(paper_ids)} papers."},
        {"id": "risks", "label": "Review conflicts and gaps", "detail": clean_text(constraints) or "Surface conflicts and missing evidence before finalization."},
        {"id": "external", "label": "External academic search", "detail": "When enabled, supplement sparse evidence with read-only external academic metadata from whitelisted academic providers.", "allowExternalSearch": False},
        {"id": "experiment", "label": "Code execution experiment", "detail": "When enabled, the Agent may propose descriptive statistics on approved CSV artifacts. Execution requires human approval and runs without network access.", "allowCodeExecution": False},
    ])


def normalize_review_plan_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for index, item in enumerate(items or [], 1):
        label = clean_text(item.get("label"))
        if not label:
            continue
        plan_item = {
            "id": clean_text(item.get("id")) or f"plan-{index}",
            "label": label[:120],
            "detail": clean_text(item.get("detail"))[:300],
            "status": "pending",
        }
        if "allowExternalSearch" in item:
            plan_item["allowExternalSearch"] = bool(item.get("allowExternalSearch"))
        if "allowCodeExecution" in item:
            plan_item["allowCodeExecution"] = bool(item.get("allowCodeExecution"))
        normalized.append(plan_item)
        if len(normalized) >= 8:
            break
    return normalized


def update_plan_status(items: List[Dict[str, Any]], status: str) -> List[Dict[str, Any]]:
    return [{**copy.deepcopy(item), "status": status} for item in items]


def build_execution_prompt(prompt: str, plan_items: List[Dict[str, Any]], constraints: str) -> str:
    directives = "; ".join(f"{clean_text(item.get('label'))}: {clean_text(item.get('detail'))}" for item in plan_items)
    parts = [clean_text(prompt), f"Approved plan: {directives}"]
    if clean_text(constraints):
        parts.append(f"Constraints: {clean_text(constraints)}")
    return "\n".join(item for item in parts if item)


def build_planning_context(project: Dict[str, Any], paper_ids: List[str], constraints: str) -> str:
    parts = [
        f"project={project.get('title')}",
        f"goal={project.get('goal')}",
        f"paper_count={len(paper_ids)}",
    ]
    if constraints:
        parts.append(f"constraints={constraints}")
    return "\n".join(parts)


def should_try_external_search(
    paper_contexts: List[Dict[str, Any]],
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
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[str]:
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
    queries: List[str],
    limit_per_query: int = 3,
) -> Dict[str, Any]:
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
    paper_contexts: List[Dict[str, Any]],
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
    paper_contexts: List[Dict[str, Any]],
) -> List[str]:
    from services.external_query_planner import build_web_search_queries as _build_web_search_queries

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

    return _build_web_search_queries(
        research_question=prompt,
        missing_aspects=missing_aspects,
    )


def retrieve_web_agent_evidence(
    queries: List[str],
    limit_per_query: int = 4,
) -> Dict[str, Any]:
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
    paper_ids: List[str],
    *,
    allow_external_search: bool = False,
    allow_web_search: bool = False,
    allow_iterative_search: bool = False,
    should_cancel: CancelCheck | None = None,
    on_progress: ProgressCallback | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    paper_contexts: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    evidence_items: List[Dict[str, Any]] = []

    for index, pdf_id in enumerate(paper_ids):
        if should_cancel and should_cancel():
            break
        with trace_step(
            "agent_collect_paper_evidence",
            input_size=len(prompt),
            meta={"pdfId": sanitize_text(pdf_id, max_chars=80)},
        ) as step:
            tool_result, tool_call = invoke_agent_tool(
                "retrieve_current_paper",
                {
                    "pdfId": pdf_id,
                    "query": prompt,
                    "topK": 6,
                    "limit": 3,
                    "maxTextChars": 420,
                },
                fallback=fallback_tool_result(pdf_id),
            )
            items = normalize_evidence_items(
                tool_result.get("items") or [],
                source_type="current_paper",
                pdf_id=pdf_id,
                limit=3,
                max_text_chars=420,
            )
            items = stabilize_source_ids(items, fallback_prefix=pdf_id)
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

    return paper_contexts, tool_calls, evidence_items[:12]


def build_agent_outputs(
    prompt: str,
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[str]]:
    source_ids = [item.get("sourceId") for item in evidence_items if item.get("sourceId")]
    paper_ids = [item.get("pdfId") for item in paper_contexts if item.get("pdfId")]
    external_evidence_count = sum(
        1 for item in evidence_items
        if str(item.get("sourceType") or "") == EXTERNAL_SOURCE_TYPE
    )

    finding = {
        "id": "project-synthesis-1",
        "summary": build_finding_summary(prompt, paper_contexts, evidence_items),
        "sourceIds": source_ids[:8],
        "status": "draft",
        "externalEvidenceCount": external_evidence_count,
    }
    comparison_table = {
        "columns": ["paperId", "evidenceCount", "retrievalStatus", "judgement", "evidencePreview"],
        "rows": [
            [
                item.get("pdfId"),
                item.get("evidenceCount", 0),
                item.get("status", "unknown"),
                build_paper_judgement(item),
                item.get("preview", ""),
            ]
            for item in paper_contexts
        ],
    }
    conflicts = enrich_conflicts_with_graph_context(detect_conflicts(paper_contexts, evidence_items))
    open_questions = []
    for item in paper_contexts:
        if item.get("evidenceCount", 0) <= 1:
            open_questions.append(f"Need denser evidence coverage for {item.get('pdfId')}.")
    if not paper_ids:
        open_questions.append("No papers are attached to the project yet.")
    if not evidence_items:
        open_questions.append("Project retrieval returned no indexed evidence and is running on fallback summaries.")
    if not open_questions:
        open_questions.append("Next round can deepen claim-level judging with stronger section-aware evidence.")
    return finding, comparison_table, conflicts, open_questions[:5]


def invoke_agent_tool(name: str, payload: Dict[str, Any], fallback: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    record_counter("retrievalCalls")
    registry = get_tool_registry()
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


def fallback_tool_result(pdf_id: str) -> Dict[str, Any]:
    return {
        "items": [
            {
                "sourceId": f"{pdf_id}-fallback-1",
                "text": f"Fallback project evidence placeholder for {pdf_id}. Indexed retrieval can replace this in later rounds.",
                "pdfId": pdf_id,
                "chunkIndex": None,
                "pageIndex": None,
                "sectionId": None,
                "metadata": {"fallback": True, "stage": "round_2"},
            }
        ]
    }


def build_minimal_report(
    prompt: str,
    project: Dict[str, Any],
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    open_questions: List[str],
    code_execution_results: Optional[List[Dict[str, Any]]] = None,
) -> str:
    paper_lines = "\n".join(build_scope_lines(paper_contexts)) or "- No project papers selected"
    evidence_lines = "\n".join(build_evidence_snapshot_lines(evidence_items)) or "- No evidence snippets yet"
    conclusion_lines = "\n".join(build_conclusion_lines(prompt, paper_contexts, evidence_items))
    question_lines = "\n".join(f"- {item}" for item in open_questions[:4]) or "- None"
    conflict_lines = "\n".join(build_conflict_lines(conflicts)) or "- No strong conflict candidates detected in this pass"
    external_lines = _build_external_evidence_section_lines(evidence_items) or ""

    external_section = ""
    if external_lines:
        has_web = any(
            str(item.get("sourceType") or "") == "web_search"
            for item in evidence_items
        )
        heading = "## External Evidence (Academic + Web)" if has_web else "## External Academic Evidence"
        external_section = (
            f"{heading}\n"
            f"{external_lines}\n\n"
        )

    code_section = ""
    if code_execution_results:
        code_lines = _build_code_execution_section_lines(code_execution_results)
        if code_lines:
            code_section = (
                "## Code-Computed Artifacts\n"
                f"{code_lines}\n\n"
            )

    return (
        "# Agent Research Draft\n\n"
        f"## Task\n{prompt}\n\n"
        f"## Project\n{project.get('title')}\n\n"
        f"## Scope\n{paper_lines}\n\n"
        "## Evidence Snapshot\n"
        f"{evidence_lines}\n\n"
        f"{external_section}"
        f"{code_section}"
        "## Current Conclusion\n"
        f"{conclusion_lines}\n\n"
        "## Conflict Candidates\n"
        f"{conflict_lines}\n\n"
        "## Open Questions\n"
        f"{question_lines}\n"
    )


def build_finding_summary(prompt: str, paper_contexts: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> str:
    paper_count = len(paper_contexts)
    evidence_count = len(evidence_items)
    support_profiles = build_paper_support_profiles(paper_contexts, evidence_items)
    if support_profiles:
        support_text = "; ".join(
            f"{item['pdfId']} has {item['evidenceCount']} snippets focused on {item['theme']}"
            for item in support_profiles[:3]
        )
        return (
            f"For '{prompt}', the Agent synthesized {evidence_count} normalized evidence items across {paper_count} papers. "
            f"The strongest current support is: {support_text}."
        )
    return (
        f"For '{prompt}', the Agent workspace has completed the end-to-end project chain across {paper_count} papers, "
        f"but the evidence set is still sparse and should be strengthened in later rounds."
    )


def evidence_preview(evidence_items: List[Dict[str, Any]]) -> str:
    snippets = []
    for item in evidence_items[:2]:
        text = clean_text(item.get("text"))
        if text:
            snippets.append(text[:80])
    return " | ".join(snippets)


def stabilize_source_ids(items: List[Dict[str, Any]], fallback_prefix: str) -> List[Dict[str, Any]]:
    stabilized = []
    for index, item in enumerate(items):
        current = copy.deepcopy(item)
        source_id = clean_text(current.get("sourceId"))
        if not source_id:
            source_id = f"{fallback_prefix}-source-{index + 1}"
        current["sourceId"] = source_id[:80]
        stabilized.append(current)
    return stabilized


def build_paper_judgement(paper_context: Dict[str, Any]) -> str:
    evidence_count = int(paper_context.get("evidenceCount") or 0)
    status = clean_text(paper_context.get("status")) or "unknown"
    if evidence_count >= 3 and status == "succeeded":
        return "Evidence is dense enough for cross-paper judgement."
    if evidence_count >= 1:
        return "Evidence is usable, but section coverage is still uneven."
    return "Evidence is too sparse for a confident judgement."


def build_scope_lines(paper_contexts: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for item in paper_contexts:
        pdf_id = clean_text(item.get("pdfId")) or "unknown-paper"
        evidence_count = int(item.get("evidenceCount") or 0)
        preview = clean_text(item.get("preview"))[:120]
        preview_suffix = f" Preview: {preview}" if preview else ""
        lines.append(f"- `{pdf_id}`: {evidence_count} evidence snippets.{preview_suffix}")
    return lines


def build_evidence_snapshot_lines(evidence_items: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for item in evidence_items[:6]:
        source_type = str(item.get("sourceType") or "")
        if source_type == EXTERNAL_SOURCE_TYPE:
            pdf_id = clean_text(item.get("provider")) or "external"
            section_id = str(item.get("year") or "unknown")
            external_label = "（含外部学术检索）"
            text = clean_text(item.get("title") or item.get("text"))[:140]
            lines.append(f"- `{pdf_id}` ({section_id}){external_label}: {text}")
        else:
            pdf_id = clean_text(item.get("pdfId")) or "unknown-paper"
            section_id = clean_text(item.get("sectionId")) or "unknown-section"
            text = clean_text(item.get("text"))[:160]
            lines.append(f"- `{pdf_id}` / `{section_id}`: {text}")
    return lines


def _build_external_evidence_section_lines(evidence_items: List[Dict[str, Any]]) -> str:
    external_items = [
        item for item in evidence_items
        if str(item.get("sourceType") or "") in {EXTERNAL_SOURCE_TYPE, "web_search"}
    ]
    if not external_items:
        return ""
    lines = []
    for item in external_items[:6]:
        provider = clean_text(item.get("provider")) or "unknown"
        title = clean_text(item.get("title")) or "Untitled"
        year = item.get("year") or "unknown"
        doi = clean_text(item.get("doi"))
        url = clean_text(item.get("url"))
        doi_url = f" https://doi.org/{doi}" if doi else (f" {url}" if url else "")
        retrieved = clean_text(item.get("retrievedAt")) or ""
        source_type = str(item.get("sourceType") or "")
        type_label = " [web]" if source_type == "web_search" else ""
        lines.append(
            f"- [{provider}]{type_label} {title} ({year}){doi_url}"
            + (f" (retrieved {retrieved})" if retrieved else "")
        )
    return "\n".join(lines)


def _build_code_execution_section_lines(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""
    lines = []
    for result in results:
        artifact_id = clean_text(result.get("artifactId")) or "unknown"
        job_id = clean_text(result.get("jobId")) or "unknown"
        row_count = result.get("rowCount")
        column_count = result.get("columns")
        lines.append(
            f"- [{job_id}] Descriptive statistics for `{artifact_id}`"
            + (f" ({row_count} rows, {column_count} columns)" if row_count is not None else "")
            + " — code-computed artifact, not original paper evidence."
        )
    return "\n".join(lines)


def build_paper_support_profiles(
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in evidence_items:
        pdf_id = clean_text(item.get("pdfId"))
        if not pdf_id:
            continue
        grouped.setdefault(pdf_id, []).append(item)

    profiles = []
    for paper_context in paper_contexts:
        pdf_id = clean_text(paper_context.get("pdfId"))
        evidence_for_paper = grouped.get(pdf_id, [])
        profiles.append(
            {
                "pdfId": pdf_id,
                "evidenceCount": int(paper_context.get("evidenceCount") or len(evidence_for_paper)),
                "theme": infer_theme_from_evidence(evidence_for_paper),
                "status": clean_text(paper_context.get("status")) or "unknown",
            }
        )
    return sorted(profiles, key=lambda item: item["evidenceCount"], reverse=True)


def build_conclusion_lines(
    prompt: str,
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[str]:
    if not paper_contexts:
        return ["- No project papers are attached yet, so a project-level conclusion cannot be formed."]

    profiles = build_paper_support_profiles(paper_contexts, evidence_items)
    strongest = [item for item in profiles if item["evidenceCount"] >= 2]
    sparse = [item for item in profiles if item["evidenceCount"] <= 1]
    fallback = [item for item in profiles if item["status"] == "fallback"]
    common_themes = extract_common_themes(profiles)

    lines = []
    if strongest:
        top_summary = "; ".join(
            f"`{item['pdfId']}` mainly surfaces {item['theme']}"
            for item in strongest[:3]
        )
        lines.append(f"- For '{prompt}', the best-supported current conclusion comes from {top_summary}.")

    if common_themes:
        lines.append(
            "- Across the current evidence, the recurring discussion centers on "
            + ", ".join(common_themes[:4])
            + "."
        )

    if strongest and sparse:
        lines.append(
            "- The comparison is already directionally useful, but it is still imbalanced because some papers have much denser evidence than others."
        )
    elif strongest:
        lines.append(
            "- The retrieved evidence is strong enough to support a first-pass comparison, especially on papers with denser method and experiment snippets."
        )
    else:
        lines.append(
            "- The current evidence mostly supports a scoping conclusion rather than a strong claim about methodological differences."
        )

    if fallback:
        fallback_text = ", ".join(f"`{item['pdfId']}`" for item in fallback[:3])
        lines.append(
            f"- Some conclusions remain provisional because {fallback_text} is still using fallback evidence rather than indexed retrieval."
        )

    return lines


def build_conflict_lines(conflicts: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for item in conflicts[:4]:
        severity = clean_text(item.get("severity")) or "unknown"
        summary = clean_text(item.get("summary"))
        claim = clean_text(item.get("claim"))
        papers = [paper for paper in item.get("papers") or [] if clean_text(paper)]
        paper_text = f" Papers: {', '.join(papers[:4])}." if papers else ""
        claim_text = f" Claim: {claim}." if claim else ""
        graph_context = item.get("graphContext") if isinstance(item.get("graphContext"), dict) else {}
        graph_text = ""
        if graph_context:
            graph_text = (
                f" Graph context: {graph_context.get('status') or 'unavailable'} with "
                f"{len(graph_context.get('nodes') or [])} nodes; this conflict was not automatically adjudicated "
                "and still requires manual review."
            )
        lines.append(f"- [{severity}] {summary}{claim_text}{paper_text}{graph_text}")
    return lines


def infer_theme_from_evidence(evidence_items: List[Dict[str, Any]]) -> str:
    if not evidence_items:
        return "limited evidence"

    section_ids = [
        clean_text(item.get("sectionId")).lower()
        for item in evidence_items
        if clean_text(item.get("sectionId"))
    ]
    for preferred in ("method", "experiment", "results", "discussion", "conclusion"):
        if preferred in section_ids:
            return preferred

    joined = " ".join(clean_text(item.get("text")) for item in evidence_items[:4])
    keywords = extract_keywords(joined)
    if keywords:
        return ", ".join(keywords[:2])
    return "paper-level evidence"


def extract_common_themes(profiles: List[Dict[str, Any]]) -> List[str]:
    counts: Dict[str, int] = {}
    for profile in profiles:
        for part in [item.strip() for item in str(profile.get("theme") or "").split(",")]:
            if not part or part == "limited evidence":
                continue
            counts[part] = counts.get(part, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [item[0] for item in ordered]


def extract_keywords(text: str) -> List[str]:
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "into", "about", "their",
        "method", "methods", "result", "results", "paper", "study", "using", "used",
        "shows", "show", "based", "current", "evidence", "section", "discussion",
    }
    counts: Dict[str, int] = {}
    for token in re.findall(r"[a-zA-Z][a-zA-Z_-]{3,}", text.lower()):
        if token in stopwords:
            continue
        counts[token] = counts.get(token, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [item[0].replace("_", " ").replace("-", " ") for item in ordered[:5]]


def detect_conflicts(paper_contexts: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(paper_contexts) < 2:
        return []

    conflicts: List[Dict[str, Any]] = []
    sparse = [item for item in paper_contexts if int(item.get("evidenceCount") or 0) <= 1]
    strong = [item for item in paper_contexts if int(item.get("evidenceCount") or 0) >= 3]
    fallback_contexts = [item for item in paper_contexts if item.get("status") == "fallback"]

    if sparse and strong:
        conflicts.append(
            {
                "id": "evidence-coverage-conflict",
                "severity": "medium",
                "claim": "Cross-paper conclusion may over-weight papers with denser retrieved evidence.",
                "papers": [*(item.get("pdfId") for item in strong[:2]), *(item.get("pdfId") for item in sparse[:2])],
                "summary": "Some papers have strong evidence coverage while others are sparse, so the comparison should separate evidence strength from actual methodological differences.",
                "sourceIds": [item.get("sourceId") for item in evidence_items[:6] if item.get("sourceId")],
                "resolutionHint": "Retrieve additional method, experiment, and limitation sections for sparse papers before making a high-confidence claim.",
            }
        )

    has_external = any(
        str(item.get("sourceType") or "") == EXTERNAL_SOURCE_TYPE
        for item in evidence_items
    )
    if has_external:
        conflicts.append(
            {
                "id": "external-evidence-coverage",
                "severity": "medium",
                "claim": "External academic evidence was used to supplement evidence gaps, but it should not be treated as equally reliable as indexed paper evidence.",
                "papers": [item.get("pdfId") for item in paper_contexts[:4] if item.get("pdfId")],
                "summary": "External academic search provided supplementary evidence for evidence gaps, but it has not been reviewed alongside the full paper text and should only be used as supplementary clues.",
                "sourceIds": [
                    item.get("sourceId") for item in evidence_items
                    if str(item.get("sourceType") or "") == EXTERNAL_SOURCE_TYPE
                ][:6],
                "resolutionHint": "Use external academic evidence only to identify additional clues, not to override or replace indexed paper conclusions.",
            }
        )

    if fallback_contexts:
        conflicts.append(
            {
                "id": "retrieval-fallback-conflict",
                "severity": "high",
                "claim": "At least one paper is using fallback evidence rather than indexed retrieval.",
                "papers": [item.get("pdfId") for item in fallback_contexts],
                "summary": "Fallback evidence can keep the workflow moving, but it should not be treated as equally reliable as indexed paper evidence.",
                "sourceIds": [item.get("sourceId") for item in evidence_items if item.get("metadata", {}).get("fallback")][:6],
                "resolutionHint": "Re-index or re-upload the affected papers, then rerun the Agent task.",
            }
        )

    if not conflicts:
        conflicts.append(
            {
                "id": "no-major-conflict",
                "severity": "low",
                "claim": "No major conflict candidate was detected in the lightweight pass.",
                "papers": [item.get("pdfId") for item in paper_contexts[:4]],
                "summary": "The current evidence does not expose a clear contradiction; later rounds can add claim extraction and contradiction scoring.",
                "sourceIds": [item.get("sourceId") for item in evidence_items[:6] if item.get("sourceId")],
                "resolutionHint": "Use this as a process marker, not a final absence-of-conflict judgement.",
            }
        )

    return conflicts[:4]


def build_code_execution_proposal(
    artifact_id: str,
    description: str = "",
) -> Dict[str, Any]:
    """Generate a structured code execution proposal for Agent review."""
    return {
        "artifactId": clean_text(artifact_id),
        "description": clean_text(description)[:300],
        "templateId": "descriptive-statistics-v1",
        "createdAt": _utc_now(),
    }


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def execute_run(
    prompt: str,
    paper_ids: List[str],
    allow_external_search: bool = False,
    allow_web_search: bool = False,
    allow_iterative_search: bool = False,
) -> Dict[str, Any]:
    paper_contexts, tool_calls, evidence_items = collect_project_evidence(
        prompt,
        paper_ids,
        allow_external_search=allow_external_search,
        allow_web_search=allow_web_search,
        allow_iterative_search=allow_iterative_search,
    )
    finding, comparison_table, conflicts, open_questions = build_agent_outputs(
        prompt,
        paper_contexts,
        evidence_items,
    )
    draft_report = build_minimal_report(
        prompt,
        {"title": "Project"},
        paper_contexts,
        evidence_items,
        conflicts,
        open_questions,
    )
    return {
        "paperContexts": paper_contexts,
        "toolCalls": tool_calls,
        "artifacts": {
            "evidenceItems": evidence_items,
            "findings": [finding],
            "comparisonTable": comparison_table,
            "conflicts": conflicts,
            "openQuestions": open_questions,
            "draftReport": draft_report,
        },
    }


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _plan_item(item_id: str, label: str, detail: str, status: str) -> Dict[str, Any]:
    return {"id": item_id, "label": label, "detail": detail, "status": status}
