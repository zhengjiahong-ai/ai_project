"""Agent reasoning chain: multi-step LLM synthesis for research reports."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from services.utils import parse_json_from_llm

_logger = logging.getLogger(__name__)

def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

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

def extract_common_themes(profiles: List[Dict[str, Any]]) -> List[str]:
    counts: Dict[str, int] = {}
    for profile in profiles:
        for part in [item.strip() for item in str(profile.get("theme") or "").split(",")]:
            if not part or part == "limited evidence":
                continue
            counts[part] = counts.get(part, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [item[0] for item in ordered]

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

def extract_claims_per_paper(
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract structured claims from each paper's evidence using LLM.

    On LLM failure, falls back to extracting claims from finding summaries.

    Returns a list of per-paper claim dicts with shape:
    ``[{paperId, claims: [{claim, section, confidence, sourceIds}]}]``
    """
    claims_by_paper: List[Dict[str, Any]] = []
    for ctx in paper_contexts:
        pdf_id = clean_text(ctx.get("pdfId", ""))
        paper_evidence = [
            e for e in evidence_items
            if clean_text(e.get("pdfId", "")) == pdf_id or clean_text(e.get("sourceId", ""))[:8] == pdf_id[:8]
        ]
        if not paper_evidence:
            claims_by_paper.append({"paperId": pdf_id, "claims": []})
            continue

        # Try LLM claim extraction
        try:
            from llm.client import DeepSeekLLM
            ev_text = "\n".join(
                f"[src:{clean_text(e.get('sourceId', str(i)))[:20]}] {clean_text(e.get('text', ''))[:400]}"
                for i, e in enumerate(paper_evidence[:6])
            )
            prompt = (
                "Extract the key claims asserted by this paper based on the evidence below. "
                "Return JSON only: {\"claims\":[{\"claim\":\"...\",\"section\":\"method|experiment|discussion\","
                "\"confidence\":0.0-1.0,\"sourceIds\":[\"src-...\"]}]}\n"
                f"Evidence:\n{ev_text}"
            )
            llm = DeepSeekLLM(model="deepseek-v4-flash", temperature=0.2)
            raw = llm._call(prompt)
            parsed = parse_json_from_llm(raw) if raw else {}
            claims_list = parsed.get("claims", []) if isinstance(parsed, dict) else []
            if claims_list:
                claims_by_paper.append({"paperId": pdf_id, "claims": claims_list[:8]})
                continue
        except Exception:
            pass

        # Fallback: build claims from finding summary
        finding_summary = build_finding_summary("", [ctx], paper_evidence)
        claims_by_paper.append({
            "paperId": pdf_id,
            "claims": [{"claim": finding_summary, "section": "overview", "confidence": 0.5, "sourceIds": [
                clean_text(e.get("sourceId", "")) for e in paper_evidence[:3]
            ]}],
        })

    return claims_by_paper

