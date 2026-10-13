"""Durable LangGraph flow for Deep Research v2.

Nodes: resolve_brief, plan, acquire, read, extract, assess, synthesize, verify, publish.
Uses SqliteSaver with long-lived connection for persistent checkpoints.
Graph state contains only compact IDs; large evidence/domain content lives in repository.
"""
from __future__ import annotations

import json
import hashlib
import logging
import sqlite3
import time
from typing import Any, Callable, TypedDict

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:  # pragma: no cover - offline tests may not have langgraph installed
    StateGraph = None  # type: ignore
    END = None  # type: ignore
    SqliteSaver = None  # type: ignore

from services.deep_research.contracts import (
    ENGINE_VERSION,
    OUTCOME_COMPLETE,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_NONE,
    OUTCOME_PARTIAL,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STATUS_WAITING_USER,
    TERMINAL_STATUSES,
    utc_now_iso,
)

logger = logging.getLogger(__name__)


# ── Graph State ────────────────────────────────────────────────────────────────

class GraphState(TypedDict, total=False):
    """Compact graph state - only IDs and control flags.
    
    Large content (evidence, claims, report body) is stored in the repository
    and referenced by ID to keep checkpoint size bounded.
    """
    run_id: str
    workspace_task_id: str  # Product task ID (mandatory)
    operation_key: str      # Idempotency key for receipt recovery
    execution_epoch: int
    brief_id: str
    plan_ids: list[str]
    source_ids: list[str]
    evidence_ids: list[str]
    claim_ids: list[str]
    coverage_state: dict[str, Any]
    gaps: list[dict[str, Any]]
    report_version_id: str
    publication_id: str
    outcome: str
    error_code: str
    stop_reason: str
    clarification_needed: bool
    clarification_question: str
    requery_count: int
    max_requery_rounds: int
    requery_queries: list[dict[str, Any]]
    budget_exhausted: bool
    started_at: float  # Monotonic timestamp for deadline calculation
    deadline_seconds: float  # Max wall clock seconds
    source_policy_mode: str  # task_only, academic_external, external_only
    previous_evidence_hashes: list[str]  # For incremental child dedup
    inherited_source_ids: list[str]  # Inherited from parent run
    inherited_evidence_ids: list[str]  # Inherited from parent run
    assess_inherited: bool  # Check reused evidence before issuing new retrieval
    prev_source_count: int  # Track no-new-evidence stopping


# ── Node Functions ─────────────────────────────────────────────────────────────

def make_wait_for_clarification_node() -> Callable[[GraphState], dict]:
    """Wait for user clarification using LangGraph interrupt mechanism.
    
    Interrupt pauses execution until resume with clarification answer.
    """
    try:
        from langgraph.types import interrupt
    except ImportError:
        # Fallback for older langgraph versions
        def interrupt(value: Any) -> Any:
            raise RuntimeError("LangGraph interrupt not available")
    
    def node(state: GraphState) -> dict:
        question = state.get("clarification_question", "Please clarify your question.")
        
        # Interrupt pauses the graph here until resumed
        answer = interrupt({
            "type": "clarification_needed",
            "question": question,
            "run_id": state.get("run_id", ""),
        })
        
        # When resumed, answer contains the clarification
        return {
            "clarification_needed": False,
            "clarification_question": "",
        }
    
    return node


def make_resolve_brief_node(
    llm_invoke: Callable[..., dict],
    repo_update: Callable[[str, Callable, dict | None], dict],
) -> Callable[[GraphState], dict]:
    """Resolve user question into structured brief with outputKind."""
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        if not run_id:
            return {"error_code": "missing_run_id", "outcome": OUTCOME_NONE}
        
        record = repo_update(run_id, lambda r: {**r, "stage": "resolve_brief"}, expected_revision=None)
        question = record.get("question", "")
        materials = record.get("materials", [])
        
        prompt = f"""Analyze this research question and determine the output kind.
Question: {question}
Materials count: {len(materials)}
Selected materials: {json.dumps([{'id': m.get('materialId'), 'title': m.get('title', '')} for m in materials], ensure_ascii=False)}
Primary papers: {json.dumps(record.get('focusPaperIds', []))}
Source policy: {json.dumps(record.get('sourcePolicy', {'mode': 'task_only'}))}

Return JSON with:
- outputKind: one of direction_survey, paper_comparison, claim_verification, experiment_design, research_entry
- title: a short Chinese report title (12-24 characters); do not repeat the full request or its instructions
- assumptions: list of inferred conditions
- clarification: string if ambiguous, empty if clear
- constraints: any explicit limitations
- measurementScope: for experiment_design, list of {{domain: quality|speed|storage, requestExcerpt: exact words from Question}}
  for EVERY measurement domain explicitly requested. Never infer these from paper titles.
  Use [] when the measurement target is unspecified. Quality-only experiments do not
  require speed or storage protocols; include those domains when the user asks for them.

Clarify only consequential ambiguity about the research target or permitted materials.
An experiment-design request is a proposed, unexecuted plan: unknown numeric settings can be
explicitly proposed and fixed across controls. Do not pause merely to ask for optional implementation
preferences or for facts that can be read from the selected papers. Never widen material permissions."""
        
        result = llm_invoke(run_id, "resolve_brief", prompt, {"max_tokens": 1500, "temperature": 0.1})
        
        # Handle LLMResult dataclass - extract content attribute
        if hasattr(result, "content"):
            content = result.content
        elif isinstance(result, dict):
            content = result.get("content", "{}")
        else:
            content = str(result)
        
        parsed = _safe_parse_json(content)
        
        # Validate parsed is a dict before accessing fields
        if not isinstance(parsed, dict):
            logger.warning("resolve_brief response not a dict: %s", type(parsed))
            return {"error_code": "invalid_brief_response", "outcome": OUTCOME_NONE}
        
        output_kind = parsed.get("outputKind", "direction_survey")
        from services.deep_research.synthesis import resolve_output_kind, OUTPUT_KIND_SECTIONS
        output_kind = resolve_output_kind(record.get("outputKind") if record.get("outputKind") not in {None, "general"} else output_kind)
        if output_kind not in OUTPUT_KIND_SECTIONS:
            return {"error_code": "invalid_brief_response", "outcome": OUTCOME_NONE}
        clarification = parsed.get("clarification", "")
        
        brief_id = f"brief_{run_id}"
        from services.deep_research.metric_scope import grounded_metric_domains
        update_payload = {
            "briefId": brief_id,
            "outputKind": output_kind,
            "metricDomains": grounded_metric_domains(parsed.get('measurementScope'), question),
            "assumptions": parsed.get("assumptions", []),
            "constraints": parsed.get("constraints", ""),
            "title": parsed.get("title", "")[:40] if isinstance(parsed.get("title"), str) else "",
        }
        
        repo_update(run_id, lambda r: {**r,
            "status": STATUS_WAITING_USER if clarification else r["status"],
            "state": {**(r.get("state") or {}), **update_payload,
                      **({"waitingSince": utc_now_iso()} if clarification else {}),
                      "clarificationNeeded": bool(clarification), "clarificationQuestion": clarification}}, expected_revision=None)
        
        if clarification:
            return {
                "brief_id": brief_id,
                "clarification_needed": True,
                "clarification_question": clarification,
            }
        
        return {"brief_id": brief_id, "clarification_needed": False}
    
    return node


