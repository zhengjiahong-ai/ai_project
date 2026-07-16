"""Research workflow tools: citation graph traversal, reasoning chains,
conflict adjudication, hypothesis generation, parallel research, past research
recall, cross-lingual search, adversarial review, and domain specialists.

All tool handlers and their registrations extracted from tool_registry.py.
"""

from typing import Any, Dict

from services.adversarial_reviewer import adversarial_review
from services.citation_graph import traverse_citation_graph
from services.conflict_adjudicator import adjudicate_conflict
from services.cross_lingual import cross_lingual_search
from services.domain_specialists import activate_domain_specialist
from services.hypothesis_engine import generate_and_verify_hypotheses
from services.parallel_research import dispatch_parallel_research
from services.reasoning_chain import build_reasoning_chain
from services.research_memory import recall_relevant_past_research
from services.trace_service import record_counter, trace_step
from services.tools._common import _clean_text
from services.tool_registry import ToolValidationError, _object_output, _safety_scope


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

def _expand_citation_graph_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    paper_id = (payload.get("paperId") or "").strip()
    if not paper_id:
        raise ToolValidationError("expand_citation_graph requires a non-empty paperId.")
    direction = str(payload.get("direction") or "both")
    max_depth = int(payload.get("maxDepth") or 3)
    max_papers = int(payload.get("maxPapers") or 50)

    with trace_step("tool_expand_citation_graph", input_size=len(paper_id)) as step:
        record_counter("citationGraphCalls")
        try:
            result = traverse_citation_graph(
                paper_id, direction=direction,
                max_depth=max_depth, max_papers=max_papers,
            )
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = result.get("nodeCount", 0)
        step["meta"] = {
            "status": result["status"],
            "nodeCount": result["nodeCount"],
            "edgeCount": result["edgeCount"],
        }
        if result["status"] != "success":
            record_counter("citationGraphFailures")
        return result


def _trace_reasoning_chain_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    claim = (payload.get("claim") or "").strip()
    if not claim:
        raise ToolValidationError("trace_reasoning_chain requires a non-empty claim.")
    evidence_sources = payload.get("evidenceSources") or []

    with trace_step("tool_reasoning_chain", input_size=len(claim)) as step:
        record_counter("reasoningChainCalls")
        try:
            result = build_reasoning_chain(claim, evidence_sources)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = result.get("nodeCount", 0)
        if result["status"] != "success":
            record_counter("reasoningChainFailures")
        return result


def _adjudicate_conflict_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    claim = (payload.get("claim") or "").strip()
    if not claim:
        raise ToolValidationError("adjudicate_conflict requires a non-empty claim.")
    pro = payload.get("proSources") or []
    con = payload.get("conSources") or []

    with trace_step("tool_adjudicate_conflict", input_size=len(claim)) as step:
        record_counter("adjudicateConflictCalls")
        try:
            result = adjudicate_conflict(claim, pro, con)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = len(result.get("reasoning", ""))
        step["meta"] = {"winner": result.get("winner"), "confidence": result.get("confidence")}
        if result["status"] != "success":
            record_counter("adjudicateConflictFailures")
        return result


def _generate_hypotheses_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    if not question:
        raise ToolValidationError("generate_and_verify_hypotheses requires a non-empty question.")
    findings = payload.get("findings") or []
    conflicts = payload.get("conflicts") or []
    gaps = payload.get("gaps") or []

    with trace_step("tool_generate_hypotheses", input_size=len(question)) as step:
        record_counter("hypothesesGeneratedCalls")
        try:
            result = generate_and_verify_hypotheses(question, findings, conflicts, gaps)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = result.get("hypothesisCount", 0)
        if result["status"] != "success":
            record_counter("hypothesesGeneratedFailures")
        return result


def _execute_tool_pipeline_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    goal = (payload.get("goal") or "").strip()
    if not goal:
        raise ToolValidationError("execute_tool_pipeline requires a non-empty goal.")

    from services.tool_orchestrator import execute_tool_pipeline

    with trace_step("tool_pipeline", input_size=len(goal)) as step:
        record_counter("toolPipelineCalls")
        try:
            result = execute_tool_pipeline(goal)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = result.get("stepCount", 0)
        if result["status"] != "success":
            record_counter("toolPipelineFailures")
        return result


def _parallel_research_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    sub_questions = payload.get("subQuestions") or []
    max_agents = int(payload.get("maxAgents") or 4)
    if not question:
        raise ToolValidationError("parallel_research requires a non-empty question.")
    if not sub_questions:
        raise ToolValidationError("parallel_research requires subQuestions.")
    with trace_step("tool_parallel_research", input_size=len(question)) as step:
        record_counter("parallelResearchCalls")
        result = dispatch_parallel_research(question, sub_questions, max_agents=max_agents)
        step["outputSize"] = result.get("agentCount", 0)
        if result["status"] != "success":
            record_counter("parallelResearchFailures")
        return result


