"""
Report builder utilities for Agent project service.

Extracted from agent_project_service.py to keep each module ≤800 lines.
These functions format findings, evidence previews, scope lines, conclusion
lines, conflict lines, and detect conflicts from paper contexts and evidence.
"""

import copy
import re
from typing import Any, Dict, List


def _build_minimal_report(
    prompt: str,
    project: Dict[str, Any],
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    open_questions: List[str],
) -> str:
    paper_lines = "\n".join(_build_scope_lines(paper_contexts)) or "- No project papers selected"
    evidence_lines = "\n".join(_build_evidence_snapshot_lines(evidence_items)) or "- No evidence snippets yet"
    conclusion_lines = "\n".join(_build_conclusion_lines(prompt, paper_contexts, evidence_items))
    question_lines = "\n".join(f"- {item}" for item in open_questions[:4]) or "- None"
    conflict_lines = "\n".join(_build_conflict_lines(conflicts)) or "- No strong conflict candidates detected in this pass"
    return (
        "# Agent Research Draft\n\n"
        f"## Task\n{prompt}\n\n"
        f"## Project\n{project.get('title')}\n\n"
        f"## Scope\n{paper_lines}\n\n"
        "## Evidence Snapshot\n"
        f"{evidence_lines}\n\n"
        "## Current Conclusion\n"
        f"{conclusion_lines}\n\n"
        "## Conflict Candidates\n"
        f"{conflict_lines}\n\n"
        "## Open Questions\n"
        f"{question_lines}\n"
    )


def _build_finding_summary(prompt: str, paper_contexts: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> str:

    paper_count = len(paper_contexts)
    evidence_count = len(evidence_items)
    support_profiles = _build_paper_support_profiles(paper_contexts, evidence_items)
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


def _evidence_preview(evidence_items: List[Dict[str, Any]]) -> str:
    from services.agent_reasoning import clean_text

    snippets = []
    for item in evidence_items[:2]:
        text = clean_text(item.get("text"))
        if text:
            snippets.append(text[:80])
    return " | ".join(snippets)


def _stabilize_source_ids(items: List[Dict[str, Any]], fallback_prefix: str) -> List[Dict[str, Any]]:
    from services.agent_reasoning import clean_text

    stabilized = []
    for index, item in enumerate(items):
        current = copy.deepcopy(item)
        source_id = clean_text(current.get("sourceId"))
        if not source_id:
            source_id = f"{fallback_prefix}-source-{index + 1}"
        current["sourceId"] = source_id[:80]
        stabilized.append(current)
    return stabilized


def _build_paper_judgement(paper_context: Dict[str, Any]) -> str:
    from services.agent_reasoning import clean_text

    evidence_count = int(paper_context.get("evidenceCount") or 0)
    status = clean_text(paper_context.get("status")) or "unknown"
    if evidence_count >= 3 and status == "succeeded":
        return "Evidence is dense enough for cross-paper judgement."
    if evidence_count >= 1:
        return "Evidence is usable, but section coverage is still uneven."
    return "Evidence is too sparse for a confident judgement."


def _build_scope_lines(paper_contexts: List[Dict[str, Any]]) -> List[str]:
    from services.agent_reasoning import clean_text

    lines = []
    for item in paper_contexts:
        pdf_id = clean_text(item.get("pdfId")) or "unknown-paper"
        evidence_count = int(item.get("evidenceCount") or 0)
        preview = clean_text(item.get("preview"))[:120]
        preview_suffix = f" Preview: {preview}" if preview else ""
        lines.append(f"- `{pdf_id}`: {evidence_count} evidence snippets.{preview_suffix}")
    return lines


def _build_evidence_snapshot_lines(evidence_items: List[Dict[str, Any]]) -> List[str]:
    from services.agent_reasoning import clean_text

    lines = []
    for item in evidence_items[:6]:
        pdf_id = clean_text(item.get("pdfId")) or "unknown-paper"
        section_id = clean_text(item.get("sectionId")) or "unknown-section"
        text = clean_text(item.get("text"))[:160]
        lines.append(f"- `{pdf_id}` / `{section_id}`: {text}")
    return lines


def _build_paper_support_profiles(
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    from services.agent_reasoning import clean_text

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
                "theme": _infer_theme_from_evidence(evidence_for_paper),
                "status": clean_text(paper_context.get("status")) or "unknown",
            }
        )
    return sorted(profiles, key=lambda item: item["evidenceCount"], reverse=True)


def _build_conclusion_lines(
    prompt: str,
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[str]:
    if not paper_contexts:
        return ["- No project papers are attached yet, so a project-level conclusion cannot be formed."]

    profiles = _build_paper_support_profiles(paper_contexts, evidence_items)
    strongest = [item for item in profiles if item["evidenceCount"] >= 2]
    sparse = [item for item in profiles if item["evidenceCount"] <= 1]
    fallback = [item for item in profiles if item["status"] == "fallback"]
    common_themes = _extract_common_themes(profiles)

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


def _build_conflict_lines(conflicts: List[Dict[str, Any]]) -> List[str]:
    from services.agent_reasoning import clean_text

    lines = []
    for item in conflicts[:4]:
        severity = clean_text(item.get("severity")) or "unknown"
        summary = clean_text(item.get("summary"))
        claim = clean_text(item.get("claim"))
        papers = [paper for paper in item.get("papers") or [] if clean_text(paper)]
        paper_text = f" Papers: {', '.join(papers[:4])}." if papers else ""
        claim_text = f" Claim: {claim}." if claim else ""
        lines.append(f"- [{severity}] {summary}{claim_text}{paper_text}")
    return lines


def _infer_theme_from_evidence(evidence_items: List[Dict[str, Any]]) -> str:
    from services.agent_reasoning import clean_text

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
    keywords = _extract_keywords(joined)
    if keywords:
        return ", ".join(keywords[:2])
    return "paper-level evidence"


def _extract_common_themes(profiles: List[Dict[str, Any]]) -> List[str]:
    counts: Dict[str, int] = {}
    for profile in profiles:
        for part in [item.strip() for item in str(profile.get("theme") or "").split(",")]:
            if not part or part == "limited evidence":
                continue
            counts[part] = counts.get(part, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [item[0] for item in ordered]


def _extract_keywords(text: str) -> List[str]:
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


def _detect_conflicts(paper_contexts: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