def make_plan_node(
    llm_invoke: Callable[..., dict],
    repo_update: Callable[[str, Callable, dict | None], dict],
    validate_plan: Callable[[list], list],
) -> Callable[[GraphState], dict]:
    """Generate research plan with obligations and dependencies."""
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        
        record = repo_update(run_id, lambda r: {**r, "stage": "plan"}, expected_revision=None)
        question = record.get("question", "")
        brief_state = record.get("state", {})
        output_kind = brief_state.get("outputKind", "direction_survey")
        materials = record.get("materials", [])
        
        prompt = f"""Create a research plan for this question.
Question: {question}
Output kind: {output_kind}
User clarification: {brief_state.get('clarification', '')}
Materials: {json.dumps([{'id': m.get('materialId'), 'title': m.get('title', '')} for m in materials[:10]], ensure_ascii=False)}
Primary papers: {json.dumps(record.get('focusPaperIds', []))}
Previously acquired source identities (reuse an exact relevant arXiv identifier for lookup):
{json.dumps(list({s.get('workId'): {'workId': s.get('workId'), 'versionId': s.get('versionId'), 'title': s.get('title')} for s in brief_state.get('sources', [])}.values())[:12], ensure_ascii=False)}
User context (notes/old reports, UNVERIFIED; use only for goals and queries, never as paper facts):
{json.dumps(record.get('contextMaterials', []), ensure_ascii=False)}

Return a compact JSON array of 1-4 plan items (prefer 1-2 for a short answer), each with:
- itemId: unique identifier
- question: sub-question to answer
- obligations: array of {{obligationId, question, requiredSources, searchQuery, purpose, requestExcerpt}}
- searchQuery: concise English academic search terms, preserving names and identifiers
- dependencies: array of itemIds this depends on
- priority: 1-3 (1=highest)

Ensure DAG structure (no cycles). Each obligation must specify which sources to check.
Preserve the user's exact limits. If only one sub-question is requested, create exactly one item.
Use short questions and at most two obligations per item. Do not repeat the same obligation.
purpose is answer_requirement for anything the user asks to receive, or supporting_research
for an auxiliary investigation used to inform that deliverable. For supporting_research,
copy requestExcerpt (at least 8 characters) literally from the original question to
identify the deliverable it serves. This label is only a hint: the final audit must
independently judge whether any unanswered support question still matters. Do not mark
requested facts, necessary experimental assumptions or requested comparisons optional.
For experiment proposals, distinguish learning how the original method works from
requiring a retelling of every original benchmark in the proposed experiment.
For experiment designs, include dataset/subset availability in the evaluation-conditions investigation:
retrieve the original evaluation's actual unit count or named units, particularly
when a paper inherits a subset from another available paper. Existing data availability
is a necessary factual prerequisite, not an optional historical benchmark retelling.
Each obligation should ask for ONE dimension that a short passage can support (e.g. storage,
speed, quality or evaluation conditions), not a compound demand for every result at once.
For mechanism questions, explicitly include the requested entities' relationship,
conditioning inputs and activation/applicability rules in the obligation question.
Do not substitute a generic overview for the user's requested mechanism or conditions.

Return a JSON ARRAY of plan items, NOT an object with items field."""
        
        result = llm_invoke(run_id, "plan", prompt, {"max_tokens": 5000, "temperature": 0.1})
        
        # Handle LLMResult dataclass - extract content attribute
        if hasattr(result, "content"):
            content = result.content
        elif isinstance(result, dict):
            content = result.get("content", "[]")
        else:
            content = str(result)
        
        parsed = _safe_parse_json(content)
        
        # Handle {items: [...]} wrapper format - extract items array
        if isinstance(parsed, dict) and "items" in parsed:
            parsed = parsed.get("items", [])
        
        # Fail closed: malformed JSON list must not proceed to retrieval
        if not isinstance(parsed, list):
            logger.warning("Plan response not a list, failing closed: %s", type(parsed))
            return {"error_code": "invalid_plan_response", "outcome": OUTCOME_NONE, "plan_ids": []}
        
        try:
            validated = validate_plan(parsed[:4])
        except ValueError as ve:
            logger.warning("Plan validation failed: %s", ve)
            return {"error_code": "invalid_plan_response", "outcome": OUTCOME_NONE, "plan_ids": []}
        
        if not validated:
            return {"error_code": "invalid_plan_response", "outcome": OUTCOME_NONE, "plan_ids": []}

        from services.deep_research.obligation_purpose import normalize_obligation_purposes
        validated = normalize_obligation_purposes(validated, question)
        allowed = [material.get("materialId") for material in materials]
        required_default = allowed if output_kind == "paper_comparison" else record.get("focusPaperIds") or allowed
        for item in validated:
            for obligation in item.get("obligations", []):
                requested = obligation.get("requiredSources", [])
                external_ids = []
                if record.get("sourcePolicy", {}).get("mode") in {"academic_external", "external_only"}:
                    from services.deep_research_academic import checked_arxiv_id
                    for sid in requested:
                        if sid.lower().startswith("arxiv:"):
                            try:
                                external_ids.append("arxiv:" + __import__('re').sub(r'v\d+$', '', checked_arxiv_id(sid.split(':', 1)[1])))
                            except ValueError:
                                pass
                obligation["requiredSources"] = [sid for sid in requested if sid in allowed] + external_ids or required_default
        # Each comparison must inspect every selected paper, while paper-specific
        # obligations should not require irrelevant evidence from all other papers.
        if output_kind == "paper_comparison":
            covered = {sid for item in validated for obl in item["obligations"] for sid in obl["requiredSources"]}
            for sid in allowed:
                if sid not in covered:
                    validated[0]["obligations"][0]["requiredSources"].append(sid)

        if output_kind == 'experiment_design':
            from services.deep_research.data_prerequisite import ensure_data_prerequisite
            # All task materials are permitted candidates; no invented external source.
            candidates = allowed or list(dict.fromkeys(sid for item in validated
                for obligation in item['obligations'] for sid in obligation['requiredSources']))
            validated = validate_plan(ensure_data_prerequisite(validated, candidates, question))
        
        plan_ids = [item["itemId"] for item in validated]
        from services.deep_research.continuation import rebind_inherited_state
        inherited = bool(brief_state.get('inheritedEvidence'))
        
        repo_update(
            run_id,
            lambda r: {**r, "state": rebind_inherited_state(r.get('state') or {}, validated)
                       if inherited else {**(r.get("state") or {}), "plan": validated}},
            expected_revision=None,
        )
        
        return {"plan_ids": plan_ids, "assess_inherited": inherited}
    
    return node


