from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

from core.document_parser import _collect_element_coords, _union_boxes
from core.pdf_outline_parser import (
    OutlineCandidate,
    PdfTextFragment,
    PdfTextLine,
    _build_display_title,
    _build_pdf_heading_candidates,
    _candidate_sort_key,
    _chinese_digit_to_arabic,
    _clean_inline_text,
    _extract_pdf_text_lines,
    _extract_standalone_heading_number,
    _infer_level,
    _normalize_heading_number,
    _normalize_merge_text,
    _should_skip_heading_candidate,
    _split_heading_number,
    _stable_source_key,
    _strip_page_from_box,
)
from core.pdfjs_fallback import _build_standalone_pdf_outline

_logger = logging.getLogger(__name__)

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover - import availability depends on runtime image
    PdfReader = None

OUTLINE_VERSION = "1.4"

# ── Re-exports for backward compatibility ─────────────────────────────────────
# These symbols were previously defined in this file and are imported by tests
# and other modules.  Re-exporting keeps existing import paths working.
__all__ = [
    "OUTLINE_VERSION",
    "OutlineCandidate",
    "PdfTextFragment",
    "PdfTextLine",
    "_build_pdf_heading_candidates",
    "_chinese_digit_to_arabic",
    "_extract_standalone_heading_number",
    "build_document_outline",
]


def build_document_outline(tei_path: str, pdf_path: str | None = None) -> list[dict]:
    """Build a richer paper outline from TEI heads plus conservative layout hints.

    The first source is GROBID's TEI structure. The second source catches short
    paragraph-level headings that GROBID often leaves inside a parent section.
    The optional PDF source reads line-level coordinates so same-page subheads
    can still be recovered when GROBID merges them into nearby body text.

    When GROBID produces no TEI headings at all (common for Chinese PDFs), a
    standalone PDF-based outline is built from font-size and boldness heuristics
    (16-1 enhancement).
    """
    with open(tei_path, "r", encoding="utf-8") as handle:
        soup = BeautifulSoup(handle, "xml")

    candidates = _extract_tei_head_candidates(soup)

    # 16-1: If GROBID found zero TEI headings, try the PDF-only CJK-enhanced path.
    if not candidates and pdf_path:
        pdf_candidates = _build_standalone_pdf_outline(pdf_path)
        if pdf_candidates:
            return _finalize_outline(_insert_missing_numbered_parents(pdf_candidates))

    candidates.extend(_extract_paragraph_heading_candidates(soup, len(candidates)))
    if pdf_path:
        candidates.extend(_extract_pdf_heading_candidates(pdf_path, len(candidates)))
    merged_candidates = _merge_candidates(candidates)
    merged_candidates = _insert_missing_numbered_parents(merged_candidates)
    return _finalize_outline(merged_candidates)


# ── TEI extraction ────────────────────────────────────────────────────────────


def _extract_tei_head_candidates(soup: BeautifulSoup) -> list[OutlineCandidate]:
    body = soup.find("body") or soup
    body_divs = body.find_all("div")
    div_keys = {id(div): f"tei-div-{index + 1}" for index, div in enumerate(body_divs)}
    candidates: list[OutlineCandidate] = []

    for index, div in enumerate(body_divs):
        head = div.find("head", recursive=False)
        if not head:
            continue

        title_text = _clean_inline_text(head.get_text(" ", strip=True))
        if not title_text or title_text.lower() == "unknown":
            continue

        heading_number, raw_title = _split_heading_number(
            title_text,
            explicit_number=_normalize_heading_number(head.get("n")),
        )
        if _should_skip_heading_candidate(raw_title, heading_number):
            continue

        display_title = _build_display_title(raw_title, heading_number)
        ancestor_divs = [parent for parent in div.find_parents("div") if id(parent) in div_keys]
        nested_level = len(ancestor_divs) + 1
        level = _infer_level(heading_number, nested_level)
        parent_div = ancestor_divs[0] if ancestor_divs else None
        coords = _collect_element_coords(head) or _collect_element_coords(div)
        bbox = _first_page_box(coords)
        page_index = bbox.get("pageIndex") if bbox else None
        preview = _build_preview(div, title_text)

        candidates.append(
            OutlineCandidate(
                raw_title=raw_title,
                display_title=display_title,
                heading_number=heading_number,
                level=level,
                source="tei",
                confidence=0.95 if heading_number else 0.86,
                page_index=page_index,
                page=page_index + 1 if page_index is not None else None,
                bbox=_strip_page_from_box(bbox),
                anchor_y=bbox.get("y") if bbox else None,
                preview=preview,
                source_key=div_keys[id(div)],
                source_parent_key=div_keys.get(id(parent_div)) if parent_div else None,
                order=index,
                source_details=["tei-head"],
            )
        )

    return candidates