def _recall_past_research_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    domain = (payload.get("domain") or "").strip()
    if not question:
        raise ToolValidationError("recall_past_research requires a non-empty question.")
    with trace_step("tool_recall_past_research", input_size=len(question)) as step:
        record_counter("recallMemoryCalls")
        result = recall_relevant_past_research(question, domain=domain)
        step["outputSize"] = result.get("count", 0)
        if result["status"] != "success":
            record_counter("recallMemoryFailures")
        return result


def _cross_lingual_search_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = (payload.get("query") or "").strip()
    if not query:
        raise ToolValidationError("cross_lingual_search requires a query.")
    languages = payload.get("languages") or ["zh", "en", "ja", "de"]
    limit = int(payload.get("limitPerLang") or 5)
    with trace_step("tool_cross_lingual_search", input_size=len(query)) as step:
        record_counter("crossLingualCalls")
        result = cross_lingual_search(query, languages=languages, limit_per_lang=limit)
        step["outputSize"] = result.get("resultCount", 0)
        if result["status"] != "success":
            record_counter("crossLingualFailures")
        return result


def _adversarial_review_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    if not question:
        raise ToolValidationError("adversarial_review requires a question.")
    findings = payload.get("findings") or []
    evidence = payload.get("evidenceItems") or []
    conflicts = payload.get("conflicts") or []
    with trace_step("tool_adversarial_review", input_size=len(question)) as step:
        record_counter("adversarialReviewCalls")
        result = adversarial_review(question, findings, evidence, conflicts)
        step["outputSize"] = result.get("counterCount", 0)
        step["meta"] = {"overallConfidence": result.get("overallConfidence")}
        if result["status"] != "success":
            record_counter("adversarialReviewFailures")
        return result