def make_acquire_node(
    retrieve_fn: Callable[[str, str, int], list],
    scope_validator: Callable[[str, str], bool],
    repo_update: Callable[[str, Callable, dict | None], dict],
    external_acquire: Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> Callable[[GraphState], dict]:
    """Acquire sources for each plan obligation, iterating EVERY selected paper.
    
    On requery rounds, uses gap-specific changed queries instead of original obligation questions.
    Deduplicates by sourceId (not workId) to retain all relevant chunks per obligation.
    Merges sources and evidence across rounds, preserving exact source identity and conditions.
    Persists normalized source metadata (workId/versionId/contentHash/accessLevel/text/location).
    
    Optional external_acquire: called only when sourcePolicy.mode is academic_external or
    external_only. Returns normalized external sources with sourceKind/workId/versionId/
    contentHash/title/arxivId/accessLevel/text/location/obligationIds. Merged into domain
    sources. Scope-validator accepts external work IDs ONLY after source persisted.
    For external_only with no materials, requiredSources use acquired external work IDs.
    """
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        requery_queries = state.get("requery_queries", [])
        
        record = repo_update(run_id, lambda r: {**r, "stage": "acquire"}, expected_revision=None)
        source_policy_mode = record.get("sourcePolicy", {}).get("mode", "task_only")
        materials = record.get("materials", [])
        plan = record.get("state", {}).get("plan", [])
        existing_sources = record.get("state", {}).get("sources", [])
        
        # Build existing source index for merging across rounds
        existing_by_id = {s["sourceId"]: s for s in existing_sources}
        normalized_sources = list(existing_sources)
        
        # Determine query set: gap-specific changed queries on requery, else original obligations
        if requery_queries:
            query_targets = requery_queries
        else:
            query_targets = []
            for plan_item in plan:
                for obligation in plan_item.get("obligations", []):
                    obl_id = obligation.get("obligationId", "")
                    question = obligation.get("question", "")
                    if obl_id and question:
                        query_targets.append({"obligationId": obl_id, "query": obligation.get("searchQuery") or question,
                                              "question": question,
                                              "requiredSources": obligation.get("requiredSources", [])})
        
        # Build material owner map for scope validation
        material_owner_map = {}
        for m in materials:
            mat_id = m.get("materialId", "")
            if mat_id:
                material_owner_map[mat_id] = mat_id
            if m.get("pdfId"):
                material_owner_map[m["pdfId"]] = mat_id
            if m.get("workId"):
                material_owner_map[m["workId"]] = mat_id
        
        # Local retrieval for task materials
        if source_policy_mode != "external_only":
            for material in materials:
                material_id = material.get("materialId", "")
                pdf_id = material.get("pdfId", material_id)
                
                if not scope_validator(run_id, material_id):
                    continue
                
                for target in query_targets:
                    if target.get("requiredSources") and material_id not in target["requiredSources"]:
                        continue
                    if target.get("missingSource") and target["missingSource"] != material_id:
                        continue
                    query = target.get("query", "")
                    obl_id = target.get("obligationId", "")
                    if not query:
                        continue
                    
                    results = retrieve_fn(query, pdf_id, limit=5)
                    
                    for item in results:
                        source_id = item.get("sourceId", "")
                        if not source_id:
                            continue
                        
                        source_work_id = item.get("sourceWorkId", item.get("pdfId", ""))
                        owner_material_id = material_owner_map.get(source_work_id)
                        if owner_material_id != material_id:
                            continue
                        
                        existing = existing_by_id.get(source_id)
                        if existing:
                            if obl_id and obl_id not in existing.get("obligationIds", []):
                                existing["obligationIds"].append(obl_id)
                        else:
                            new_source = {
                                "sourceId": source_id,
                                "workId": source_work_id,
                                "ownerMaterialId": owner_material_id,
                                "versionId": material.get("versionId") or item.get("versionId", source_id),
                                "contentHash": item.get("contentHash") or hashlib.sha256(item.get("text", "").encode()).hexdigest(),
                                "materialContentHash": material.get("contentHash"),
                                "accessLevel": item.get("accessLevel", "fulltext"),
                                "text": item.get("text", ""),
                                "tableData": item.get("tableData"),
                                "location": item.get("location", {"chunkIndex": item.get("chunkIndex", 0)}),
                                "obligationIds": [obl_id] if obl_id else [],
                                "sourceKind": "task_paper",
                                "title": item.get("title") or material.get("title", ""),
                                "url": item.get("url", ""),
                            }
                            normalized_sources.append(new_source)
                            existing_by_id[source_id] = new_source
        
        # External acquisition: only when policy permits and callback provided
        use_external = source_policy_mode in ("academic_external", "external_only") and external_acquire is not None
        if use_external:
            ext_sources = external_acquire(run_id, query_targets)
            for ext in ext_sources:
                ext_source_id = ext.get("sourceId", "")
                if not ext_source_id:
                    continue
                
                # Persist external source first so scope validator can accept it
                ext_work_id = ext.get("workId", "")
                existing = existing_by_id.get(ext_source_id)
                if existing:
                    ext_obl_ids = ext.get("obligationIds", [])
                    for oid in ext_obl_ids:
                        if oid and oid not in existing.get("obligationIds", []):
                            existing["obligationIds"].append(oid)
                else:
                    new_ext = {
                        "sourceId": ext_source_id,
                        "workId": ext_work_id,
                        "ownerMaterialId": ext_work_id,
                        "versionId": ext.get("versionId", ext_source_id),
                        "contentHash": ext.get("contentHash", ""),
                        "accessLevel": ext.get("accessLevel", "abstract"),
                        "text": ext.get("text", ""),
                        "location": ext.get("location", {}),
                        "obligationIds": ext.get("obligationIds", []),
                        "sourceKind": ext.get("sourceKind", "arxiv"),
                        "title": ext.get("title", ""),
                        "url": ext.get("url", ""),
                        "arxivId": ext.get("arxivId", ""),
                        "sourceType": "academic_paper",
                    }
                    normalized_sources.append(new_ext)
                    existing_by_id[ext_source_id] = new_ext
        
        source_ids = [s["sourceId"] for s in normalized_sources]
        
        repo_update(
            run_id,
            lambda r: {**r, "state": {**(r.get("state") or {}), "sourceIds": source_ids, "sources": normalized_sources}},
            expected_revision=None,
        )
        
        return {"source_ids": source_ids}
    
    return node


def make_read_node(
    read_fn: Callable[[str, str], dict],
    scope_validator: Callable[[str, str], bool],
    repo_update: Callable[[str, Callable, dict | None], dict],
) -> Callable[[GraphState], dict]:
    """Read source content with location preservation.
    
    Validates scope by mapping source to owner work/material before validation.
    Preserves full source metadata for evidence identity contract.
    Note: Scope validation is done in graph node using work_id; TrackedSourceReader
    also validates but uses source_id directly - this is acceptable since the
    graph node does the authoritative check first.
    """
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        source_ids = state.get("source_ids", [])
        
        record = repo_update(run_id, lambda r: {**r, "stage": "read"}, expected_revision=None)
        
        # Get normalized sources from acquire node (contains workId/ownerMaterialId mapping)
        sources_map = {s["sourceId"]: s for s in record.get("state", {}).get("sources", [])}
        
        read_results = []
        from services.deep_research.selection import balanced_sample
        extracted = {(e.get("sourceId"), e.get("contentHash")) for e in record.get("state", {}).get("evidence", [])}
        available = [sources_map[sid] for sid in source_ids if sid in sources_map]
        available.sort(key=lambda source: (source["sourceId"], source.get("contentHash")) in extracted)
        selected = balanced_sample(available,
            lambda source: (source.get("workId"), tuple(source.get("obligationIds", []))),
            24 if record.get("budget", {}).get("profile") == "extended" else 12)
        for source_meta in selected:
            source_id = source_meta["sourceId"]
            # Map source to owner material for scope validation
            source_meta = sources_map.get(source_id, {})
            # Use ownerMaterialId (resolved in acquire) for scope validation, not source_id directly
            owner_material_id = source_meta.get("ownerMaterialId", source_meta.get("workId", source_id))
            
            # Validate scope using owner material ID
            if not scope_validator(run_id, owner_material_id):
                logger.warning("Scope validation failed for source %s (owner %s)", source_id, owner_material_id)
                continue
            
            # Read content - reader may return empty if no content available
            content = read_fn(run_id, source_id)
            
            # Use source metadata text as fallback if reader returns empty pages
            pages = content.get("pages", []) if content else []
            if not pages and source_meta.get("text"):
                # Fallback to chunk text from acquire node
                pages = [{"page": 0, "text": source_meta.get("text", "")}]
            
            if pages:
                # Preserve full source metadata for evidence identity contract
                read_results.append({
                    "sourceId": source_id,
                    "workId": source_meta.get("workId", source_id),
                    "ownerMaterialId": owner_material_id,
                    "versionId": source_meta.get("versionId", source_id),
                    "contentHash": source_meta.get("contentHash", ""),
                    "accessLevel": content.get("accessLevel", source_meta.get("accessLevel", "unknown")) if content else source_meta.get("accessLevel", "unknown"),
                    "pages": pages,
                    "text": source_meta.get("text", ""),  # Original chunk text
                    "tableData": source_meta.get("tableData"),
                    "location": source_meta.get("location", {}),
                    "sourceKind": source_meta.get("sourceKind", "local"),
                    "title": source_meta.get("title", ""),
                    "url": source_meta.get("url", ""),
                    "obligationIds": source_meta.get("obligationIds", []),
                })
        
        repo_update(
            run_id,
            lambda r: {**r, "state": {**(r.get("state") or {}), "readResults": read_results}},
            expected_revision=None,
        )
        
        return {"source_ids": source_ids}  # Pass through
    
    return node


def make_extract_node(
    llm_invoke: Callable[..., dict],
    make_evidence_fn: Callable[..., dict],
    scope_validator: Callable[[str, str], bool],
    repo_update: Callable[[str, Callable, dict | None], dict],
) -> Callable[[GraphState], dict]:
    """Extract evidence from read content with literal preservation.
    
    Uses full source metadata from read node to satisfy evidence identity contract.
    Extract prompts supply obligation IDs for relevance binding.
    Merges evidence across requery rounds by evidence ID.
    Skips re-extraction of sources already extracted (same contentHash) for incremental children.
    Preserves sourceKind/title/url in evidence records.
    """
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        previous_hashes = set(state.get("previous_evidence_hashes", []))
        
        record = repo_update(run_id, lambda r: {**r, "stage": "extract"}, expected_revision=None)
        read_results = record.get("state", {}).get("readResults", [])
        plan = record.get("state", {}).get("plan", [])
        existing_evidence = record.get("state", {}).get("evidence", [])
        
        # Build obligation lookup for prompt context
        obligation_map = {}
        for plan_item in plan:
            for obl in plan_item.get("obligations", []):
                obl_id = obl.get("obligationId", "")
                if obl_id:
                    obligation_map[obl_id] = obl.get("question", "")
        
        # Index existing evidence for merge
        existing_by_id = {e["evidenceId"]: e for e in existing_evidence}
        # Track which content hashes have already been extracted
        extracted_hashes = {(e.get("sourceId"), e.get("contentHash")) for e in existing_evidence if e.get("sourceId")}
        all_evidence = list(existing_evidence)
        
        for read_result in read_results:
            source_id = read_result.get("sourceId", "")
            work_id = read_result.get("workId", source_id)
            pages = read_result.get("pages", [])
            access_level = read_result.get("accessLevel", "abstract")
            content_hash = read_result.get("contentHash", "")
            source_kind = read_result.get("sourceKind", "local")
            source_title = read_result.get("title", "")
            source_url = read_result.get("url", "")
            
            # Skip re-extraction of already-extracted content (incremental child dedup)
            if (source_id, content_hash) in extracted_hashes:
                for ev in all_evidence:
                    if ev.get("sourceId") == source_id and ev.get("contentHash") == content_hash:
                        ev["obligationIds"] = list(obligation_map)
                continue
            
            if not scope_validator(run_id, work_id):
                continue
            
            # Get obligation IDs relevant to this source
            source_obl_ids = read_result.get("obligationIds", [])
            if not source_obl_ids:
                source_obl_ids = list(obligation_map.keys())[:5]
            
            for page in pages[:5]:
                text = page.get("text", "")[:3000]
                if not text or len(text) < 50:
                    continue
                
                # Supply obligation IDs in extract prompt
                obl_context = [{"obligationId": oid, "question": obligation_map.get(oid, "")} for oid in source_obl_ids if oid in obligation_map]
                
                prompt = f"""Extract evidence from this text relevant to the research obligations.
Text (page {page.get('page', '?')}): {text[:3000]}

Obligations (with IDs): {json.dumps(obl_context[:5], ensure_ascii=False)}

Return a JSON array of at most THREE self-contained, relevant evidence items. Return [] if none.
Keep complete sentences with their conditions; omit fragmentary labels, dangling numbers and unrelated captions.
For requested mechanisms, retain conditioning inputs and activation/applicability rules.
Each item has:
- quote: exact literal text from source
- location: {{page, section, chunk}}
- obligationIds: which obligation IDs this supports (must match provided IDs)
- conditions: any dataset/model/hardware conditions mentioned
- kind: reported/inference/suggestion"""
                
                result = llm_invoke(run_id, "extract", prompt, {"max_tokens": 1500, "temperature": 0.0})
                
                if hasattr(result, "content"):
                    content = result.content
                elif isinstance(result, dict):
                    content = result.get("content", "[]")
                else:
                    content = str(result)
                
                parsed = _safe_parse_json(content)
                
                if not isinstance(parsed, list):
                    continue
                
                for ev in parsed[:3]:
                    if not isinstance(ev, dict):
                        continue
                    from services.deep_research.literal_quote import original_quote_span
                    quote = original_quote_span(ev.get("quote", ""), text)
                    if quote is None:
                        continue
                    
                    # Validate obligation IDs are from the supplied set
                    ev_obl_ids = ev.get("obligationIds", [])
                    if not isinstance(ev_obl_ids, list):
                        ev_obl_ids = []
                    ev_obl_ids = [oid for oid in ev_obl_ids if oid in obligation_map]
                    
                    try:
                        evidence = make_evidence_fn(
                            source={
                                "workId": work_id,
                                "versionId": read_result.get("versionId", source_id),
                                "contentHash": content_hash,
                                "accessLevel": access_level,
                            },
                            quote=quote,
                            original=text,
                            location={**read_result.get("location", {}), **{k: v for k, v in page.items() if k != "text"}},
                            obligation_ids=ev_obl_ids,
                            conditions=ev.get("conditions") if isinstance(ev.get("conditions"), dict) else
                                {"context": ev["conditions"]} if isinstance(ev.get("conditions"), str) and ev["conditions"] else {},
                        )
                        
                        # Preserve source metadata on evidence
                        evidence["sourceKind"] = source_kind
                        evidence["sourceId"] = source_id
                        evidence["sourceTitle"] = source_title
                        evidence["sourceUrl"] = source_url
                        
                        # Merge: skip duplicates by evidence ID
                        if evidence["evidenceId"] not in existing_by_id:
                            all_evidence.append(evidence)
                            existing_by_id[evidence["evidenceId"]] = evidence
                            if content_hash:
                                extracted_hashes.add((source_id, content_hash))
                    except ValueError:
                        pass
        
        repo_update(
            run_id,
            lambda r: {**r, "state": {**(r.get("state") or {}), "evidence": all_evidence}},
            expected_revision=None,
        )
        
        return {"evidence_ids": [e["evidenceId"] for e in all_evidence]}
    
    return node


def make_assess_node(
    coverage_gaps_fn: Callable[[list, list, list], list],
    repo_update: Callable[[str, Callable, dict | None], dict],
    llm_invoke: Callable[..., dict] | None = None,
) -> Callable[[GraphState], dict]:
    """Assess coverage and decide next action.
    
    Uses a batched budgeted LLM call per assess round to judge obligation/evidence
    binding and conditions. Literal=='passed' plus obligation ID alone is NOT sufficient
    for relevance — the LLM must confirm the evidence actually addresses the obligation.
    Unsupported/unchecked evidence never closes a gap.
    
    Changed queries target specific missing source/obligation pairs with meaningful
    gap-focused content (not just a round marker). Stops on no new evidence.
    Bounded maximum 2 requery rounds.
    """
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        requery_count = state.get("requery_count", 0)
        prev_source_count = state.get("prev_source_count", 0)
        
        record = repo_update(run_id, lambda r: {**r, "stage": "assess"}, expected_revision=None)
        plan = record.get("state", {}).get("plan", [])
        evidence = record.get("state", {}).get("evidence", [])
        materials = record.get("materials", [])
        current_source_count = len(record.get("state", {}).get("sources", []))
        
        # Build obligation lookup
        obligation_map = {}
        for plan_item in plan:
            for obl in plan_item.get("obligations", []):
                obl_id = obl.get("obligationId", "")
                if obl_id:
                    obligation_map[obl_id] = obl.get("question", "")
        
        # Batch relevance judgment via LLM if available
        from services.deep_research.selection import balanced_sample
        relevance_verdicts: dict[str, bool] = {}
        if llm_invoke is not None and evidence:
            relevance_pairs = []
            for ev in evidence:
                for obl_id in ev.get("obligationIds", []):
                    if obl_id in obligation_map:
                        relevance_pairs.append({
                            "evidenceId": ev["evidenceId"],
                            "obligationId": obl_id,
                            "quote": ev.get("quote", ""),
                            "conditions": ev.get("conditions", {}),
                            "obligationQuestion": obligation_map[obl_id],
                            "sourceWorkId": ev.get("sourceWorkId", ""),
                        })
            
            if relevance_pairs:
                selected_pairs = balanced_sample(relevance_pairs,
                    lambda pair: (pair["sourceWorkId"], pair["obligationId"]), 20)
                batch_prompt = f"""For each evidence-obligation pair below, judge whether the evidence ACTUALLY addresses the obligation question. A literal quote match is NOT sufficient — the content must be topically relevant and the conditions must be compatible.

Pairs:
{json.dumps(selected_pairs, ensure_ascii=False, indent=2)}

Return a COMPACT JSON array of {{evidenceId, obligationId, relevant: true/false}}.
Do not include reasons or extra prose; include one verdict for EVERY supplied pair.
Only mark relevant=true if the evidence directly bears on the obligation question."""
                
                try:
                    result = llm_invoke(run_id, "assess_relevance", batch_prompt,
                                        {"max_tokens": 4000, "temperature": 0.0})
                    if hasattr(result, "content"):
                        resp_content = result.content
                    elif isinstance(result, dict):
                        resp_content = result.get("content", "[]")
                    else:
                        resp_content = str(result)
                    
                    verdicts = _safe_parse_json(resp_content)
                    if isinstance(verdicts, list):
                        for v in verdicts:
                            if isinstance(v, dict):
                                key = f"{v.get('evidenceId', '')}:{v.get('obligationId', '')}"
                                relevance_verdicts[key] = v.get("relevant") is True
                except Exception:
                    pass
        
        # Build coverage records — only supported if LLM confirmed relevance
        coverage = []
        for ev in evidence:
            ev_obl_ids = ev.get("obligationIds", [])
            if not ev_obl_ids:
                continue
            literal_passed = ev.get("verification", {}).get("literal") == "passed"
            if not literal_passed:
                continue
            for obl_id in ev_obl_ids:
                if obl_id not in obligation_map:
                    continue
                rel_key = f"{ev['evidenceId']}:{obl_id}"
                is_relevant = relevance_verdicts.get(rel_key, False)
                coverage.append({
                    "obligationId": obl_id,
                    "sourceWorkId": ev.get("sourceWorkId", ""),
                    "state": "supported" if is_relevant else "unchecked",
                    "checked": True,
                })
        
        required_sources = [m.get("materialId", "") for m in materials]
        if not required_sources:
            required_sources = list(dict.fromkeys(s.get("workId") for s in record.get("state", {}).get("sources", []) if s.get("workId")))
        # Keep a positive result when another passage for the same pair was insufficient.
        merged_coverage = {}
        for row in coverage:
            key = (row["obligationId"], row["sourceWorkId"])
            if key not in merged_coverage or row["state"] == "supported":
                merged_coverage[key] = row
        coverage = list(merged_coverage.values())
        gaps = coverage_gaps_fn(plan, coverage, required_sources)
        if not required_sources:
            gaps = [{"obligationId": obl_id, "question": question, "missingEvidence": "尚未取得可用文献", "checked": True}
                    for obl_id, question in obligation_map.items()]
        
        # Decide next action - bounded maximum 2 requery rounds
        stop_reason = ""
        requery_queries = []
        
        # Stop on no new evidence since last round
        if requery_count > 0 and current_source_count <= prev_source_count:
            stop_reason = "no_new_evidence"
        elif not gaps:
            stop_reason = "covered"
        elif requery_count >= (4 if record.get("budget", {}).get("profile") == "extended" else 2):
            stop_reason = "max_requery"
        elif len(gaps) > len(plan) * 2:
            stop_reason = "too_many_gaps"
        else:
            # Generate meaningful gap-focused queries targeting missing source/obligation pairs
            seen_queries = set()
            for gap in gaps:
                obl_id = gap.get("obligationId", "")
                question = gap.get("question", "")
                missing_source = gap.get("sourceWorkId", "")
                if not obl_id or not question:
                    continue
                # Meaningful changed query: include the gap context and missing source
                strategy = "对照实验 消融结果 评测设置 固定条件" if requery_count == 0 else "反对证据 局限性 失败案例 泛化边界"
                parts = [question, gap.get("missingEvidence", ""), strategy]
                changed_query = "；".join(parts)
                key = (obl_id, missing_source)
                if key not in seen_queries:
                    seen_queries.add(key)
                    requery_queries.append({
                        "obligationId": obl_id,
                        "query": changed_query,
                        "missingSource": missing_source,
                    })
        
        missing = {gap.get("obligationId") for gap in gaps}
        progress_plan = [{**item, "status": "gap" if any(obl["obligationId"] in missing for obl in item.get("obligations", [])) else "completed"}
                         for item in plan]
        repo_update(
            run_id,
            lambda r: {**r, "state": {**(r.get("state") or {}), "plan": progress_plan, "gaps": gaps, "stopReason": stop_reason}},
            expected_revision=None,
        )
        
        new_requery_count = requery_count
        if gaps and not stop_reason and requery_queries:
            new_requery_count = requery_count + 1
        
        return {
            "gaps": gaps,
            "stop_reason": stop_reason,
            "requery_count": new_requery_count,
            "requery_queries": requery_queries,
            "prev_source_count": current_source_count,
        }
    
    return node


def make_synthesize_node(
    llm_invoke: Callable[..., dict],
    repo_update: Callable[[str, Callable, dict | None], dict],
) -> Callable[[GraphState], dict]:
    """Synthesize total answer from verified evidence. Uses reserve pool.
    
    Generates ONE synthesis for the total question. Sections organized by output kind
    using claim IDs mapped to sections. No unchecked model prose in report body.
    """
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        
        record = repo_update(run_id, lambda r: {**r, "stage": "synthesize"}, expected_revision=None)
        question = record.get("question", "")
        evidence = record.get("state", {}).get("evidence", [])
        gaps = record.get("state", {}).get("gaps", [])
        brief_state = record.get("state", {})
        output_kind = brief_state.get("outputKind", "direction_survey")
        from services.deep_research.answer_constraints import requested_character_limit
        requested_limit = requested_character_limit(question)
        from services.deep_research.synthesis import OUTPUT_KIND_SECTIONS
        section_templates = OUTPUT_KIND_SECTIONS.get(output_kind, OUTPUT_KIND_SECTIONS["direction_survey"])
        claim_limit = 5 if output_kind == 'paper_comparison' else (2 if requested_limit and requested_limit <= 300 else 3 if requested_limit else 12)
        paper_titles = {m.get('materialId'): m.get('title', '') for m in record.get('materials', [])}
        
        # Format evidence summaries with obligation binding
        from services.deep_research.selection import balanced_sample, surrounding_context, comparison_evidence_order
        evidence_summaries = []
        evidence_aliases = {}
        source_aliases = {}
        source_registry = {}
        candidates = comparison_evidence_order(evidence, paper_titles) if output_kind == 'paper_comparison' else evidence
        for ev in balanced_sample(candidates,
                lambda item: (item.get("sourceWorkId", ""), tuple(item.get("obligationIds", []))), 20):
            alias = f"E{len(evidence_aliases) + 1}"
            evidence_aliases[alias] = ev['evidenceId']
            source_id = ev.get('sourceWorkId', '')
            if source_id not in source_aliases:
                source_aliases[source_id] = f'P{len(source_aliases) + 1}'
                source_registry[source_aliases[source_id]] = {
                    'workId': source_id,
                    'title': paper_titles.get(source_id, '') or ev.get('sourceTitle', '')}
            evidence_summaries.append({
                "evidenceId": alias,
                "quote": ev.get("quote", ""),
                "source": source_aliases[source_id],
                "sourceContext": surrounding_context(ev),
                **({'tableData': ev['tableData']} if ev.get('tableData') is not None else {}),
                'location': {key: value for key, value in ev.get('location', {}).items()
                             if key not in {'chunk', 'pageResolution'}},
                **({'conditions': ev['conditions']} if ev.get('conditions') else {}),
                "obligations": ev.get("obligationIds", []),
                "accessLevel": ev.get("accessLevel", "fulltext"),
            })
        
        from uuid import uuid4
        from services.deep_research.prompt_budget import fit_evidence_prompt
        evidence_marker = uuid4().hex
        claim_fields = 'claimId, text, kind, evidenceRefs, conditions, obligationIds, detailLevel'
        if output_kind == 'experiment_design':
            claim_fields += ', designRole (required on every proposal/hypothesis), executionSpec (required for groups, data and analysis roles)'
        synthesis_obligations = [{k: o[k] for k in ('obligationId', 'question', 'purpose', 'requestExcerpt', 'requiredSources') if k in o}
                                 for p in brief_state.get('plan', []) for o in p.get('obligations', [])]
        prompt = f"""Synthesize a complete answer to the research question.
Question: {question}
Output kind: {output_kind}
Strict total character limit: {requested_limit or 'concise, no explicit maximum'}
Answer directly and omit secondary quantitative examples. Conditions count toward the same limit.
Claim count is independent of display length: shorten each statement rather than merging unrelated facts.
Evidence count: {len(evidence)}
User clarification: {brief_state.get('clarification', '')}
Gaps: {json.dumps([g.get('question') for g in gaps[:5]], ensure_ascii=False)}
Research questions (answer_requirement is a requested deliverable; supporting_research informs it): {json.dumps(synthesis_obligations, ensure_ascii=False, separators=(',', ':'))}
Source registry (P keys identify papers, not evidenceRefs): {json.dumps(source_registry, ensure_ascii=False, separators=(',', ':'))}

Evidence summaries:
{evidence_marker}

Return ONLY compact JSON with:
- sections: array of {{title, claimIds: [claim_id_strings]}}
- claims: array of {{{claim_fields}}}
Table measurements require tableBindings: [{{evidenceId,rowNumber,groupIndex,metric,value}}].
Copy exact tableData row, zero-based group, metric and string value. Name dataset, method variant,
metric and value together; no anonymous numeric series. Without tableData use qualitative evidence;
never bypass table checks by relabeling a reported measurement as inference.
Use ONLY supplied E IDs in evidenceRefs. Evidence IDs are routing keys only: keep E1/E2/... and raw IDs OUT of text and conditions.
P keys are also internal: use source titles in prose, never P1/P2/....
Use source names in prose; UI supplies links. Missing selected evidence does not prove authors omitted a test.
Limitations are evidence-bounded inference claims. Never invent results or present unchecked claims as verified.
Section titles MUST be selected from {json.dumps(section_templates, ensure_ascii=False)}.
Sections reference actual claimIds. All facts, proposals and hypotheses require claims and sections;
no extra unchecked prose. At most {claim_limit} claims, each independently checkable; never merge
unrelated papers, benchmarks or protocols to shorten the answer. For two requested points use at most two claims.
Write concise understandable Chinese, explaining technical components, conditioning inputs and activation rules;
not English placeholders or generic 'depends on the input/view'. Answer each requested aspect or state its
specific evidence limitation. Respect scope and total text+conditions length; put conflicting conditions beside conclusions.
Kinds: reported, inference, hypothesis, proposal. Copy reported numbers exactly; derived ratios/differences are inferences.
Proposals are unexecuted choices, not existing facts. Preserve method labels and variant markers;
distinguish reproduced baselines from original-paper measurements and separate results from controlled trajectories.
With contextOmitted, never invent antecedents or attribute baseline findings to the proposed method.
Abstract-only claims use detailLevel="abstract" and explicitly limit their scope; otherwise "fulltext".
Experiment designs must cover hypothesis, groups, controls, data, metrics, steps, confounders and decisions.
Orient losses before formulas, distinguish conditional/averaged effects and paper distillation from proposed truncation."""

        if output_kind == 'paper_comparison':
            prompt += "\nFor a comparison, separate each paper's reported evidence from the cross-paper judgment. " \
                      "Where evidence exists, provide one short reported claim per paper, followed by a separate " \
                      "inference about comparability. A baseline reproduced in paper A is a result of paper A, " \
                      "not a measurement from paper B. Keep each numerical tuple with its own dataset and protocol. " \
                      "Do not transfer an abstract's resolution or speed claim onto a main-table row without evidence. " \
                      "Prefer a supported qualitative tradeoff over a long list of numbers whose conditions cannot " \
                      "fit the requested length. If one paper lacks evidence, record that gap instead of inventing its claim. " \
                      "A cross-paper judgment must cite the supplied evidence from both papers that supports it. " \
                      "Distinguish documented conflicting conditions from conditions not established by the selected evidence. " \
                      "Unknown hardware or resolution is not proof that hardware or resolution differs. " \
                      "Discuss every requested tradeoff (including quality) before adding secondary ablation examples."
        
        if output_kind == "experiment_design":
            from services.deep_research.experimental_reasoning import FACTORIAL_REFERENCE, design_requirements
            prompt += "\nStatistical reference (apply only if the design has two binary factors):\n" + FACTORIAL_REFERENCE
            from services.deep_research.execution_spec import EXECUTION_SPEC_CONTRACT
            prompt += '\n' + EXECUTION_SPEC_CONTRACT
            prompt += '\nEach proposed design claim MUST have one designRole from the contract below. ' \
                      'Use exactly one complete claim per role; keep its configuration and decision rules together. ' \
                      'These are proposals, not facts about the paper. ' \
                      'Do not replace a concrete choice with “keep everything fixed”. If no specific split/budget ' \
                      'is documented, choose and label a reproducible proposed protocol, not an invented paper setting.\n' \
                      + design_requirements(brief_state.get('metricDomains'))
        template = prompt
        prompt, evidence_summaries = fit_evidence_prompt(evidence_summaries,
            lambda rows: template.replace(evidence_marker, json.dumps(rows, ensure_ascii=False, separators=(',', ':')), 1))
        evidence_aliases = {row['evidenceId']: evidence_aliases[row['evidenceId']] for row in evidence_summaries}
        result = llm_invoke(run_id, "synthesize", prompt, {"max_tokens": 4000, "temperature": 0.2}, use_reserve=True)
        finish = (result.get('finishReason', result.get('finish_reason')) if isinstance(result, dict)
                  else getattr(result, 'finish_reason', None))
        if finish == 'length':
            return {'error_code': 'invalid_synthesis_response'}
        
        if hasattr(result, "content"):
            content = result.content
        elif isinstance(result, dict):
            content = result.get("content", "{}")
        else:
            content = str(result)
        
        parsed = _safe_parse_json(content)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("claims"), list):
            return {"error_code": "invalid_synthesis_response"}
        from services.deep_research.answer_constraints import compact_answer, resolve_evidence_aliases
        parsed = resolve_evidence_aliases(parsed, evidence_aliases)
        if output_kind == "experiment_design":
            from services.deep_research.execution_materialization import materialize_execution_claim
            parsed['claims'] = [materialize_execution_claim({**claim, 'designContractVersion': 2})
                                if isinstance(claim, dict) else claim for claim in parsed['claims']]
        parsed = compact_answer(parsed, question,
            lambda prompt: llm_invoke(run_id, "synthesize_compact", prompt,
                {"max_tokens": 2000, "temperature": 0.0}), _safe_parse_json,
            output_kind=output_kind, evidence=evidence)
        if parsed is None:
            return {"error_code": "invalid_synthesis_response"}
        
        if output_kind == "experiment_design":
            # Compaction must not hide required settings back in metadata.
            parsed['claims'] = [materialize_execution_claim({**claim, 'designContractVersion': 2})
                                if isinstance(claim, dict) else claim for claim in parsed['claims']]
            from services.deep_research.answer_constraints import answer_character_count
            if requested_limit and answer_character_count(parsed) > requested_limit:
                return {"error_code": "invalid_synthesis_response"}

        report_version_id = f"report_{run_id}_v1"
        
        repo_update(
            run_id,
            lambda r: {
                **r,
                "state": {
                    **(r.get("state") or {}),
                    "reportVersionId": report_version_id,
                    "reportBody": parsed,
                },
            },
            expected_revision=None,
        )
        
        return {"report_version_id": report_version_id}
    
    return node


