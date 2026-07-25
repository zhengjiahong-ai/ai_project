"""Paper-related tool handlers and their registration.

This module extracts paper-skeleton, evidence-judgment, background-knowledge-graph,
critical-analysis, page-translation, knowledge-graph-neighborhood, and paper-draft
tools from the central tool registry into a dedicated module.
"""

from typing import Any

from schemas.requests import (
    BackgroundKnowledgeRequest,
    DeepAnalysisRequest,
    PageTranslationRequest,
)
from services import (
    analysis_service,
    background_knowledge_service,
    knowledge_graph_store,
    page_translation_service,
)
from services.retrieval_judge_service import judge_evidence_quality
from services.tool_registry import ToolValidationError, _object_output, _safety_scope
from services.tools._common import _clean_text, _coerce_positive_int
from services.trace_service import record_counter, trace_step


def register_tools(registry) -> None:
    """Register all paper-related tools on the given ToolRegistry instance."""

    registry.register(
        "read_paper_skeleton",
        "Normalize a paper skeleton into reusable planning context.",
        {
            "type": "object",
            "properties": {
                "paperSkeleton": {"type": "object"},
                "maxSections": {"type": "integer", "minimum": 1, "maximum": 50},
                "maxCharsPerSection": {"type": "integer", "minimum": 1, "maximum": 5000},
            },
            "additionalProperties": False,
        },
        _read_paper_skeleton_tool,
        output_schema=_object_output(
            ["text", "sections"],
            {
                "text": {"type": "string"},
                "sections": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
        ),
        safety_scope=_safety_scope(["request_paper_skeleton"], network_access=False, sensitive_output=True),
    )
    registry.register(
        "judge_evidence",
        "Judge whether retrieved evidence is sufficient for a question.",
        {
            "type": "object",
            "required": ["question", "evidenceItems"],
            "properties": {
                "question": {"type": "string", "minLength": 1},
                "evidenceItems": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "keywords": {"type": "array", "items": {"type": "string", "minLength": 1}},
            },
            "additionalProperties": False,
        },
        _judge_evidence_tool,
        output_schema=_object_output(
            ["verdict", "confidence", "reason", "missingAspects", "shouldRetry", "judgeScore", "coverage", "retryReason"],
            {
                "verdict": {"type": "string", "enum": ["CORRECT", "AMBIGUOUS", "INCORRECT"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
                "missingAspects": {"type": "array", "items": {"type": "string"}},
                "shouldRetry": {"type": "boolean"},
                "judgeScore": {"type": "integer", "minimum": 0, "maximum": 100},
                "coverage": {"type": "object", "additionalProperties": True},
                "retryReason": {"type": "string"},
                "reflection": {"type": "string"},
                "suggestedQueries": {"type": "array", "items": {"type": "string"}},
            },
        ),
        safety_scope=_safety_scope(["provided_evidence"], network_access=False, sensitive_output=False),
    )
    registry.register(
        "generate_background_graph",
        "Generate prerequisite background knowledge graph and learning path.",
        {
            "type": "object",
            "properties": {
                "paper_topic": {},
                "user_knowledge_level": {},
                "reader_profile": {"type": "object"},
                "behavior_signals": {"type": "object"},
                "pdfId": {"type": "string"},
                "paperSkeleton": {"type": "object"},
                "paperStructure": {"type": "object"},
            },
            "additionalProperties": False,
        },
        _generate_background_graph_tool,
        output_schema=_object_output(
            ["background_knowledge"],
            {"background_knowledge": {"type": "array", "items": {"type": "string"}}},
        ),
        safety_scope=_safety_scope(
            ["request_context", "current_paper_index", "model_provider"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "run_critical_analysis",
        "Run evidence-based critical analysis for a paper.",
        {
            "type": "object",
            "properties": {
                "paper_content": {"type": "string"},
                "pdf_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        _run_critical_analysis_tool,
        output_schema=_object_output(
            ["claimed_contributions", "evidence_based_contributions", "overclaim_risks", "missing_evidence", "rag_sources"],
            {
                "claimed_contributions": {"type": "string"},
                "evidence_based_contributions": {"type": "string"},
                "overclaim_risks": {"type": "array", "items": {"type": "string"}},
                "missing_evidence": {"type": "array", "items": {"type": "string"}},
                "rag_sources": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
        ),
        safety_scope=_safety_scope(
            ["request_content", "current_paper_index", "model_provider"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "translate_page",
        "Translate a PDF page using the existing page translation service.",
        {
            "type": "object",
            "required": ["pageIndex", "pageText"],
            "properties": {
                "pdfId": {"type": "string", "minLength": 1},
                "pageIndex": {"type": "integer", "minimum": 0},
                "pageText": {"type": "string", "minLength": 1},
                "paperSkeleton": {"type": "object"},
                "pageLayout": {"type": "object"},
            },
            "additionalProperties": False,
        },
        _translate_page_tool,
        output_schema=_object_output(
            ["status", "pageIndex", "sourceText", "translatedText", "translatedBlocks", "renderMode"],
            {
                "status": {"type": "string", "enum": ["success"]},
                "pageIndex": {"type": "integer", "minimum": 0},
                "sourceText": {"type": "string"},
                "translatedText": {"type": "string"},
                "translatedBlocks": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "renderMode": {"type": "string", "enum": ["overlay", "plain"]},
            },
        ),
        safety_scope=_safety_scope(
            ["request_page_text", "model_provider"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "read_knowledge_graph_neighborhood",
        "Read a bounded one-hop neighborhood from persisted background knowledge graphs.",
        {
            "type": "object",
            "properties": {
                "paperIds": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "sourceIds": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "seedTerms": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "maxNodes": {"type": "integer", "minimum": 1, "maximum": 8},
                "maxEdges": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "additionalProperties": False,
        },
        _read_knowledge_graph_neighborhood_tool,
        output_schema=_object_output(
            ["status", "paperIds", "seedTerms", "nodes", "edges", "sourceIds", "provenanceSummary", "contextNote"],
            {
                "status": {"type": "string", "enum": ["available", "partial", "unavailable"]},
                "paperIds": {"type": "array", "items": {"type": "string"}},
                "seedTerms": {"type": "array", "items": {"type": "string"}},
                "nodes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "edges": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "sourceIds": {"type": "array", "items": {"type": "string"}},
                "provenanceSummary": {"type": "object", "additionalProperties": True},
                "contextNote": {"type": "string", "minLength": 1},
            },
        ),
        safety_scope=_safety_scope(["knowledge_graph_snapshots"], network_access=False, sensitive_output=True),
    )
    registry.register(
        "generate_paper_draft",
        "Generate a structured academic paper draft (Markdown + LaTeX) from "
        "research findings. Includes Abstract, Introduction, Related Work, "
        "Methodology, Results, Discussion, Conclusion, and References (BibTeX).",
        {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 500},
                "findings": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "evidenceItems": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "conflicts": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "title": {"type": "string", "maxLength": 300},
            },
            "additionalProperties": False,
        },
        _generate_paper_draft_tool,
        output_schema={
            "type": "object",
            "required": ["status", "title", "outputPath", "referenceCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "title": {"type": "string"},
                "sections": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "referenceCount": {"type": "integer", "minimum": 0},
                "outputPath": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["paper_writer"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )


def _read_paper_skeleton_tool(payload: dict[str, Any]) -> dict[str, Any]:
    paper_skeleton = payload.get("paperSkeleton") if isinstance(payload.get("paperSkeleton"), dict) else {}
    max_sections = _coerce_positive_int(payload.get("maxSections"), 6)
    max_chars_per_section = _coerce_positive_int(payload.get("maxCharsPerSection"), 220)

    with trace_step("tool_read_paper_skeleton", input_size=len(paper_skeleton)) as step:
        sections = []
        for key, value in paper_skeleton.items():
            text = _clean_text(value)
            if not text:
                continue
            sections.append({
                "key": str(key),
                "text": text[:max_chars_per_section],
            })
            if len(sections) >= max_sections:
                break
        rendered_text = "\n".join(f"{section['key']}: {section['text']}" for section in sections)
        step["outputSize"] = len(sections)
        return {
            "text": rendered_text,
            "sections": sections,
        }


def _judge_evidence_tool(payload: dict[str, Any]) -> dict[str, Any]:
    question = _clean_text(payload.get("question"))
    evidence_items = payload.get("evidenceItems")
    if not question:
        raise ToolValidationError("judge_evidence requires a non-empty question.")
    if not isinstance(evidence_items, list):
        raise ToolValidationError("judge_evidence requires evidenceItems to be a list.")

    with trace_step("tool_judge_evidence", input_size=len(evidence_items)) as step:
        result = judge_evidence_quality(question, evidence_items, keywords=payload.get("keywords") or [])
        step["outputSize"] = len(result.get("missingAspects") or [])
        return result


def _read_knowledge_graph_neighborhood_tool(payload: dict[str, Any]) -> dict[str, Any]:
    with trace_step("tool_read_knowledge_graph_neighborhood", input_size=len(payload)) as step:
        result = knowledge_graph_store.read_graph_neighborhood(payload)
        step["outputSize"] = len(result.get("nodes") or [])
        return result


def _generate_background_graph_tool(payload: dict[str, Any]) -> dict[str, Any]:
    with trace_step("tool_generate_background_graph", input_size=len(payload)) as step:
        response = background_knowledge_service.get_background_knowledge(BackgroundKnowledgeRequest(**payload))
        step["outputSize"] = len(response.get("background_knowledge") or [])
        return response


def _run_critical_analysis_tool(payload: dict[str, Any]) -> dict[str, Any]:
    with trace_step("tool_run_critical_analysis", input_size=len(payload)) as step:
        response = analysis_service.deep_analysis(DeepAnalysisRequest(**payload))
        step["outputSize"] = len(response.get("rag_sources") or [])
        return response


def _translate_page_tool(payload: dict[str, Any]) -> dict[str, Any]:
    with trace_step("tool_translate_page", input_size=len(str(payload.get("pageText") or ""))) as step:
        response = page_translation_service.translate_page(PageTranslationRequest(**payload))
        step["outputSize"] = len(str(response.get("translatedText") or ""))
        return response


def _generate_paper_draft_tool(payload: dict[str, Any]) -> dict[str, Any]:
    from services.paper_writer import generate_paper_draft
    question = (payload.get("question") or "").strip()
    if not question:
        raise ToolValidationError("generate_paper_draft requires a question.")
    title = (payload.get("title") or "").strip()
    findings = payload.get("findings") or []
    evidence = payload.get("evidenceItems") or []
    conflicts = payload.get("conflicts") or []
    with trace_step("tool_generate_paper_draft", input_size=len(question)) as step:
        record_counter("paperDraftCalls")
        result = generate_paper_draft(question, findings, evidence, conflicts, title=title)
        step["outputSize"] = result.get("referenceCount", 0)
        if result["status"] != "success":
            record_counter("paperDraftFailures")
        return result
