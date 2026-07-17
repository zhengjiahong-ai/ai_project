"""Automated academic paper drafting — generates structured paper drafts from
research findings in Markdown and LaTeX formats.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTPUT_DIR = os.environ.get(
    "PAPER_DRAFT_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "paper_drafts"),
)


# ── Public API ───────────────────────────────────────────────────────────────

def generate_paper_draft(
    question: str,
    findings: list[dict[str, Any]] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    meta_analysis: dict[str, Any] | None = None,
    adversarial_review: dict[str, Any] | None = None,
    title: str = "",
    section: str = "",
    existing_sections: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate a structured academic paper draft.

    If ``section`` is provided, only that section is regenerated; all other
    sections are preserved from ``existing_sections``.

    Returns ``{status, title, sections, references, markdown, latex, bibtex, sty, error}``.
    """
    if not question or not question.strip():
        return _error("Research question cannot be empty.")

    findings = findings or []
    evidence = evidence_items or []
    conflicts = conflicts or []
    meta = meta_analysis or {}
    adv = adversarial_review or {}

    title = title.strip() if title and title.strip() else f"A Systematic Review of {question[:80]}"

    if section and existing_sections:
        # Per-section regeneration: rebuild only the requested section
        existing = dict(existing_sections)
        rebuilt = _build_sections(question, title, findings, evidence, conflicts, meta, adv)
        if section in rebuilt:
            existing[section] = rebuilt[section]
        sections = existing
    else:
        sections = _build_sections(question, title, findings, evidence, conflicts, meta, adv)
    references = _build_references(evidence)
    markdown = _render_markdown(title, sections, references)
    bibtex = _render_bibtex(references)
    sty = _render_sty()
    latex = _render_latex(title, sections, references)

    # Write to disk
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(OUTPUT_DIR) / timestamp
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "paper.md").write_text(markdown, encoding="utf-8")
    (out_path / "paper.tex").write_text(latex, encoding="utf-8")
    (out_path / "references.bib").write_text(bibtex, encoding="utf-8")
    (out_path / "pixiu-paper.sty").write_text(sty, encoding="utf-8")

    return {
        "status": "success",
        "title": title,
        "sections": [{"heading": s["heading"], "wordCount": len(s["body"].split()), "body": s["body"]} for s in sections],
        "referenceCount": len(references),
        "bibtex": bibtex,
        "sty": sty,
        "outputPath": str(out_path),
        "markdown": markdown,
        "latex": latex,
        "error": "",
    }


# ── Section builders ─────────────────────────────────────────────────────────