def make_verify_node(
    verify_claims_fn: Callable[[list, list, Callable | None], dict],
    semantic_check_fn: Callable[[list, list], list] | None,
    repo_update: Callable[[str, Callable, dict | None], dict],
    llm_invoke: Callable[..., dict] | None = None,
) -> Callable[[GraphState], dict]:
    """Verify claims against evidence with literal and semantic checks. Semantic uses reserve."""
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        
        if state.get("error_code"):
            return {}
        record = repo_update(run_id, lambda r: {**r, "stage": "verify"}, expected_revision=None)
        report_body = record.get("state", {}).get("reportBody", {})
        evidence = record.get("state", {}).get("evidence", [])
        
        claims = report_body.get("claims", [])
        
        # Semantic check uses reserve pool (wrapped to pass use_reserve flag)
        def budgeted_semantic(claims_to_check: list, evidence_list: list) -> list:
            if semantic_check_fn is None:
                return []
            return semantic_check_fn(claims_to_check, evidence_list)
        
        from services.deep_research.final_coverage import audit_final_answer
        from services.deep_research.coverage_repair import prepare_coverage_repair, merge_verified_revisions
        saved = record.get('state', {})
        if saved.get('repairAttempted') and 'initialAnswerCoverage' in saved and 'repairTargets' in saved:
            verification_result = saved['initialVerification']
            answer_coverage = saved['initialAnswerCoverage']
            repair_targets = saved['repairTargets']
        else:
            verification_result = verify_claims_fn(claims, evidence, budgeted_semantic)
            current = repo_update(run_id, lambda r: r, expected_revision=None)
            answer_coverage = audit_final_answer(run_id, record.get('question', ''),
                saved.get('plan', []), verification_result.get('accepted', []),
                evidence, llm_invoke, _safe_parse_json, budget=current.get('budget'))
            repair_targets = prepare_coverage_repair(report_body, verification_result,
                answer_coverage if answer_coverage.get('status') == 'checked' else {'gaps': []})
        if saved.get('repairCompleted') and saved.get('verifiedReport'):
            return {'claim_ids': [c['claimId'] for c in saved['verifiedReport'].get('verifiedClaims', [])]}

        # Repair at most once, using the normal call pool so the final verifier's
        # reserve remains protected. Repaired wording passes the same checks again.
        if repair_targets.get("rejected") and llm_invoke:
            repo_update(run_id, lambda r: {**r, "state": {**r.get("state", {}), "repairAttempted": True,
                "initialVerification": verification_result, 'initialAnswerCoverage': answer_coverage,
                'repairTargets': repair_targets}}, expected_revision=None)
            from services.deep_research.repair import repair_rejected
            from services.deep_research.contracts import BudgetExhaustedError
            def invoke_repair(prompt):
                # Admit the rewrite and its independent verification as a pair.
                # Do not spend the final seconds on wording that cannot be checked.
                from datetime import datetime, UTC
                maximum = float(record.get('budget', {}).get('maxWallClockSeconds') or 0)
                started = record.get('startedAt')
                if maximum and started:
                    elapsed = (datetime.now(UTC) - datetime.fromisoformat(started.replace('Z', '+00:00'))).total_seconds()
                    minimum = min(90.0, maximum / 4)
                    if maximum - elapsed < minimum:
                        repo_update(run_id, lambda r: {**r, 'state': {**r.get('state', {}),
                            'repairStatus': 'skipped_time', 'repairTimeRequiredSeconds': minimum}}, expected_revision=None)
                        raise BudgetExhaustedError('repairTimeSeconds', maximum - minimum, elapsed)
                try:
                    response = llm_invoke(run_id, "repair_claims", prompt,
                        {"max_tokens": 3000, "temperature": 0.0})
                except BudgetExhaustedError as exc:
                    repo_update(run_id, lambda r: {**r, "state": {**r.get("state", {}),
                        "repairStatus": "skipped_budget", "repairLimit": exc.details}}, expected_revision=None)
                    raise
                finish = (response.get('finishReason', response.get('finish_reason'))
                          if isinstance(response, dict) else getattr(response, 'finish_reason', None))
                repo_update(run_id, lambda r: {**r, "state": {**r.get("state", {}),
                    "repairStatus": "output_truncated" if finish == 'length' else "response_received"}},
                    expected_revision=None)
                return response
            try:
                revised = saved.get('repairDraft')
                if revised is None:
                    from services.deep_research.repair_budget import repair_prompt_byte_limit
                    current = repo_update(run_id, lambda r: r, expected_revision=None)
                    revised = repair_rejected(report_body, repair_targets, evidence, record.get("question", ""),
                        invoke_repair, _safe_parse_json,
                        max_prompt_bytes=repair_prompt_byte_limit(current.get('budget', {})),
                        metric_domains=record.get('state', {}).get('metricDomains'))
                    repo_update(run_id, lambda r: {**r, 'state': {**r.get('state', {}),
                        'repairDraft': revised}}, expected_revision=None)
                if revised:
                    def revised_semantic(targets, sources):
                        check = getattr(semantic_check_fn, 'check_revisions', None)
                        if check:
                            return check(targets, sources, repair_targets.get('accepted', []))
                        return budgeted_semantic(targets, sources)
                    merged = saved.get('repairVerification')
                    if merged is None:
                        checked = verify_claims_fn(revised, evidence, revised_semantic)
                        merged = merge_verified_revisions(verification_result, checked)
                        repo_update(run_id, lambda r: {**r, 'state': {**r.get('state', {}),
                            'repairVerification': merged}}, expected_revision=None)
                    if merged.get('accepted') != verification_result.get('accepted'):
                        current = repo_update(run_id, lambda r: r, expected_revision=None)
                        answer_coverage = audit_final_answer(run_id, record.get('question', ''),
                            record.get('state', {}).get('plan', []), merged.get('accepted', []),
                            evidence, llm_invoke, _safe_parse_json, budget=current.get('budget'))
                    verification_result = merged
            except BudgetExhaustedError as exc:
                repo_update(run_id, lambda r: {**r, 'state': {**r.get('state', {}),
                    'repairStatus': r.get('state', {}).get('repairStatus') or 'skipped_budget',
                    'repairLimit': exc.details}},
                    expected_revision=None)
        
        accepted = verification_result.get("accepted", [])
        rejected = verification_result.get("rejected", [])

        # Update report with only verified claims
        verified_report = {
            **report_body,
            "verifiedClaims": accepted,
            "rejectedClaims": rejected,
            "answerCoverage": answer_coverage,
            "verificationSummary": {
                "accepted": len(accepted),
                "rejected": len(rejected),
            },
        }
        
        repo_update(
            run_id,
            lambda r: {
                **r,
                "state": {**(r.get("state") or {}), "verifiedReport": verified_report,
                          'repairCompleted': bool(r.get('state', {}).get('repairAttempted'))},
            },
            expected_revision=None,
        )
        
        return {"claim_ids": [c.get("claimId") for c in accepted]}
    
    return node


