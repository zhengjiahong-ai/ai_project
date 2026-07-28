from __future__ import annotations

import re

from core.pdf_outline_parser import (
    _CHAPTER_RE,
    _COMMON_CHINESE_UNNUMBERED_HEADING_RE,
    _COMMON_UNNUMBERED_HEADING_RE,
    OutlineCandidate,
    PdfTextLine,
    _build_display_title,
    _candidate_sort_key,
    _classify_paragraph_heading,
    _clean_heading_title,
    _clean_inline_text,
    _estimate_body_font_by_page,
    _extract_pdf_text_lines,
    _looks_like_noise_line,
    _repair_pdf_heading_title,
    _stable_source_key,
    _strip_page_from_box,
)

try:
    from PyPDF2 import PdfReader as _PdfReader
except Exception:  # pragma: no cover
    _PdfReader = None


def _build_standalone_pdf_outline(pdf_path: str) -> list[OutlineCandidate]:
    """Build a complete outline from PDF alone when GROBID TEI has no headings (16-1).

    This path is critical for Chinese PDFs, where GROBID typically produces
    body text paragraphs but zero ``<div><head>`` elements.

    Strategy:
    1. Extract all PDF text lines.
    2. Rank lines by heading-likelihood (font size above body median + bold).
    3. Group candidates by page → sort by position → infer hierarchy.
    4. Apply CJK-specific heading patterns.
    """
    if _PdfReader is None:
        return []

    try:
        lines = _extract_pdf_text_lines(pdf_path)
    except Exception:
        return []

    if not lines:
        return []

    body_font_by_page = _estimate_body_font_by_page(lines)
    candidates: list[OutlineCandidate] = []

    for index, line in enumerate(lines):
        text = _clean_inline_text(line.text)
        if not text or len(text) > 200:
            continue
        if _looks_like_noise_line(text):
            continue

        body_font = body_font_by_page.get(line.page_index)
        heading_score = _rate_pdf_heading_likelihood(line, body_font, text)

        has_cjk = bool(re.search(r"[一-鿿]", text))
        min_score = 0.55 if has_cjk else 0.68
        if heading_score < min_score:
            continue

        heading_number, raw_title, _ = _classify_paragraph_heading(text)
        if not raw_title:
            raw_title = _repair_pdf_heading_title(text)
            heading_number = ""

        if heading_score >= 0.9:
            level = 1
        elif heading_score >= 0.78:
            level = 2
        elif heading_score >= 0.65:
            level = 3
        else:
            level = 4

        bbox = {
            "pageIndex": line.page_index,
            "x": line.x,
            "y": line.y,
            "width": line.width,
            "height": line.height,
        }
        candidates.append(
            OutlineCandidate(
                raw_title=raw_title,
                display_title=_build_display_title(raw_title, heading_number),
                heading_number=heading_number,
                level=level,
                source="pdf-layout",
                confidence=round(heading_score, 2),
                page_index=line.page_index,
                page=line.page_index + 1,
                bbox=_strip_page_from_box(bbox),
                anchor_y=line.y,
                preview="",
                source_key=_stable_source_key("pdf-standalone", text, bbox, index),
                source_parent_key=None,
                order=index,
                source_details=["pdf-standalone-heading"],
            )
        )

    return sorted(candidates, key=_candidate_sort_key)


def _rate_pdf_heading_likelihood(
    line: PdfTextLine,
    body_font: float | None,
    text: str,
) -> float:
    """Score a PDF text line 0–1 on how likely it is a section heading (16-1)."""
    score = 0.35

    if body_font and line.font_size >= body_font + 2.5:
        score += 0.22
    elif body_font and line.font_size >= body_font + 1.5:
        score += 0.14
    elif body_font and line.font_size >= body_font + 0.5:
        score += 0.06

    if line.bold_ratio >= 0.7:
        score += 0.12
    elif line.bold_ratio >= 0.4:
        score += 0.06

    words = text.split()
    if len(words) <= 8:
        score += 0.08
    elif len(words) <= 14:
        score += 0.04

    if re.match(r"^\s*\d+(?:\.\d+)*\s", text):
        score += 0.10
    if _CHAPTER_RE.match(text):
        score += 0.08

    if _COMMON_UNNUMBERED_HEADING_RE.match(_clean_heading_title(text)):
        score += 0.10
    if _COMMON_CHINESE_UNNUMBERED_HEADING_RE.match(_clean_heading_title(text)):
        score += 0.12

    cjk_chars = len(re.findall(r"[一-鿿]", text))
    if cjk_chars >= 2 and cjk_chars <= 20:
        score += 0.06

    if re.search(r"\b(the|this|these|we propose|in this|our method)\b", text, re.IGNORECASE):
        score -= 0.20
    if text.endswith((".", "。", ";", "；")):
        score -= 0.10

    return max(0.0, min(1.0, score))