def _build_sections(
    question: str, title: str, findings: list[dict[str, Any]],
    evidence: list[dict[str, Any]], conflicts: list[dict[str, Any]],
    meta: dict[str, Any], adv: dict[str, Any],
) -> list[dict[str, Any]]:
    sections = []

    # Abstract
    sections.append({"heading": "Abstract", "body": _llm_abstract(question, findings, conflicts)})

    # Introduction
    intro = (
        f"This paper presents a systematic investigation of the research question: "
        f"*{question}*. Through automated multi-source literature search, "
        f"evidence synthesis, and cross-validation across {len(evidence)} evidence "
        f"items from {len(findings)} sub-questions, we provide a structured analysis "
        f"of the current state of knowledge."
    )
    sections.append({"heading": "Introduction", "body": intro})

    # Related Work (from citation graph)
    related = _build_related_work(evidence)
    if related:
        sections.append({"heading": "Related Work", "body": related})

    # Methodology
    method = (
        f"The research was conducted using the Pixiu Automated Research system. "
        f"The primary question was decomposed into {len(findings)} sub-questions, "
        f"each investigated through multi-source search (academic databases, web search, "
        f"citation graph traversal). Evidence was judged for sufficiency (CORRECT/AMBIGUOUS/INCORRECT) "
        f"and scored on coverage, source diversity, and trust weighting. "
        f"Conflicts were adjudicated through rule-based scoring and LLM analysis."
    )
    sections.append({"heading": "Methodology", "body": method})

    # Results
    results_lines = []
    for i, f in enumerate(findings, 1):
        results_lines.append(f"**Sub-question {i}**: {f.get('subQuestion', '')}")
        results_lines.append(f"Finding: {f.get('summary', 'No conclusion.')} [{f.get('verdict', '?')}]")
        judge = f.get("judgeScore")
        if judge is not None:
            results_lines.append(f"Confidence: {judge}/100")
        results_lines.append("")
    if meta.get("summary"):
        ms = meta["summary"]
        results_lines.append(f"**Meta-analysis**: pooled effect size {ms.get('effectSize','?')} "
                            f"(95% CI: [{ms.get('ciLower','?')}, {ms.get('ciUpper','?')}]).")
    sections.append({"heading": "Results", "body": "\n".join(results_lines)})

    # Discussion (conflicts + adversarial review)
    disc_lines = []
    if conflicts:
        disc_lines.append("### Conflicts Identified")
        for c in conflicts[:5]:
            disc_lines.append(f"- **{c.get('claim', c.get('topic', ''))}**: {c.get('summary', '')[:200]}")
    if adv.get("reviewedFindings"):
        disc_lines.append("### Critical Self-Assessment")
        for rf in adv.get("reviewedFindings", [])[:5]:
            disc_lines.append(f"- {rf.get('subQuestion','')[:100]}: confidence adjusted "
                            f"{rf.get('originalConfidence',0):.2f}→{rf.get('adjustedConfidence',0):.2f}")
    sections.append({"heading": "Discussion", "body": "\n".join(disc_lines) if disc_lines else "See Results section."})

    # Conclusion
    conclusion = _llm_conclusion(question, findings)
    sections.append({"heading": "Conclusion", "body": conclusion})

    return sections


def _build_related_work(evidence: list[dict[str, Any]]) -> str:
    lines = []
    seen = set()
    for e in evidence:
        title = (e.get("title") or "").strip()
        if title and title not in seen:
            seen.add(title)
            year = e.get("year", "")
            authors = ", ".join((e.get("authors") or [])[:3])
            lines.append(f"- {authors} ({year}). *{title[:150]}*.")
            if len(lines) >= 8:
                break
    return "\n".join(lines) if lines else ""