def _extract_paragraph_heading_candidates(soup: BeautifulSoup, order_offset: int) -> list[OutlineCandidate]:
    from core.pdf_outline_parser import (
        _classify_paragraph_heading,
    )  # local import avoids shadowing

    body = soup.find("body") or soup
    body_divs = body.find_all("div")
    div_keys = {id(div): f"tei-div-{index + 1}" for index, div in enumerate(body_divs)}
    candidates: list[OutlineCandidate] = []

    for index, paragraph in enumerate(body.find_all("p")):
        text = _clean_inline_text(paragraph.get_text(" ", strip=True))
        if not text:
            continue

        heading_number, raw_title, confidence = _classify_paragraph_heading(text)
        if not raw_title:
            continue
        if _should_skip_heading_candidate(raw_title, heading_number):
            continue

        coords = _collect_element_coords(paragraph)
        bbox = _first_page_box(coords)
        parent_div = paragraph.find_parent("div")
        parent_key = div_keys.get(id(parent_div)) if parent_div else None
        source_key = _stable_source_key("layout", text, bbox, index)
        display_title = _build_display_title(raw_title, heading_number)
        level = _infer_level(heading_number, 2 if parent_key else 1)

        candidates.append(
            OutlineCandidate(
                raw_title=raw_title,
                display_title=display_title,
                heading_number=heading_number,
                level=level,
                source="layout",
                confidence=confidence,
                page_index=bbox.get("pageIndex") if bbox else None,
                page=bbox.get("pageIndex") + 1 if bbox and bbox.get("pageIndex") is not None else None,
                bbox=_strip_page_from_box(bbox),
                anchor_y=bbox.get("y") if bbox else None,
                preview="",
                source_key=source_key,
                source_parent_key=parent_key,
                order=order_offset + index,
                source_details=["paragraph-heading"],
            )
        )

    return candidates


def _extract_pdf_heading_candidates(pdf_path: str, order_offset: int) -> list[OutlineCandidate]:
    """Thin wrapper – delegates to pdf_outline_parser for PDF line extraction and heading detection."""
    if PdfReader is None:
        return []

    try:
        lines = _extract_pdf_text_lines(pdf_path)
    except Exception as error:
        _logger.error(f"pdf outline line extraction skipped: {error}")
        return []

    return _build_pdf_heading_candidates(lines, order_offset)


# ── Preview / coordinate helpers ──────────────────────────────────────────────


def _build_preview(div, title_text: str) -> str:
    paragraphs = []
    for paragraph in div.find_all("p"):
        text = _clean_inline_text(paragraph.get_text(" ", strip=True))
        if not text or text == title_text:
            continue
        paragraphs.append(text)
        if len(" ".join(paragraphs)) >= 180:
            break
    return " ".join(paragraphs)[:180]


def _first_page_box(coords: list[dict]) -> dict | None:
    if not coords:
        return None

    valid_coords = [coord for coord in coords if coord.get("pageIndex") is not None]
    if not valid_coords:
        return None

    first_page = min(coord["pageIndex"] for coord in valid_coords)
    page_boxes = [coord for coord in valid_coords if coord.get("pageIndex") == first_page]
    union_box = _union_boxes(page_boxes)
    if not union_box:
        return None
    return {"pageIndex": first_page, **union_box}


# ── Merge logic ───────────────────────────────────────────────────────────────


def _merge_candidates(candidates: Iterable[OutlineCandidate]) -> list[OutlineCandidate]:
    merged: list[OutlineCandidate] = []

    for candidate in sorted(candidates, key=_candidate_sort_key):
        duplicate = _find_merge_target(merged, candidate)
        if duplicate is None:
            merged.append(candidate)
            continue

        duplicate.source = _merge_source_label(duplicate.source, candidate.source)
        duplicate.confidence = max(duplicate.confidence, candidate.confidence)
        duplicate.source_details = sorted(set(duplicate.source_details + candidate.source_details))
        if not duplicate.heading_number and candidate.heading_number:
            duplicate.heading_number = candidate.heading_number
            duplicate.display_title = _build_display_title(duplicate.raw_title, duplicate.heading_number)
            duplicate.level = _infer_level(duplicate.heading_number, duplicate.level)
        if not duplicate.bbox and candidate.bbox:
            duplicate.bbox = candidate.bbox
            duplicate.anchor_y = candidate.anchor_y
        if duplicate.page_index is None and candidate.page_index is not None:
            duplicate.page_index = candidate.page_index
            duplicate.page = candidate.page
        if not duplicate.preview and candidate.preview:
            duplicate.preview = candidate.preview

    return merged