def make_publish_node(
    repo_publish: Callable[..., tuple],
    repo_update: Callable[[str, Callable, dict | None], dict],
) -> Callable[[GraphState], dict]:
    """Publish verified report atomically to outbox.
    
    Renders ONLY verified claims or clearly labeled proposals/hypotheses.
    Sections organized by output kind using claim IDs to sections.
    No unchecked model prose in report body. No repeated synthesis model call.
    """
    
    def node(state: GraphState) -> dict:
        run_id = state.get("run_id", "")
        if state.get("error_code"):
            return {}
        report_version_id = state.get("report_version_id") or f"report_{run_id}_v1"
        execution_epoch = state.get("execution_epoch", 0)
        
        record = repo_update(run_id, lambda r: {**r, "stage": "publish"}, expected_revision=None)
        verified_report = record.get("state", {}).get("verifiedReport", {})
        brief_state = record.get("state", {})
        output_kind = brief_state.get("outputKind", "direction_survey")
        
        accepted_claims = verified_report.get("verifiedClaims", [])
        rejected_count = len(verified_report.get("rejectedClaims", []))
        from services.deep_research.final_coverage import remaining_retrieval_gaps
        audit = verified_report.get('answerCoverage', {})
        from services.deep_research.obligation_purpose import nonblocking_research_obligations
        research_notes = nonblocking_research_obligations(brief_state.get('plan', []),
            record.get('question', ''), accepted_claims, audit.get('verdicts'),
            audit.get('wholeQuestionId'), audit.get('invalidAspectObligations', [])) \
            if audit.get('status') == 'checked' else []
        research_questions = {o.get('obligationId'): o.get('question', '')
                              for item in brief_state.get('plan', []) for o in item.get('obligations', [])}
        research_notes = [{**note, 'question': research_questions.get(note['obligationId'], '')}
                          for note in research_notes]
        gaps = [*remaining_retrieval_gaps(record.get('state', {}).get('gaps', []), audit,
                    accepted_claims, record.get('state', {}).get('evidence', []),
                    plan=brief_state.get('plan', []), question=record.get('question', '')),
                *audit.get('gaps', [])]
        
        factual_claims = [claim for claim in accepted_claims if claim.get("kind") in {"reported", "inference"}]
        from services.deep_research.reporting import build_sections, conversation_summary, verification_notice
        sections = build_sections(accepted_claims, output_kind, verified_report.get("sections"))
        if output_kind == "experiment_design":
            from services.deep_research.synthesis import OUTPUT_KIND_SECTIONS
            from services.deep_research.experimental_reasoning import DESIGN_ROLE_LABELS, missing_design_roles
            present = {section["title"] for section in sections}
            gaps = [*gaps, *[{"question": f"补齐实验方案：{title}", "missingEvidence": "尚未形成经过检查的方案内容"}
                            for title in OUTPUT_KIND_SECTIONS["experiment_design"] if title not in present]]
            gaps.extend({'question': f'补齐实验方案：{DESIGN_ROLE_LABELS[role]}',
                         'missingEvidence': '这项方案要求尚未通过完整性和逻辑核验', 'designRole': role}
                        for role in missing_design_roles(accepted_claims))
        complete_proposal = output_kind in {"experiment_design", "research_entry"} and bool(evidence := record.get("state", {}).get("evidence", []))
        if not accepted_claims:
            outcome = OUTCOME_INCONCLUSIVE
        elif gaps or (rejected_count and audit.get('status') != 'checked') or (not factual_claims and not complete_proposal):
            outcome = OUTCOME_PARTIAL
        elif accepted_claims:
            outcome = OUTCOME_COMPLETE
        else:
            outcome = OUTCOME_INCONCLUSIVE
        
        # Build sections from verified claims only, organized by output kind
        
        # Build safe summary from accepted claims only
        safe_summary = conversation_summary(accepted_claims, outcome,
            evidence=record.get('state', {}).get('evidence', []))
        
        publication_payload = {
            "reportVersionId": report_version_id,
            "outputKind": output_kind,
            "summary": safe_summary,
            "sections": sections,
            "claims": accepted_claims,
            "evidence": evidence if (evidence := record.get("state", {}).get("evidence", [])) else [],
            "limitations": verification_notice(accepted_claims),
            "gaps": gaps,
            "researchNotes": research_notes,
            "outcome": outcome,
        }
        
        dedup_key = f"{run_id}:{report_version_id}"
        missing_ids = {gap.get('obligationId') for gap in gaps if isinstance(gap, dict)}
        broad_gap = any(not isinstance(gap, dict) or gap.get('wholeQuestion') for gap in gaps)
        final_plan = [{**item, 'status': 'gap' if broad_gap or any(
            o.get('obligationId') in missing_ids for o in item.get('obligations', [])) else 'completed'}
            for item in brief_state.get('plan', [])]
        
        pub_record, created = repo_publish(
            run_id=run_id,
            dedup_key=dedup_key,
            payload=publication_payload,
            outcome=outcome,
            expected_epoch=execution_epoch,
            report_text=_render_report_markdown(publication_payload),
        )
        
        repo_update(
            run_id,
            lambda r: {
                **r,
                "state": {
                    **(r.get("state") or {}),
                    "publicationId": pub_record.get("publicationId", ""),
                    "reportText": _render_report_markdown(publication_payload),
                    "plan": final_plan,
                },
            },
            expected_revision=None,
        )
        
        return {
            "publication_id": pub_record.get("publicationId", ""),
            "outcome": outcome,
        }
    
    return node