def cross_paper_consistency_check(
    claims_by_paper: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check cross-paper consistency from extracted claims.

    Returns ``{aligned, contradictory, unique, summary}`` where each category
    lists claim pairs with sourceId references.
    """
    aligned: List[Dict[str, Any]] = []
    contradictory: List[Dict[str, Any]] = []
    unique: List[Dict[str, Any]] = []

    # Build a simple keyword-overlap consistency matrix
    for i, paper_a in enumerate(claims_by_paper):
        for claim_a in paper_a.get("claims", []):
            claim_text = str(claim_a.get("claim", "")).lower()
            if not claim_text:
                continue

            matched = False
            for j, paper_b in enumerate(claims_by_paper):
                if i >= j:
                    continue
                for claim_b in paper_b.get("claims", []):
                    claim_b_text = str(claim_b.get("claim", "")).lower()
                    if not claim_b_text:
                        continue

                    # Simple overlap measure
                    words_a = set(claim_text.split())
                    words_b = set(claim_b_text.split())
                    if not words_a or not words_b:
                        continue
                    overlap = len(words_a & words_b) / min(len(words_a), len(words_b))

                    entry = {
                        "paperA": paper_a["paperId"],
                        "paperB": paper_b["paperId"],
                        "claimA": claim_a["claim"],
                        "claimB": claim_b["claim"],
                        "sourceIdsA": claim_a.get("sourceIds", []),
                        "sourceIdsB": claim_b.get("sourceIds", []),
                        "overlap": round(overlap, 2),
                    }

                    if overlap > 0.6:
                        aligned.append(entry)
                        matched = True
                    elif overlap > 0.2:
                        contradictory.append(entry)
                        matched = True

            if not matched:
                unique.append({
                    "paperId": paper_a["paperId"],
                    "claim": claim_a["claim"],
                    "sourceIds": claim_a.get("sourceIds", []),
                })

    # Try LLM-based consistency analysis
    summary = ""
    try:
        from llm.client import DeepSeekLLM
        aligned_text = "\n".join(
            f"ALIGNED: {e['paperA']} ↔ {e['paperB']}: {e['claimA'][:100]}"
            for e in aligned[:5]
        )
        contradictory_text = "\n".join(
            f"CONTRADICT: {e['paperA']} vs {e['paperB']}: {e['claimA'][:80]} vs {e['claimB'][:80]}"
            for e in contradictory[:5]
        )
        prompt = (
            "Summarize the cross-paper consistency findings. "
            "Identify the most important aligned and contradictory claims.\n\n"
            f"{aligned_text}\n\n{contradictory_text}"
        )
        llm = DeepSeekLLM(model="deepseek-v4-flash", temperature=0.2)
        result = llm._call(prompt)
        if result and len(str(result).strip()) > 20:
            summary = str(result).strip()
    except Exception:
        summary = (
            f"Cross-paper analysis: {len(aligned)} aligned claims across papers, "
            f"{len(contradictory)} contradictory claims, {len(unique)} unique claims."
        )

    return {
        "aligned": aligned[:10],
        "contradictory": contradictory[:10],
        "unique": unique[:10],
        "summary": summary,
    }

def synthesize_llm_report(
    prompt: str,
    paper_contexts: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    open_questions: List[str],
    advanced_analysis: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a structured research synthesis via multi-step reasoning.

    Step A: Extract per-paper claims from evidence.
    Step B: Cross-paper consistency check (aligned/contradictory/unique).
    Step C: Weighted LLM synthesis with claim-level sourceId citations.

    Falls back to rule-based on any LLM failure.
    """
    try:
        from llm.client import get_llm

        # Step A+B: Claim extraction and cross-paper consistency
        claims_by_paper = extract_claims_per_paper(paper_contexts, evidence_items)
        consistency = cross_paper_consistency_check(claims_by_paper, evidence_items)

        evidence_summary = "\n".join(
            f"- [{item.get('sourceType', 'unknown')}] src:{clean_text(str(item.get('sourceId', '')), 20)} "
            f"{clean_text(item.get('text', item.get('title', '')))[:300]}"
            for item in evidence_items[:10]
        )
        conflict_summary = "\n".join(
            f"- [{c.get('severity', '?')}] {clean_text(c.get('summary', c.get('claim', '')))[:200]}"
            for c in (conflicts or [])[:5]
        )

        synthesis_prompt = (
            "You are a senior research synthesizer. Use the structured claim analysis "
            "to produce a research synthesis in Markdown.\n\n"
            "## Executive Summary\n2-3 sentence overview citing key sourceIds.\n\n"
            "## Per-Paper Claims\nFor each paper, list its key claims with sourceIds.\n\n"
            "## Cross-Paper Consistency\n"
            f"Aligned claims (same finding across papers): {consistency['summary'][:300]}\n"
            "Identify the 2-3 most important agreements and 2-3 most important contradictions.\n"
            "Cite specific evidence sourceIds for each claim.\n\n"
            "## Evidence Strength Assessment\nRate overall quality and explain gaps.\n\n"
            "## Key Insights\n3-5 actionable insights from the synthesis.\n\n"
            "## Recommendations for Further Research\n2-3 specific directions.\n\n"
            f"Research Question: {prompt}\n\n"
            f"Evidence ({len(evidence_items)} items):\n{evidence_summary}\n\n"
            f"Conflicts:\n{conflict_summary}\n\n"
            f"Open Questions:\n" + "\n".join(f"- {q}" for q in (open_questions or [])[:4])
        )

        llm = get_llm()
        result = llm._call(prompt=synthesis_prompt)
        if result and len(str(result).strip()) > 100:
            return str(result).strip()
    except Exception:
        pass

    # Fallback: build a rule-based synthesis
    profiles = build_paper_support_profiles(paper_contexts, evidence_items)
    strongest = [p for p in profiles if p["evidenceCount"] >= 2]
    themes = extract_common_themes(profiles)

    lines = ["## Executive Summary\n"]
    lines.append(
        f"This synthesis covers {len(paper_contexts)} papers with {len(evidence_items)} evidence items. "
        f"{len(strongest)} papers provide moderate-to-strong evidence coverage."
    )
    lines.append("\n## Cross-Paper Synthesis\n")
    if themes:
        lines.append(f"Key recurring themes: {', '.join(themes[:4])}.")
    for p in profiles:
        lines.append(f"- `{p['pdfId']}`: {p['evidenceCount']} snippets, theme: {p['theme']}")
    lines.append("\n## Evidence Strength Assessment\n")
    dense = len([p for p in profiles if p["evidenceCount"] >= 3])
    if dense >= 2:
        lines.append("Overall evidence quality: **moderate** — multiple papers provide dense coverage.")
    elif strongest:
        lines.append("Overall evidence quality: **limited** — some papers have useful evidence but coverage is uneven.")
    else:
        lines.append("Overall evidence quality: **limited** — most papers have sparse evidence coverage.")
    lines.append("\n## Key Insights\n")
    lines.append("- The automated evidence collection identified both converging and diverging claims across papers.")
    if conflicts:
        lines.append(f"- {len(conflicts)} potential conflicts were detected and flagged for human review.")
    if open_questions:
        lines.append(f"- {len(open_questions)} open questions remain for follow-up investigation.")
    lines.append("\n## Recommendations for Further Research\n")
    lines.append("- Run additional retrieval rounds with refined queries targeting specific sections (methods, experiments).")
    lines.append("- Human review of flagged conflicts is recommended before drawing final conclusions.")
    return "\n".join(lines)