def _find_merge_target(existing: list[OutlineCandidate], candidate: OutlineCandidate) -> OutlineCandidate | None:
    candidate_text = _normalize_merge_text(candidate.raw_title)
    for item in existing:
        if candidate.page_index is not None and item.page_index is not None:
            if candidate.page_index != item.page_index:
                continue
        if candidate_text != _normalize_merge_text(item.raw_title):
            continue
        if candidate.anchor_y is not None and item.anchor_y is not None:
            if abs(candidate.anchor_y - item.anchor_y) > 40:
                continue
        return item
    return None


def _merge_source_label(left: str, right: str) -> str:
    labels = {label for label in [left, right] if label}
    if "tei+layout" in labels:
        return "tei+layout"
    if "tei" in labels and ({"layout", "pdf-layout"} & labels):
        return "tei+layout"
    if {"layout", "pdf-layout"} <= labels:
        return "layout"
    return sorted(labels)[0] if labels else "tei"


# ── Parent inference ──────────────────────────────────────────────────────────


def _insert_missing_numbered_parents(candidates: list[OutlineCandidate]) -> list[OutlineCandidate]:
    by_number = {
        _normalize_heading_number(candidate.heading_number): candidate
        for candidate in candidates
        if _normalize_heading_number(candidate.heading_number)
    }
    additions: list[OutlineCandidate] = []

    for candidate in candidates:
        number = _normalize_heading_number(candidate.heading_number)
        if not re.match(r"^\d+(?:\.\d+)+$", number):
            continue

        parts = number.split(".")
        for depth in range(1, len(parts)):
            parent_number = ".".join(parts[:depth])
            if parent_number in by_number:
                continue

            parent = OutlineCandidate(
                raw_title=f"Section {parent_number}",
                display_title=f"{parent_number} Section {parent_number}",
                heading_number=parent_number,
                level=depth,
                source="inferred",
                confidence=0.35,
                page_index=candidate.page_index,
                page=candidate.page,
                bbox=candidate.bbox,
                anchor_y=(candidate.anchor_y - 1) if candidate.anchor_y is not None else None,
                preview="由子章节编号自动补齐的父级章节，请以原文为准。",
                source_key=f"inferred-parent-{parent_number}",
                source_parent_key=(
                    f"inferred-parent-{'.'.join(parts[:depth - 1])}" if depth > 1 else None
                ),
                order=candidate.order - (0.1 * (len(parts) - depth)),
                source_details=["inferred-missing-parent"],
            )
            additions.append(parent)
            by_number[parent_number] = parent

    if not additions:
        return candidates

    return sorted([*candidates, *additions], key=_candidate_sort_key)


# ── Finalize ──────────────────────────────────────────────────────────────────


def _finalize_outline(candidates: list[OutlineCandidate]) -> list[dict]:
    if not candidates:
        return []

    min_level = min(max(candidate.level, 1) for candidate in candidates)
    source_id_to_outline_id: dict[str, str] = {}
    outline_items: list[dict] = []

    for index, candidate in enumerate(candidates):
        level = max(1, min(6, candidate.level - min_level + 1))
        outline_id = _build_outline_id(candidate, index)
        source_id_to_outline_id[candidate.source_key] = outline_id
        outline_items.append(
            {
                "id": outline_id,
                "title": candidate.display_title,
                "displayTitle": candidate.display_title,
                "rawTitle": candidate.raw_title,
                "headingNumber": candidate.heading_number,
                "level": level,
                "nestedLevel": level,
                "parentId": None,
                "pageIndex": candidate.page_index,
                "page": candidate.page,
                "bbox": candidate.bbox,
                "anchorY": candidate.anchor_y,
                "source": candidate.source,
                "sourceDetails": candidate.source_details,
                "confidence": round(candidate.confidence, 2),
                "preview": candidate.preview,
                "type": "section",
                "order": index + 1,
                "_sourceParentKey": candidate.source_parent_key,
            }
        )

    stack: list[dict] = []
    for item in outline_items:
        explicit_parent_id = source_id_to_outline_id.get(item.pop("_sourceParentKey", "") or "")
        parent = None
        if explicit_parent_id:
            parent = next(
                (
                    previous
                    for previous in outline_items
                    if previous["id"] == explicit_parent_id and previous["level"] < item["level"]
                ),
                None,
            )

        if parent is None:
            while stack and stack[-1]["level"] >= item["level"]:
                stack.pop()
            parent = stack[-1] if stack else None

        item["parentId"] = parent["id"] if parent else None
        stack.append(item)

    return outline_items


def _build_outline_id(candidate: OutlineCandidate, index: int) -> str:
    number = candidate.heading_number.replace(".", "-").lower()
    if number:
        return f"outline-{number}-{index + 1}"
    return _stable_source_key(
        "outline",
        candidate.display_title,
        {"pageIndex": candidate.page_index, "y": candidate.anchor_y},
        index,
    )