def _build_references(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for i, e in enumerate(evidence, 1):
        title = (e.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        refs.append({
            "id": f"ref-{i}",
            "authors": (e.get("authors") or [])[:8],
            "title": title[:300],
            "year": e.get("year"),
            "venue": e.get("venue") or e.get("journal", ""),
            "doi": e.get("doi", ""),
            "url": e.get("url", ""),
        })
    return refs


# ── LLM helpers ──────────────────────────────────────────────────────────────

def _llm_abstract(question: str, findings: list[dict[str, Any]], conflicts: list[dict[str, Any]]) -> str:
    try:
        from concurrent.futures import ThreadPoolExecutor
        from llm.client import get_llm

        f_str = "; ".join(f.get("summary", "")[:100] for f in findings[:5])
        c_str = "; ".join(c.get("claim", "")[:100] for c in (conflicts or [])[:3])
        prompt = (
            f"Write a 200-300 word academic abstract for a systematic review on: {question}\n"
            f"Key findings: {f_str}\n"
            f"Disagreements: {c_str}\n\n"
            "Structure: Background, Methods, Results, Conclusions. Academic tone."
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            return (future.result(timeout=20) or f"A systematic review of {question}.")[:1500]
    except Exception:
        return f"This paper systematically examines the question: {question}. "

def _llm_conclusion(question: str, findings: list[dict[str, Any]]) -> str:
    try:
        from concurrent.futures import ThreadPoolExecutor
        from llm.client import get_llm

        f_str = "; ".join(f.get("summary", "")[:120] for f in findings[:5])
        prompt = (
            f"Write a concise conclusion paragraph (~150 words) for a review on: {question}\n"
            f"Main findings: {f_str}\n\n"
            "Include: summary of evidence, limitations, future directions. Academic tone."
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            return (future.result(timeout=20) or f"Further research is needed on {question}.")[:1000]
    except Exception:
        return f"The evidence regarding {question} suggests further investigation is warranted."


# ── Renderers ────────────────────────────────────────────────────────────────

def _render_markdown(title: str, sections: list[dict[str, Any]], references: list[dict[str, Any]]) -> str:
    lines = [f"# {title}", "", "*Auto-generated by Pixiu Automated Research*", ""]
    for s in sections:
        lines.append(f"## {s['heading']}")
        lines.append(s["body"])
        lines.append("")
    lines.append("## References")
    for r in references:
        authors = ", ".join(r["authors"][:3])
        year = r.get("year", "n.d.")
        lines.append(f"- [{r['id']}] {authors} ({year}). *{r['title'][:200]}*. {r.get('venue','')}.")
    return "\n".join(lines)


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = [
        ("\\", r"\textbackslash "),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde "),
        ("^", r"\^{}"),
    ]
    result = str(text or "")
    for char, repl in replacements:
        result = result.replace(char, repl)
    return result


def _render_sty() -> str:
    """Generate a minimal Overleaf-compatible .sty file."""
    return (
        "% Pixiu Paper Draft Style File\n"
        "% Generated for Overleaf compatibility\n"
        "\\ProvidesPackage{pixiu-paper}\n\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage{hyperref}\n"
        "\\usepackage{amsmath,amssymb}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage[backend=bibtex]{biblatex}\n"
        "\\usepackage{geometry}\n"
        "\\geometry{a4paper, margin=1in}\n\n"
        "\\newcommand{\\pixiuNote}[1]{\\marginpar{\\footnotesize\\textsf{#1}}}\n"
    )


def _render_latex(title: str, sections: list[dict[str, Any]], references: list[dict[str, Any]]) -> str:
    lines = [
        r"\documentclass{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{hyperref}",
        r"\title{" + _escape_latex(title) + "}",
        r"\date{\today}",
        r"\begin{document}",
        r"\maketitle",
    ]
    for s in sections:
        cmd = "section*" if s["heading"] == "Abstract" else "section"
        heading = _escape_latex(s["heading"])
        body = _escape_latex(s.get("body", ""))
        lines.append(rf"\{cmd}{{{heading}}}")
        lines.append(body)
        lines.append("")
    lines.append(r"\begin{thebibliography}{99}")
    for r in references:
        authors = _escape_latex(", ".join(r.get("authors", [])[:3]) or "Unknown")
        title = _escape_latex(str(r.get("title", ""))[:200])
        year = str(r.get("year", "n.d."))
        lines.append(rf"\bibitem{{{r['id']}}} {authors} ({year}). \textit{{{title}}}.")
    lines.append(r"\end{thebibliography}")
    lines.append(r"\end{document}")
    return "\n".join(lines)


def _infer_bibtex_type(ref: dict[str, Any]) -> str:
    """Infer BibTeX entry type from reference metadata."""
    venue = str(ref.get("venue", "")).lower()
    if any(w in venue for w in ("conference", "proceedings", "workshop", "symposium")):
        return "inproceedings"
    if any(w in venue for w in ("arxiv", "preprint")):
        return "techreport"
    if any(w in venue for w in ("book", "monograph")):
        return "book"
    return "article"


def _render_bibtex(references: list[dict[str, Any]]) -> str:
    entries = []
    for r in references:
        authors = " and ".join(str(a) for a in r.get("authors", [])[:5])
        entry_type = _infer_bibtex_type(r)
        year = str(r.get("year", "")).strip()
        if not year:
            year = "n.d."
        entries.append(
            f"@{entry_type}{{{r['id']},\n"
            f"  author = {{{authors}}},\n"
            f"  title = {{{str(r.get('title', ''))[:300]}}},\n"
            f"  year = {{{year}}},\n"
            f"  journal = {{{r.get('venue', '')}}},\n"
            f"  doi = {{{r.get('doi', '')}}}\n}}"
        )
    return "\n\n".join(entries)


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "title": "", "sections": [], "referenceCount": 0,
            "outputPath": "", "markdown": "", "latex": "", "error": message}
