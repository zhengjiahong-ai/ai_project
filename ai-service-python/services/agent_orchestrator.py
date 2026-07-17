import copy
from typing import Any, Callable, Dict, List, Tuple

from services.agent_evidence_collector import (
    collect_project_evidence,
)
from services.agent_report_sections import (
    build_minimal_report,
    build_paper_judgement,
    detect_conflicts,
)
from services.external_evidence import EXTERNAL_SOURCE_TYPE
from services.knowledge_graph_store import enrich_conflicts_with_graph_context


ProgressCallback = Callable[[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], float, str], None]
CancelCheck = Callable[[], bool]
from services.agent_advanced_analysis import run_advanced_analysis
from services.agent_reasoning import (
    build_finding_summary,
    clean_text,
    synthesize_llm_report,
)


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

    # P6-18: cross-source evidence validation
    try:
        from services.evidence_cross_validator import cross_validate_evidence

        cv_result = cross_validate_evidence(evidence_items, use_llm=False)
        if cv_result.get("claims"):
            conflicts.append({
                "id": "cross-validation",
                "conflictType": "cross-validation",
                "severity": "low",
                "claim": "Multi-source evidence cross-validation",
                "summary": (
                    f"Cross-validated {cv_result['summary']['total_claims']} claims across sources: "
                    f"{cv_result['summary']['confirmed']} confirmed, "
                    f"{cv_result['summary']['supported']} supported, "
                    f"{cv_result['summary']['single_source']} single-source, "
                    f"{cv_result['summary']['contradicted']} contradicted."
                ),
                "papers": paper_ids,
                "sourceIds": [],
                "crossValidation": cv_result,
            })
    except Exception:
        pass  # cross-validation is optional; never blocks agent output

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
    domain: str = "",
) -> Dict[str, Any]:
    # Activate domain specialist if a domain is selected
    domain_config = {}
    if domain and domain.strip():
        try:
            from services.domain_specialists import activate_domain_specialist
            domain_config = activate_domain_specialist(domain.strip())
        except Exception:
            domain_config = {}

    paper_contexts, tool_calls, evidence_items, research_timeline = collect_project_evidence(
        prompt,
        paper_ids,
        allow_external_search=allow_external_search,
        allow_web_search=allow_web_search,
        allow_iterative_search=allow_iterative_search,
        domain_config=domain_config,
    )
    finding, comparison_table, conflicts, open_questions = build_agent_outputs(
        prompt,
        paper_contexts,
        evidence_items,
    )

    # ── Multi-round follow-up ────────────────────────────────────────────
    MAX_FOLLOW_UP_ROUNDS = 2
    follow_up_round = 0
    while follow_up_round < MAX_FOLLOW_UP_ROUNDS and _should_follow_up(open_questions, evidence_items):
        follow_up_round += 1
        refined_queries = _build_follow_up_queries(prompt, open_questions, paper_contexts)
        if not refined_queries:
            break

        research_timeline.append(_timeline_step(
            "search",
            f"补充检索第 {follow_up_round} 轮",
            f"基于 {len(open_questions)} 个证据缺口发起定向补充检索",
        ))

        # Re-collect with refined queries targeting sparse papers
        try:
            fu_contexts, fu_tool_calls, fu_evidence, fu_timeline = collect_project_evidence(
                prompt,
                paper_ids,
                allow_external_search=allow_external_search,
                allow_web_search=allow_web_search,
                allow_iterative_search=allow_iterative_search,
                domain_config=domain_config,
            )
            # Merge new evidence
            evidence_items = _merge_evidence(evidence_items, fu_evidence)
            tool_calls.extend(fu_tool_calls or [])
            research_timeline.extend(fu_timeline or [])
        except Exception:
            break

        # Re-build outputs with expanded evidence
        finding, comparison_table, conflicts, open_questions = build_agent_outputs(
            prompt,
            paper_contexts,
            evidence_items,
        )

        research_timeline.append(_timeline_step(
            "search",
            f"补充检索第 {follow_up_round} 轮完成",
            f"证据项增至 {len(evidence_items)} 条",
        ))
    # ── End follow-up ─────────────────────────────────────────────────────

    advanced_analysis = run_advanced_analysis(
        prompt=prompt,
        paper_ids=paper_ids,
        evidence_items=evidence_items,
        findings=[finding],
        conflicts=conflicts,
        open_questions=open_questions,
    )
    draft_report = build_minimal_report(
        prompt,
        {"title": "Project"},
        paper_contexts,
        evidence_items,
        conflicts,
        open_questions,
    )
    llm_synthesis = synthesize_llm_report(
        prompt=prompt,
        paper_contexts=paper_contexts,
        evidence_items=evidence_items,
        conflicts=conflicts,
        open_questions=open_questions,
        advanced_analysis=advanced_analysis,
    )
    return {
        "paperContexts": paper_contexts,
        "toolCalls": tool_calls,
        "researchTimeline": research_timeline,
        "artifacts": {
            "evidenceItems": evidence_items,
            "findings": [finding],
            "comparisonTable": comparison_table,
            "conflicts": conflicts,
            "openQuestions": open_questions,
            "draftReport": draft_report,
            "llmSynthesis": llm_synthesis,
            "advancedAnalysis": advanced_analysis,
        },
    }


def _timeline_step(
    step_type: str,
    summary: str,
    detail: str = "",
    status: str = "success",
    duration_ms: int = 0,
) -> Dict[str, Any]:
    import uuid
    return {
        "stepId": uuid.uuid4().hex[:12],
        "type": step_type,
        "summary": summary,
        "detail": detail,
        "status": status,
        "durationMs": duration_ms,
    }


def _plan_item(item_id: str, label: str, detail: str, status: str) -> Dict[str, Any]:
    return {"id": item_id, "label": label, "detail": detail, "status": status}


def _should_follow_up(open_questions: List[str], evidence_items: List[Dict[str, Any]]) -> bool:
    """Decide whether another follow-up round is warranted.

    Follow-up is triggered when open_questions indicate evidence gaps
    and there are fewer than 12 evidence items (to avoid over-collection).
    """
    if not open_questions:
        return False
    gap_signals = [
        q for q in open_questions
        if any(kw in str(q).lower() for kw in ("need", "gap", "sparse", "missing", "cover"))
    ]
    return len(gap_signals) > 0 and len(evidence_items) < 12


def _build_follow_up_queries(
    prompt: str,
    open_questions: List[str],
    paper_contexts: List[Dict[str, Any]],
) -> List[str]:
    """Build refined queries for supplementary evidence retrieval."""
    sparse_pdfs = [
        clean_text(ctx.get("pdfId", ""))
        for ctx in paper_contexts
        if int(ctx.get("evidenceCount", 0)) <= 1
    ]
    queries = []
    for pdf_id in sparse_pdfs[:3]:
        for q in open_questions[:2]:
            query = f"{prompt[:80]} evidence gap for {pdf_id}: {q[:120]}"
            queries.append(query[:256])
    return queries[:5]


def _merge_evidence(
    existing: List[Dict[str, Any]],
    new_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge new evidence items into existing, deduplicating by sourceId."""
    seen = {str(item.get("sourceId", "")) for item in existing if item.get("sourceId")}
    merged = list(existing)
    for item in new_items or []:
        sid = str(item.get("sourceId", ""))
        if sid and sid not in seen:
            seen.add(sid)
            merged.append(item)
    return merged
