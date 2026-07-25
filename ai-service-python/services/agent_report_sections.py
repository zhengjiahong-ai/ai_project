"""
Report section formatters for the Agent orchestrator.

Extracted from agent_orchestrator.py to keep each module ≤800 lines.
Builds formatted report sections (scope, evidence snapshots, external evidence,
code execution, cross-validation, source provenance, conflicts).
"""

import copy
from typing import Any

from services.agent_reasoning import build_conclusion_lines, clean_text
from services.external_evidence import EXTERNAL_SOURCE_TYPE


def build_minimal_report(
    prompt: str,
    project: dict[str, Any],
    paper_contexts: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    open_questions: list[str],
    code_execution_results: list[dict[str, Any]] | None = None,
    execute_python_results: list[dict[str, Any]] | None = None,
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

    py_section = ""
    if execute_python_results:
        py_lines = _build_python_execution_section_lines(execute_python_results)
        if py_lines:
            py_section = (
                "## Python Code Execution\n"
                f"{py_lines}\n\n"
            )

    cross_validation_lines = _build_cross_validation_lines(conflicts)
    provenance_lines = _build_agent_provenance_lines(evidence_items)

    return (
        "# Agent Research Draft\n\n"
        f"## Task\n{prompt}\n\n"
        f"## Project\n{project.get('title')}\n\n"
        f"## Scope\n{paper_lines}\n\n"
        "## Evidence Snapshot\n"
        f"{evidence_lines}\n\n"
        f"{external_section}"
        f"{code_section}"
        f"{py_section}"
        "## Current Conclusion\n"
        f"{conclusion_lines}\n\n"
        "## Conflict Candidates\n"
        f"{conflict_lines}\n\n"
        f"{cross_validation_lines}"
        f"{provenance_lines}"
        "## Open Questions\n"
        f"{question_lines}\n"
    )


def evidence_preview(evidence_items: list[dict[str, Any]]) -> str:
    snippets = []
    for item in evidence_items[:2]:
        text = clean_text(item.get("text"))
        if text:
            snippets.append(text[:80])
    return " | ".join(snippets)


def stabilize_source_ids(items: list[dict[str, Any]], fallback_prefix: str) -> list[dict[str, Any]]:
    stabilized = []
    for index, item in enumerate(items):
        current = copy.deepcopy(item)
        source_id = clean_text(current.get("sourceId"))
        if not source_id:
            source_id = f"{fallback_prefix}-source-{index + 1}"
        current["sourceId"] = source_id[:80]
        stabilized.append(current)
    return stabilized


def build_paper_judgement(paper_context: dict[str, Any]) -> str:
    evidence_count = int(paper_context.get("evidenceCount") or 0)
    status = clean_text(paper_context.get("status")) or "unknown"
    if evidence_count >= 3 and status == "succeeded":
        return "Evidence is dense enough for cross-paper judgement."
    if evidence_count >= 1:
        return "Evidence is usable, but section coverage is still uneven."
    return "Evidence is too sparse for a confident judgement."


def build_scope_lines(paper_contexts: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in paper_contexts:
        pdf_id = clean_text(item.get("pdfId")) or "unknown-paper"
        evidence_count = int(item.get("evidenceCount") or 0)
        preview = clean_text(item.get("preview"))[:120]
        preview_suffix = f" Preview: {preview}" if preview else ""
        lines.append(f"- `{pdf_id}`: {evidence_count} evidence snippets.{preview_suffix}")
    return lines


def build_evidence_snapshot_lines(evidence_items: list[dict[str, Any]]) -> list[str]:
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


def _build_external_evidence_section_lines(evidence_items: list[dict[str, Any]]) -> str:
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


def _build_code_execution_section_lines(results: list[dict[str, Any]]) -> str:
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


def _build_python_execution_section_lines(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    lines = []
    for i, result in enumerate(results):
        status = result.get("status", "unknown")
        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        error = (result.get("error") or "").strip()
        lines.append(f"\n**Execution {i + 1}** ({status}):")
        if stdout:
            lines.append("```\n" + stdout[:2000] + "\n```")
        if stderr:
            lines.append("Stderr:\n```\n" + stderr[:1000] + "\n```")
        if error:
            lines.append(f"Error: {error}")
    return "\n".join(lines)


def _build_cross_validation_lines(conflicts: list[dict[str, Any]]) -> str:
    """Build cross-validation report section from conflicts list."""
    cv_conflicts = [c for c in (conflicts or []) if c.get("conflictType") == "cross-validation"]
    if not cv_conflicts:
        return ""
    cv = cv_conflicts[0].get("crossValidation") or {}
    claims = cv.get("claims") or []
    summary = cv.get("summary") or {}
    if not claims:
        return ""

    lines = ["## Cross-Source Validation\n"]
    lines.append(f"Validated {summary.get('total_claims', 0)} claims across sources: "
                 f"{summary.get('confirmed', 0)} confirmed, "
                 f"{summary.get('supported', 0)} supported, "
                 f"{summary.get('single_source', 0)} single-source, "
                 f"{summary.get('contradicted', 0)} contradicted.\n")

    for claim in claims:
        level = claim.get("agreement_level", "unknown")
        label = {"confirmed": "✓", "supported": "~", "single_source": "?", "contradicted": "✗"}.get(level, "?")
        sources_str = ", ".join(claim.get("source_types", []))
        lines.append(f"- {label} [{level}] {claim.get('claim', '')[:200]} (sources: {sources_str})")
        if claim.get("needs_more_evidence"):
            lines.append("  ⚠ 需更多证据 — 仅单一来源支持")
        if claim.get("needs_manual_review"):
            lines.append("  ⚠ 需人工核查 — 存在矛盾声明")

    lines.append("")
    return "\n".join(lines)


def _build_agent_provenance_lines(evidence_items: list[dict[str, Any]]) -> str:
    """Build source provenance section from external evidence items."""
    provenance_items = []
    for item in (evidence_items or []):
        provenance = item.get("provenance") if isinstance(item, dict) else None
        if not isinstance(provenance, dict):
            continue
        provenance_items.append({
            "sourceId": item.get("sourceId", ""),
            "provider": item.get("provider", ""),
            "discoveryPath": provenance.get("discoveryPath", ""),
            "searchQuery": provenance.get("searchQuery", ""),
            "searchIteration": provenance.get("searchIteration"),
            "sourceUrl": provenance.get("sourceUrl", ""),
            "retrievalTimestamp": provenance.get("retrievalTimestamp", ""),
        })

    if not provenance_items:
        return ""

    seen = set()
    lines = ["## Source Provenance", ""]
    for item in provenance_items:
        key = (item["sourceId"], item["sourceUrl"])
        if key in seen:
            continue
        seen.add(key)
        parts = [f"[{item['discoveryPath'] or 'unknown'}]"]
        if item["provider"]:
            parts.append(item["provider"])
        if item["searchQuery"]:
            parts.append(f'query: "{item["searchQuery"]}"')
        if isinstance(item["searchIteration"], int):
            parts.append(f"round {item['searchIteration']}")
        if item["sourceUrl"]:
            parts.append(item["sourceUrl"][:120])
        if item["retrievalTimestamp"]:
            parts.append(item["retrievalTimestamp"])
        lines.append(f"- {' → '.join(parts)}")
    lines.append("")
    return "\n".join(lines)


def build_conflict_lines(conflicts: list[dict[str, Any]]) -> list[str]:
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


def detect_conflicts(paper_contexts: list[dict[str, Any]], evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(paper_contexts) < 2:
        return []

    conflicts: list[dict[str, Any]] = []
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