def _activate_domain_specialist_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    domain = (payload.get("domain") or "").strip()
    if not domain:
        raise ToolValidationError("activate_domain_specialist requires a domain.")
    with trace_step("tool_activate_domain_specialist", input_size=len(domain)) as step:
        result = activate_domain_specialist(domain)
        step["outputSize"] = len(result.get("tools", []))
        return result


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_tools(registry) -> None:
    """Register all research workflow tools on *registry*."""

    registry.register(
        "expand_citation_graph",
        "Traverse the citation graph from a seed paper using Semantic Scholar. "
        "Supports forward (who cited this), backward (references), or both directions. "
        "Returns paper nodes with title/year/abstract/authors/citationCount and edges. "
        "Configurable max depth (1-4) and max papers (1-200).",
        {
            "type": "object",
            "required": ["paperId"],
            "properties": {
                "paperId": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 256,
                },
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "both"],
                },
                "maxDepth": {"type": "integer", "minimum": 1, "maximum": 4},
                "maxPapers": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
        _expand_citation_graph_tool,
        output_schema={
            "type": "object",
            "required": ["status", "seed", "nodes", "edges", "nodeCount", "edgeCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "seed": {"type": "object", "additionalProperties": True},
                "nodes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "edges": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "nodeCount": {"type": "integer", "minimum": 0},
                "edgeCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["citation_graph"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "trace_reasoning_chain",
        "Trace a scientific claim through multiple evidence sources and classify "
        "each source's stance: supports, contradicts, extends, replicates, or "
        "cites_without_engagement. Uses LLM for classification with rule-based fallback.",
        {
            "type": "object",
            "required": ["claim"],
            "properties": {
                "claim": {"type": "string", "minLength": 1, "maxLength": 500},
                "evidenceSources": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "additionalProperties": False,
        },
        _trace_reasoning_chain_tool,
        output_schema={
            "type": "object",
            "required": ["status", "claim", "chain", "summary", "nodeCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "claim": {"type": "string"},
                "chain": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "summary": {"type": "string"},
                "nodeCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["reasoning_chain"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "adjudicate_conflict",
        "Adjudicate a scientific disagreement between pro and con evidence sources. "
        "Evaluates methodology rigor, venue authority, recency, and replication. "
        "Returns winner (pro/con/inconclusive) with confidence and reasoning.",
        {
            "type": "object",
            "required": ["claim"],
            "properties": {
                "claim": {"type": "string", "minLength": 1, "maxLength": 300},
                "proSources": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "conSources": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "additionalProperties": False,
        },
        _adjudicate_conflict_tool,
        output_schema={
            "type": "object",
            "required": ["status", "claim", "winner", "confidence", "reasoning", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "claim": {"type": "string"},
                "winner": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "proScore": {"type": "number"},
                "conScore": {"type": "number"},
                "reasoning": {"type": "string"},
                "keyFactors": {"type": "array", "items": {"type": "string"}},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["conflict_adjudication"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "generate_and_verify_hypotheses",
        "Generate 3-5 testable scientific hypotheses from research findings, "
        "conflicts, and evidence gaps. Each hypothesis includes a statement, "
        "testable prediction, required evidence type, and search queries.",
        {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 500},
                "findings": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "conflicts": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "gaps": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        _generate_hypotheses_tool,
        output_schema={
            "type": "object",
            "required": ["status", "question", "hypotheses", "hypothesisCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "question": {"type": "string"},
                "hypotheses": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "hypothesisCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["hypothesis_engine"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "execute_tool_pipeline",
        "Plan and execute a multi-tool pipeline to achieve a research goal. "
        "The LLM generates a DAG of tool calls, then the orchestrator executes "
        "in topological order, feeding upstream outputs to downstream inputs. "
        "Fallback to simple search to fetch plan when LLM is unavailable.",
        {
            "type": "object",
            "required": ["goal"],
            "properties": {
                "goal": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            "additionalProperties": False,
        },
        _execute_tool_pipeline_tool,
        output_schema={
            "type": "object",
            "required": ["status", "goal", "plan", "results", "stepCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "goal": {"type": "string"},
                "plan": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "results": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "stepCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["tool_orchestrator"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "parallel_research",
        "Dispatch sub-questions to independent research agents that execute "
        "concurrently (up to 6 agents). Merges findings with cross-validation "
        "and LLM summary. Each agent runs search to fetch to judge independently.",
        {
            "type": "object",
            "required": ["question", "subQuestions"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 500},
                "subQuestions": {"type": "array", "items": {"type": "string"}},
                "maxAgents": {"type": "integer", "minimum": 1, "maximum": 6},
            },
            "additionalProperties": False,
        },
        _parallel_research_tool,
        output_schema={
            "type": "object",
            "required": ["status", "question", "subResults", "mergedFindings", "agentCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "question": {"type": "string"},
                "subResults": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "mergedFindings": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "crossValidation": {"type": "string"},
                "agentCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["parallel_research"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "recall_past_research",
        "Search past research findings for knowledge relevant to the current "
        "question. Returns semantically similar previous findings with evidence "
        "summaries. Uses keyword embedding for cross-session memory.",
        {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 500},
                "domain": {"type": "string", "maxLength": 100},
            },
            "additionalProperties": False,
        },
        _recall_past_research_tool,
        output_schema={
            "type": "object",
            "required": ["status", "question", "memories", "count", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "question": {"type": "string"},
                "memories": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "count": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_memory"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "cross_lingual_search",
        "Search across multiple languages for academic evidence. Translates the "
        "query into each target language, searches external academic providers, "
        "and translates results back. Supports zh/en/ja/de/fr/ko/es.",
        {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 300},
                "languages": {"type": "array", "items": {"type": "string"}},
                "limitPerLang": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "additionalProperties": False,
        },
        _cross_lingual_search_tool,
        output_schema={
            "type": "object",
            "required": ["status", "query", "results", "resultCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "query": {"type": "string"},
                "translations": {"type": "object", "additionalProperties": True},
                "results": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "resultCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["cross_lingual"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "adversarial_review",
        "Perform adversarial self-review of research findings. Generates "
        "counter-arguments as a skeptical reviewer, identifies weaknesses "
        "(single-source risk, confounding, methodology limitations), and "
        "adjusts confidence scores accordingly.",
        {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 300},
                "findings": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "evidenceItems": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "conflicts": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "additionalProperties": False,
        },
        _adversarial_review_tool,
        output_schema={
            "type": "object",
            "required": ["status", "reviewedFindings", "overallConfidence", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "reviewedFindings": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "overallConfidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "shouldSeekMoreEvidence": {"type": "boolean"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["adversarial_review"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "activate_domain_specialist",
        "Activate a domain-specific research agent with pre-configured tools, "
        "search queries, and evaluation criteria. Domains: cs, medical, bio, physics, econ.",
        {
            "type": "object",
            "required": ["domain"],
            "properties": {
                "domain": {"type": "string", "minLength": 1, "maxLength": 20},
            },
            "additionalProperties": False,
        },
        _activate_domain_specialist_tool,
        output_schema={
            "type": "object",
            "required": ["status", "domain", "tools", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "domain": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "string"}},
                "searchQueries": {"type": "array", "items": {"type": "string"}},
                "knowledgeBase": {"type": "string"},
                "promptExtension": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["domain_specialist"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