def _build_verified_sections(accepted_claims: list[dict], output_kind: str) -> list[dict]:
    from services.deep_research.reporting import build_sections
    return build_sections(accepted_claims, output_kind)


def _render_report_markdown(payload: dict) -> str:
    from services.deep_research.reporting import render_report
    return render_report(payload)


# ── Conditional Edges ──────────────────────────────────────────────────────────

def route_after_resolve_brief(state: GraphState) -> str:
    if state.get("budget_exhausted"):
        return "publish"
    if state.get("clarification_needed"):
        return "wait_clarification"  # Route to clarification node which calls interrupt()
    if state.get("error_code"):
        return "fail"
    return "plan"


def route_after_assess(state: GraphState) -> str:
    stop_reason = state.get("stop_reason", "")
    gaps = state.get("gaps", [])
    requery_count = state.get("requery_count", 0)
    budget_exhausted = state.get("budget_exhausted", False)
    requery_queries = state.get("requery_queries", [])
    
    if state.get("error_code"):
        return "fail"
    if budget_exhausted:
        return "synthesize"
    if stop_reason == "covered" or not gaps:
        return "synthesize"
    if stop_reason in ("max_requery", "too_many_gaps", "no_new_evidence"):
        return "synthesize"
    # Only requery if we have changed queries and haven't exceeded bound
    if requery_count <= state.get("max_requery_rounds", 2) and requery_queries:
        return "acquire"
    return "synthesize"


def route_after_publish(state: GraphState) -> str:
    if state.get("error_code"):
        return "fail"
    return "end"


# ── Graph Builder ──────────────────────────────────────────────────────────────

def build_deep_research_graph(
    *,
    llm_invoke: Callable[..., dict],
    retrieve_fn: Callable[[str, str, int], list],
    read_fn: Callable[[str, str], dict],
    scope_validator: Callable[[str, str], bool],
    make_evidence_fn: Callable[..., dict],
    coverage_gaps_fn: Callable[[list, list, list], list],
    verify_claims_fn: Callable[[list, list, Callable | None], dict],
    semantic_check_fn: Callable[[list, list], list] | None = None,
    repo_update: Callable[[str, Callable, dict | None], dict],
    repo_publish: Callable[[str, str, dict], tuple],
    validate_plan_fn: Callable[[list], list],
    checkpoint_conn: sqlite3.Connection | None = None,
    external_acquire: Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    extract_batch_size: int = 1,
) -> Any:
    """Build the compiled LangGraph with persistent checkpoints.
    
    Args:
        llm_invoke: Function(run_id, node_name, prompt, extra_body, use_reserve=False) -> {content, usage}
        retrieve_fn: Tracked retriever function
        read_fn: Tracked reader function  
        scope_validator: Authoritative validator (injected, fail-closed)
        make_evidence_fn: From verification module
        coverage_gaps_fn: From coverage module
        verify_claims_fn: From verification module
        semantic_check_fn: Optional semantic checker (uses reserve pool)
        repo_update: Repository update_run function
        repo_publish: Repository publish_report function
        validate_plan_fn: From coverage module
        checkpoint_conn: Long-lived SQLite connection for checkpoints (required for production)
        external_acquire: Optional AcademicAcquisition callback for external sources
    
    Returns:
        Compiled LangGraph ready for invoke/stream
    """
    if StateGraph is None:
        raise RuntimeError("LangGraph not available - install langgraph package")
    
    workflow = StateGraph(GraphState)
    def bounded(function):
        def execute(state):
            from services.deep_research.contracts import BudgetExhaustedError
            try:
                return function(state)
            except BudgetExhaustedError:
                return {"budget_exhausted": True, "stop_reason": "budget_exhausted"}
        return execute
    
    # Add nodes
    workflow.add_node("resolve_brief", bounded(make_resolve_brief_node(llm_invoke, repo_update)))
    workflow.add_node("wait_clarification", make_wait_for_clarification_node())
    workflow.add_node("plan", bounded(make_plan_node(llm_invoke, repo_update, validate_plan_fn)))
    workflow.add_node("acquire", make_acquire_node(retrieve_fn, scope_validator, repo_update, external_acquire=external_acquire))
    workflow.add_node("read", make_read_node(read_fn, scope_validator, repo_update))
    if extract_batch_size > 1:
        from services.deep_research.extraction import make_batched_extract_node
        extractor = make_batched_extract_node(llm_invoke, make_evidence_fn, scope_validator, repo_update,
                                               batch_size=min(extract_batch_size, 3))
    else:
        extractor = make_extract_node(llm_invoke, make_evidence_fn, scope_validator, repo_update)
    workflow.add_node("extract", bounded(extractor))
    workflow.add_node("assess", make_assess_node(coverage_gaps_fn, repo_update, llm_invoke=llm_invoke))
    workflow.add_node("synthesize", bounded(make_synthesize_node(llm_invoke, repo_update)))
    workflow.add_node("verify", make_verify_node(verify_claims_fn, semantic_check_fn, repo_update, llm_invoke=llm_invoke))
    workflow.add_node("publish", make_publish_node(repo_publish, repo_update))
    
    # Set entry point
    workflow.set_entry_point("resolve_brief")
    
    # Add edges - clarification node calls interrupt() internally
    workflow.add_conditional_edges("resolve_brief", route_after_resolve_brief, {
        "plan": "plan",
        "wait_clarification": "wait_clarification",  # Routes to node that calls interrupt()
        "publish": "publish",
        "fail": END,
    })
    
    # After clarification interrupt, resume goes to plan
    workflow.add_edge("wait_clarification", "plan")
    
    workflow.add_conditional_edges("plan", lambda state: "fail" if state.get("error_code") else "publish" if state.get("budget_exhausted") else "assess" if state.get('assess_inherited') else "acquire",
                                   {"fail": END, "acquire": "acquire", "assess": "assess", "publish": "publish"})
    workflow.add_edge("acquire", "read")
    workflow.add_edge("read", "extract")
    workflow.add_conditional_edges("extract", lambda state: "synthesize" if state.get("budget_exhausted") else "assess",
                                   {"synthesize": "synthesize", "assess": "assess"})
    
    workflow.add_conditional_edges("assess", route_after_assess, {
        "acquire": "acquire",
        "synthesize": "synthesize",
        "fail": END,
    })
    
    workflow.add_edge("synthesize", "verify")
    workflow.add_edge("verify", "publish")
    
    workflow.add_conditional_edges("publish", route_after_publish, {
        "end": END,
        "fail": END,
    })
    
    # Compile with checkpointer - REQUIRED for production
    if checkpoint_conn is not None:
        if SqliteSaver is None:
            raise RuntimeError("SqliteSaver not available")
        checkpointer = SqliteSaver(checkpoint_conn)
        return workflow.compile(checkpointer=checkpointer)
    
    # For testing without persistence
    return workflow.compile()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_parse_json(text: str) -> Any:
    """Parse JSON from LLM output, handling markdown fences and partial responses."""
    if not text:
        return {}
    
    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines if they're fences
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object/array in the text
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = cleaned.find(start_char)
            end = cleaned.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end+1])
                except json.JSONDecodeError:
                    continue
        
        logger.warning("Failed to parse structured model response (%s bytes)", len(text.encode("utf-8")))
        return {}


def estimate_prompt_tokens(prompt: str) -> int:
    """Conservative token estimation for UTF-8 text.
    
    Chinese characters typically require more tokens than ASCII.
    Uses byte length / 3 as conservative estimate (NOT upper bound).
    This is the actual byte-based calculation, not capped at any maximum.
    """
    byte_length = len(prompt.encode("utf-8"))
    return max(1, byte_length // 3)


def check_deadline(started_at: float, deadline_seconds: float) -> bool:
    """Check if deadline has been exceeded. Returns True if still within deadline."""
    if deadline_seconds <= 0:
        return True
    elapsed = time.monotonic() - started_at
    return elapsed < deadline_seconds


def remaining_seconds(started_at: float, deadline_seconds: float) -> float:
    """Get remaining seconds until deadline. Returns 0 if exceeded."""
    if deadline_seconds <= 0:
        return float("inf")
    elapsed = time.monotonic() - started_at
    remaining = deadline_seconds - elapsed
    return max(0.0, remaining)
