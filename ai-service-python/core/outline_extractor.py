from __future__ import annotations

import hashlib
import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable

from bs4 import BeautifulSoup

from core.document_parser import _collect_element_coords, _union_boxes

import logging
_logger = logging.getLogger(__name__)

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover - import availability depends on runtime image
    PdfReader = None

OUTLINE_VERSION = "1.4"

_DIGIT_NUMBER_RE = re.compile(r"^\s*(\d+(?:[.\-]\d+)*)(?:[.)])?(?=\s|$)")
_ROMAN_NUMBER_RE = re.compile(r"^\s*([IVXLC]+)(?:[.)])?(?=\s|$)", re.IGNORECASE)
_ALPHA_NUMBER_RE = re.compile(r"^\s*([A-Z])(?:[.)])?(?=\s|$)")
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?P<number>\d+(?:[.\-]\d+)*|[IVXLC]+|[A-Z])(?:[.)])?\s+"
    r"(?P<title>[A-Z0-9][^\n]{2,120})\s*$",
    re.IGNORECASE,
)
_NUMBERED_HEADING_PREFIX_RE = re.compile(
    r"^\s*(?P<number>\d+(?:[.\-]\d+)*|[IVXLC]+|[A-Z])(?:[.)])?\s+"
    r"(?P<tail>[A-Z0-9][^\n]{2,260})",
    re.IGNORECASE,
)
_BODY_START_BOUNDARY_RE = re.compile(
    r"\s+(?=(?:The|This|These|Those|We|Our|In this|In the|For the|For a|However|"
    r"Specifically|To address|To evaluate|As shown|Unlike)\b)"
)
_COMMON_UNNUMBERED_HEADING_RE = re.compile(
    r"^(abstract|introduction|related work|background|preliminaries|method|methods|"
    r"methodology|approach|model|model architecture|problem formulation|implementation details|"
    r"training details|experimental setup|experiment|experiments|evaluation|results|discussion|"
    r"limitations|conclusion|future work|ablation|ablation study|dataset|datasets|baselines?)$",
    re.IGNORECASE,
)

# ── Chinese heading patterns ────────────────────────────────────────────────
_CHINESE_DIGIT_CHARS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_CHINESE_DIGIT_RE = re.compile(
    r"^\s*(["
    + "".join(_CHINESE_DIGIT_CHARS)
    + r"]{1,3})(?:[、，。．.)]|(?=\s))"
)
_CHAPTER_RE = re.compile(
    r"^\s*第\s*(["
    + "".join(_CHINESE_DIGIT_CHARS)
    + r"一二三四五六七八九十]{1,3}|\d{1,2})\s*[章节部分篇](?:\s|$)"
)
_MIXED_CN_EN_HEADING_RE = re.compile(
    r"^\s*(?P<number>\d+(?:[.\-]\d+)*|["
    + "".join(_CHINESE_DIGIT_CHARS)
    + r"]{1,3})(?:[.)、，．]|\s{1,4})"
    r"(?=[一-鿿])"
    r"(?P<title>[一-鿿][^\n]{1,120})\s*$"
)
_CN_NUMBERED_HEADING_PREFIX_RE = re.compile(
    r"^\s*(?P<number>\d+(?:[.\-]\d+)*)"
    r"(?:[.)、，．]|\s{1,4})"
    r"(?P<tail>[一-鿿][^\n]{2,260})"
)
_COMMON_CHINESE_UNNUMBERED_HEADING_RE = re.compile(
    r"^(摘要|绪论|引言|前言|介绍|研究背景|相关工作|文献综述|"
    r"问题描述|问题定义|问题建模|系统模型|模型架构|方法|方法论|"
    r"研究方法|算法设计|实验设计|实验设置|实验|实验与评估|"
    r"实验结果|结果与分析|结果与讨论|讨论|局限|不足|"
    r"结论|总结与展望|未来工作|致谢|参考文献|附录|"
    r"数据|数据集|基线|基准|评估指标|消融实验|"
    r"实现细节|训练细节)$"
)

# Extended heading RE that also accepts Chinese-numbered and Chinese section headings.
_NUMBERED_HEADING_RE_WITH_CN = re.compile(
    r"^\s*(?P<number>\d+(?:[.\-]\d+)*|[IVXLC]+|[A-Z]|["
    + "".join(_CHINESE_DIGIT_CHARS)
    + r"]{1,3})(?:[.)、，．])?\s+"
    r"(?P<title>[A-Z0-9一-鿿][^\n]{2,120})\s*$",
    re.IGNORECASE,
)
_NUMBERED_HEADING_PREFIX_RE_WITH_CN = re.compile(
    r"^\s*(?P<number>\d+(?:[.\-]\d+)*|[IVXLC]+|[A-Z]|["
    + "".join(_CHINESE_DIGIT_CHARS)
    + r"]{1,3})(?:[.)、，．])?\s+"
    r"(?P<tail>[A-Z0-9一-鿿][^\n]{2,260})",
    re.IGNORECASE,
)


@dataclass
class OutlineCandidate:
    raw_title: str
    display_title: str
    heading_number: str = ""
    level: int = 1
    source: str = "tei"
    confidence: float = 0.7
    page_index: int | None = None
    page: int | None = None
    bbox: Dict[str, float] | None = None
    anchor_y: float | None = None
    preview: str = ""
    source_key: str = ""
    source_parent_key: str | None = None
    order: int = 0
    source_details: list[str] = field(default_factory=list)


@dataclass
class PdfTextFragment:
    text: str
    page_index: int
    x: float
    y: float
    font_size: float
    estimated_width: float
    is_bold: bool
    order: int


@dataclass
class PdfTextLine:
    text: str
    page_index: int
    x: float
    y: float
    width: float
    height: float
    font_size: float
    bold_ratio: float
    page_width: float
    page_height: float
    order: int


def build_document_outline(tei_path: str, pdf_path: str | None = None) -> list[dict]:
    """Build a richer paper outline from TEI heads plus conservative layout hints.

    The first source is GROBID's TEI structure. The second source catches short
    paragraph-level headings that GROBID often leaves inside a parent section.
    The optional PDF source reads line-level coordinates so same-page subheads
    can still be recovered when GROBID merges them into nearby body text.
    """
    with open(tei_path, "r", encoding="utf-8") as handle:
        soup = BeautifulSoup(handle, "xml")

    candidates = _extract_tei_head_candidates(soup)
    candidates.extend(_extract_paragraph_heading_candidates(soup, len(candidates)))
    if pdf_path:
        candidates.extend(_extract_pdf_heading_candidates(pdf_path, len(candidates)))
    merged_candidates = _merge_candidates(candidates)
    merged_candidates = _insert_missing_numbered_parents(merged_candidates)
    return _finalize_outline(merged_candidates)


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
    if PdfReader is None:
        return []

    try:
        lines = _extract_pdf_text_lines(pdf_path)
    except Exception as error:
        _logger.error(f"pdf outline line extraction skipped: {error}")
        return []

    return _build_pdf_heading_candidates(lines, order_offset)


def _extract_pdf_text_lines(pdf_path: str) -> list[PdfTextLine]:
    reader = PdfReader(pdf_path)
    fragments: list[PdfTextFragment] = []
    order = 0

    for page_index, page in enumerate(reader.pages):
        _page_width = float(page.mediabox.width or 0)  # noqa: F841
        page_height = float(page.mediabox.height or 0)

        def visitor_text(text, _cm, tm, font_dict, font_size):
            nonlocal order
            clean_text = _clean_inline_text(text)
            if not clean_text:
                return

            try:
                x = float(tm[4])
                y = float(tm[5])
            except (TypeError, ValueError, IndexError):
                return

            size = float(font_size or 0)
            if size <= 0:
                return

            font_name = str((font_dict or {}).get("/BaseFont") or "")
            top_y = max(page_height - y, 0.0) if page_height else max(y, 0.0)
            for line_text in _split_pdf_fragment_text(clean_text):
                estimated_width = max(len(line_text) * size * 0.45, size * 2)
                fragments.append(
                    PdfTextFragment(
                        text=line_text,
                        page_index=page_index,
                        x=max(x, 0.0),
                        y=top_y,
                        font_size=size,
                        estimated_width=estimated_width,
                        is_bold="bold" in font_name.lower() or "black" in font_name.lower(),
                        order=order,
                    )
                )
                order += 1

        page.extract_text(visitor_text=visitor_text)

    return _group_pdf_fragments_into_lines(fragments, reader)


def _split_pdf_fragment_text(text: str) -> list[str]:
    normalized = str(text or "").replace("\r", "\n")
    parts = [part.strip() for part in normalized.split("\n")]
    return [_clean_inline_text(part) for part in parts if _clean_inline_text(part)]


def _group_pdf_fragments_into_lines(fragments: list[PdfTextFragment], reader) -> list[PdfTextLine]:
    if not fragments:
        return []

    lines: list[PdfTextLine] = []
    fragments_by_page: dict[int, list[PdfTextFragment]] = {}
    for fragment in fragments:
        fragments_by_page.setdefault(fragment.page_index, []).append(fragment)

    for page_index, page_fragments in fragments_by_page.items():
        page = reader.pages[page_index]
        page_width = float(page.mediabox.width or 0)
        page_height = float(page.mediabox.height or 0)
        rows: list[list[PdfTextFragment]] = []

        for fragment in sorted(page_fragments, key=lambda item: (item.y, item.x, item.order)):
            target_row = None
            for row in rows:
                row_y = statistics.median(item.y for item in row)
                row_font = statistics.median(item.font_size for item in row)
                tolerance = max(2.5, row_font * 0.35, fragment.font_size * 0.35)
                if abs(fragment.y - row_y) <= tolerance:
                    target_row = row
                    break
            if target_row is None:
                rows.append([fragment])
            else:
                target_row.append(fragment)

        for row in rows:
            row_parts = sorted(row, key=lambda item: (item.x, item.order))
            segments: list[list[PdfTextFragment]] = []
            current_segment: list[PdfTextFragment] = []
            previous_right: float | None = None

            for fragment in row_parts:
                gap = 0 if previous_right is None else fragment.x - previous_right
                gap_limit = max(24.0, fragment.font_size * 3.2)
                if current_segment and gap > gap_limit:
                    segments.append(current_segment)
                    current_segment = []
                current_segment.append(fragment)
                previous_right = max(previous_right or 0, fragment.x + fragment.estimated_width)

            if current_segment:
                segments.append(current_segment)

            for segment in segments:
                line = _make_pdf_text_line(segment, page_width, page_height)
                if line:
                    lines.append(line)

    return sorted(lines, key=lambda item: (item.page_index, item.y, item.x, item.order))


def _make_pdf_text_line(
    fragments: list[PdfTextFragment],
    page_width: float,
    page_height: float,
) -> PdfTextLine | None:
    if not fragments:
        return None

    ordered = sorted(fragments, key=lambda item: (item.x, item.order))
    text = _clean_inline_text(" ".join(fragment.text for fragment in ordered))
    if not text:
        return None

    left = min(fragment.x for fragment in ordered)
    top = min(fragment.y for fragment in ordered)
    right = max(fragment.x + fragment.estimated_width for fragment in ordered)
    font_sizes = [fragment.font_size for fragment in ordered if fragment.font_size > 0]
    font_size = statistics.median(font_sizes) if font_sizes else 0.0
    bold_ratio = sum(1 for fragment in ordered if fragment.is_bold) / len(ordered)

    return PdfTextLine(
        text=text,
        page_index=ordered[0].page_index,
        x=left,
        y=top,
        width=max(right - left, font_size * 2),
        height=max(font_size * 1.2, 1.0),
        font_size=font_size,
        bold_ratio=bold_ratio,
        page_width=page_width,
        page_height=page_height,
        order=min(fragment.order for fragment in ordered),
    )


def _build_pdf_heading_candidates(lines: list[PdfTextLine], order_offset: int) -> list[OutlineCandidate]:
    candidates: list[OutlineCandidate] = []
    body_font_by_page = _estimate_body_font_by_page(lines)

    candidates.extend(_recover_split_pdf_numbered_heading_candidates(lines, body_font_by_page, order_offset))

    for index, line in enumerate(lines):
        heading_number, raw_title, confidence = _classify_pdf_line_heading(line, body_font_by_page.get(line.page_index))
        if not raw_title:
            continue
        if _should_skip_heading_candidate(raw_title, heading_number):
            continue

        bbox = {
            "pageIndex": line.page_index,
            "x": line.x,
            "y": line.y,
            "width": line.width,
            "height": line.height,
        }
        display_title = _build_display_title(raw_title, heading_number)
        candidates.append(
            OutlineCandidate(
                raw_title=raw_title,
                display_title=display_title,
                heading_number=heading_number,
                level=_infer_level(heading_number, 1),
                source="pdf-layout",
                confidence=confidence,
                page_index=line.page_index,
                page=line.page_index + 1,
                bbox=_strip_page_from_box(bbox),
                anchor_y=line.y,
                preview="",
                source_key=_stable_source_key("pdf-layout", line.text, bbox, index),
                source_parent_key=None,
                order=order_offset + index,
                source_details=["pdf-line-heading"],
            )
        )

    return sorted(candidates, key=_candidate_sort_key)


def _recover_split_pdf_numbered_heading_candidates(
    lines: list[PdfTextLine],
    body_font_by_page: dict[int, float],
    order_offset: int,
) -> list[OutlineCandidate]:
    candidates: list[OutlineCandidate] = []
    ordered_lines = sorted(lines, key=lambda item: (item.page_index, item.y, item.x, item.order))

    for index, line in enumerate(ordered_lines):
        number = _extract_standalone_heading_number(line.text)
        if not number:
            continue

        paired_line = _find_split_heading_title_line(line, ordered_lines[index + 1 : index + 8])
        if not paired_line:
            continue

        raw_title = _repair_pdf_heading_title(paired_line.text)
        if not _looks_like_numbered_heading(number, raw_title):
            continue

        bbox = _union_boxes(
            [
                {
                    "pageIndex": line.page_index,
                    "x": line.x,
                    "y": line.y,
                    "width": line.width,
                    "height": line.height,
                },
                {
                    "pageIndex": paired_line.page_index,
                    "x": paired_line.x,
                    "y": paired_line.y,
                    "width": paired_line.width,
                    "height": paired_line.height,
                },
            ]
        ) or {
            "x": min(line.x, paired_line.x),
            "y": min(line.y, paired_line.y),
            "width": line.width + paired_line.width,
            "height": max(line.height, paired_line.height),
        }
        bbox = {"pageIndex": line.page_index, **bbox}
        confidence = min(
            0.9,
            0.82
            + _pdf_heading_style_bonus(paired_line, body_font_by_page.get(line.page_index), True, raw_title)
            + 0.03,
        )

        combined_text = f"{number} {raw_title}"
        candidates.append(
            OutlineCandidate(
                raw_title=raw_title,
                display_title=_build_display_title(raw_title, number),
                heading_number=number,
                level=_infer_level(number, 2),
                source="pdf-layout",
                confidence=confidence,
                page_index=line.page_index,
                page=line.page_index + 1,
                bbox=_strip_page_from_box(bbox),
                anchor_y=bbox.get("y"),
                preview="",
                source_key=_stable_source_key("pdf-layout", combined_text, bbox, index),
                source_parent_key=None,
                order=order_offset + line.order + 0.01,
                source_details=["pdf-line-heading", "split-number-title"],
            )
        )

    return candidates


def _extract_standalone_heading_number(text: str) -> str:
    cleaned = _clean_inline_text(text)
    match = re.match(r"^(\d+(?:[.\-]\d+)+)(?:[.)])?$", cleaned)
    if not match:
        return ""
    return _normalize_heading_number(match.group(1))


def _find_split_heading_title_line(
    number_line: PdfTextLine,
    nearby_lines: list[PdfTextLine],
) -> PdfTextLine | None:
    for candidate in nearby_lines:
        if candidate.page_index != number_line.page_index:
            break
        if _looks_like_noise_line(candidate.text):
            continue

        same_row = (
            abs(candidate.y - number_line.y) <= max(4.0, number_line.font_size * 0.7)
            and candidate.x > number_line.x
        )
        next_visual_row = (
            0 < candidate.y - number_line.y <= max(12.0, number_line.font_size * 1.3)
            and abs(candidate.x - number_line.x) <= 96
        )
        if not same_row and not next_visual_row:
            if candidate.y - number_line.y > max(18.0, number_line.font_size * 1.8):
                break
            continue

        title = _repair_pdf_heading_title(candidate.text)
        if _looks_like_heading_text(title) and (_is_uppercase_heading(title) or len(title.split()) <= 10):
            return candidate

    return None


def _estimate_body_font_by_page(lines: list[PdfTextLine]) -> dict[int, float]:
    page_fonts: dict[int, list[float]] = {}
    for line in lines:
        if line.font_size <= 0:
            continue
        if len(line.text.split()) < 5:
            continue
        page_fonts.setdefault(line.page_index, []).append(round(line.font_size, 1))

    estimates: dict[int, float] = {}
    for page_index, sizes in page_fonts.items():
        if not sizes:
            continue
        estimates[page_index] = statistics.mode(sizes)

    all_sizes = [size for sizes in page_fonts.values() for size in sizes]
    if all_sizes:
        fallback = statistics.mode(all_sizes)
        for line in lines:
            estimates.setdefault(line.page_index, fallback)
    return estimates


def _classify_pdf_line_heading(line: PdfTextLine, body_font_size: float | None) -> tuple[str, str, float]:
    text = _clean_inline_text(line.text)
    if not text or len(text) > 180:
        return "", "", 0.0
    if _looks_like_noise_line(text):
        return "", "", 0.0

    number, title, confidence = _classify_paragraph_heading(text)
    if not title:
        return "", "", 0.0

    title = _repair_pdf_heading_title(title)
    if _is_noisy_pdf_alpha_heading(number, title):
        return "", "", 0.0

    if number and not _looks_like_numbered_heading(number, title):
        return "", "", 0.0

    confidence += _pdf_heading_style_bonus(line, body_font_size, bool(number), title)
    if confidence < 0.76 and not _is_strong_numbered_pdf_heading(number, title):
        return "", "", 0.0
    return number, title, min(round(confidence, 2), 0.9)


def _pdf_heading_style_bonus(line: PdfTextLine, body_font_size: float | None, has_number: bool, title: str) -> float:
    bonus = 0.0
    if body_font_size and line.font_size >= body_font_size + 0.8:
        bonus += 0.06
    if body_font_size and line.font_size >= body_font_size + 1.8:
        bonus += 0.04
    if line.bold_ratio >= 0.5:
        bonus += 0.05
    if has_number:
        bonus += 0.04
    if _is_uppercase_heading(title):
        bonus += 0.03
    return bonus


def _is_strong_numbered_pdf_heading(number: str, title: str) -> bool:
    if not re.match(r"^\d+(?:\.\d+)*$", _normalize_heading_number(number)):
        return False
    return _looks_like_numbered_heading(number, title)


def _is_noisy_pdf_alpha_heading(number: str, title: str) -> bool:
    normalized_number = _normalize_heading_number(number)
    if not re.fullmatch(r"[A-Z]", normalized_number or ""):
        return False

    cleaned = _clean_heading_title(title)
    if not cleaned:
        return True

    if normalized_number not in set("ABCDEFGH"):
        return True

    if _looks_like_formula_heading_fragment(cleaned):
        return True

    first_alpha = re.search(r"[A-Za-z]", cleaned)
    if first_alpha and cleaned[first_alpha.start()].islower():
        return True

    words = re.findall(r"[A-Za-z][A-Za-z-]{2,}|[\u4e00-\u9fff]{2,}", cleaned)
    if len(words) < 2 and not _COMMON_UNNUMBERED_HEADING_RE.match(cleaned):
        return True

    return False


def _looks_like_formula_heading_fragment(text: str) -> bool:
    cleaned = _clean_inline_text(text)
    if re.search(r"[\[\]{}=≤≥<>±−+*/_γλμΣ∑()]", cleaned):
        return True
    if re.search(r"\b(dBm|GHz|MHz|kHz|W|dB|SINR|SNR)\b", cleaned):
        return True
    if re.search(r"\b(total|rank|where|with|follows?equal)\b", cleaned, re.IGNORECASE):
        return True
    return False


def _looks_like_noise_line(text: str) -> bool:
    cleaned = _clean_inline_text(text)
    if not cleaned:
        return True
    if len(cleaned) <= 2:
        return True
    if re.fullmatch(r"\d+", cleaned):
        return True
    if re.match(r"^\s*(?:\d+\s+){3,}\d+\s+", cleaned):
        return True
    if re.fullmatch(r"(figure|fig\.|table)\s+\d+.*", cleaned, re.IGNORECASE):
        return True
    if re.search(r"\b(arxiv|doi|http|www\.)\b", cleaned, re.IGNORECASE):
        return True
    return False


def _should_skip_heading_candidate(raw_title: str, heading_number: str = "") -> bool:
    title = _clean_heading_title(raw_title)
    number = _normalize_heading_number(heading_number)
    if not title:
        return True

    if not number and re.fullmatch(r"\d+(?:[.\-]\d+)*", title):
        return True

    if not number and re.fullmatch(r"[\W_]+", title):
        return True

    # Chinese short headings (摘要, 结论, 引言, 方法 etc.) are valid
    is_chinese = bool(re.search(r"[一-鿿]", title))
    if is_chinese and _COMMON_CHINESE_UNNUMBERED_HEADING_RE.match(title):
        return False

    if len(title) <= 2 and not number:
        return True

    return False


def _classify_paragraph_heading(text: str) -> tuple[str, str, float]:
    # ── 1. Chinese chapter pattern (第X章 / 第X节) ──
    chapter_result = _try_chinese_chapter_heading(text)
    if chapter_result:
        return chapter_result

    # ── 2. Numbered heading (English / mixed / Chinese numbers) ──
    numbered_match = _NUMBERED_HEADING_RE_WITH_CN.match(text)
    if numbered_match:
        number = _normalize_heading_number(numbered_match.group("number"))
        raw_title = _clean_heading_title(numbered_match.group("title"))
        if _looks_like_numbered_heading_cn(number, raw_title):
            return number, raw_title, 0.82 if number else 0.74

    # ── 3. Mixed Chinese-English numbered heading ──
    mixed_cn_result = _try_mixed_cn_heading(text)
    if mixed_cn_result:
        return mixed_cn_result

    # ── 4. Prefixed heading (long paragraphs with a heading at the front) ──
    prefixed_heading = _extract_numbered_heading_prefix(text)
    if prefixed_heading:
        return prefixed_heading

    # ── 5. Chinese-number-only heading (一、 / 二、 / etc.) ──
    cn_digit_result = _try_chinese_digit_heading(text)
    if cn_digit_result:
        return cn_digit_result

    if len(text) > 140:
        return "", "", 0.0

    compact_text = _clean_heading_title(text)

    # ── 6. Common unnumbered headings (English + Chinese) ──
    if _COMMON_UNNUMBERED_HEADING_RE.match(compact_text):
        return "", compact_text, 0.68
    if _COMMON_CHINESE_UNNUMBERED_HEADING_RE.match(compact_text):
        return "", compact_text, 0.68

    return "", "", 0.0


def _try_chinese_chapter_heading(text: str) -> tuple[str, str, float] | None:
    """Detect headings like 第一章 研究背景 / 第2节 方法."""
    match = _CHAPTER_RE.match(text)
    if not match:
        return None
    remaining = _clean_inline_text(text[match.end():])
    if not remaining or not re.search(r"[一-鿿]", remaining):
        # 第X章  without any Chinese title text is likely just a separator
        return None
    if _looks_like_heading_text(remaining) or _COMMON_CHINESE_UNNUMBERED_HEADING_RE.match(remaining):
        return "", remaining, 0.84
    # Try to find a heading boundary in the remaining text
    boundary_title = _heading_before_body_boundary(remaining)
    if boundary_title and _looks_like_heading_text(boundary_title):
        return "", boundary_title, 0.78
    return "", remaining[:120], 0.76


def _try_mixed_cn_heading(text: str) -> tuple[str, str, float] | None:
    """Detect mixed Chinese-English headings like 1.1 研究背景 / 二、相关工作."""
    match = _MIXED_CN_EN_HEADING_RE.match(text)
    if not match:
        # Also try the prefix variant for longer paragraphs
        prefix_match = _CN_NUMBERED_HEADING_PREFIX_RE.match(text)
        if not prefix_match:
            return None
        number = _normalize_heading_number(prefix_match.group("number"))
        tail = _clean_inline_text(prefix_match.group("tail"))
        if not tail:
            return None
        boundary_title = _heading_before_body_boundary(tail)
        if boundary_title and _looks_like_heading_text(boundary_title):
            return number, boundary_title, 0.72
        # Take first 14 CJK chars as title
        title = _extract_leading_cjk_title(tail)
        if title and _looks_like_heading_text(title):
            return number, title, 0.70
        return None

    number = _normalize_heading_number(match.group("number"))
    raw_title = _clean_heading_title(match.group("title"))
    if raw_title and _looks_like_heading_text(raw_title):
        return number, raw_title, 0.80
    return None


def _try_chinese_digit_heading(text: str) -> tuple[str, str, float] | None:
    """Detect headings starting with Chinese digits like 一、引言 / 二、方法."""
    match = _CHINESE_DIGIT_RE.match(text)
    if not match:
        return None
    after_number = _clean_inline_text(text[match.end():])
    if not after_number:
        return None
    if not re.search(r"[一-鿿]", after_number):
        return None
    number = _chinese_digit_to_arabic(match.group(1))
    if not number:
        return None
    boundary_title = _heading_before_body_boundary(after_number)
    if boundary_title and _looks_like_heading_text(boundary_title):
        return number, boundary_title, 0.72
    if _COMMON_CHINESE_UNNUMBERED_HEADING_RE.match(after_number):
        return number, after_number, 0.74
    if _looks_like_heading_text(after_number):
        return number, after_number, 0.70
    return None


def _chinese_digit_to_arabic(text: str) -> str:
    """Convert simple Chinese digit text (一-十, 十一-二十) to Arabic string."""
    text = text.strip()
    if not text:
        return ""
    if text in _CHINESE_DIGIT_CHARS:
        return str(_CHINESE_DIGIT_CHARS[text])
    if len(text) == 2 and text[0] == "十":
        # 十一 → 11, 十二 → 12, ...
        units = _CHINESE_DIGIT_CHARS.get(text[1], 0)
        return str(10 + units)
    if len(text) == 2 and text[1] == "十":
        # 二十 → 20
        tens = _CHINESE_DIGIT_CHARS.get(text[0], 0)
        return str(tens * 10)
    return text


def _extract_leading_cjk_title(text: str, max_chars: int = 14) -> str:
    """Extract leading CJK characters + mixed script as a title fragment."""
    words = re.findall(r"[一-鿿　-〿＀-￯]+|[A-Za-z][A-Za-z-]{2,}", text)
    title_parts: list[str] = []
    for w in words:
        title_parts.append(w)
        if len("".join(title_parts)) >= max_chars:
            break
    return " ".join(title_parts).strip()


def _looks_like_numbered_heading_cn(number: str, title: str) -> bool:
    """Extended version of _looks_like_numbered_heading that also handles Chinese titles."""
    cleaned = _clean_heading_title(title)
    normalized_number = _normalize_heading_number(number)
    if not normalized_number or not _looks_like_heading_text(cleaned):
        return False
    if re.fullmatch(r"\d{3,}", normalized_number):
        return False
    if not any(char.isalpha() for char in cleaned) and not re.search(r"[一-鿿]", cleaned):
        return False
    if re.fullmatch(r"\d+", normalized_number) and _looks_like_numbered_sentence_item(cleaned):
        return False
    if _COMMON_UNNUMBERED_HEADING_RE.match(cleaned) or _COMMON_CHINESE_UNNUMBERED_HEADING_RE.match(cleaned):
        return True
    if _is_uppercase_heading(cleaned):
        return True
    word_tokens = re.findall(r"[A-Za-z][A-Za-z-]{2,}|[一-鿿]{2,}", cleaned)
    if len(word_tokens) >= 2:
        return True
    if re.fullmatch(r"[IVXLC]+|[A-Z]", normalized_number, re.IGNORECASE) and len(word_tokens) >= 1:
        return True
    # Chinese titles: single longer CJK term is acceptable
    if re.search(r"[一-鿿]", cleaned) and len(cleaned) >= 3:
        return True
    return False


def _extract_numbered_heading_prefix(text: str) -> tuple[str, str, float] | None:
    match = _NUMBERED_HEADING_PREFIX_RE_WITH_CN.match(text)
    if not match:
        return None

    number = _normalize_heading_number(match.group("number"))
    tail = _clean_inline_text(match.group("tail"))
    if not number or not tail:
        return None

    uppercase_title = _leading_uppercase_heading(tail)
    if uppercase_title and _looks_like_numbered_heading_cn(number, uppercase_title):
        return number, uppercase_title, 0.78

    boundary_title = _heading_before_body_boundary(tail)
    if boundary_title and _looks_like_numbered_heading_cn(number, boundary_title):
        return number, boundary_title, 0.72

    # Chinese section: try extracting a leading CJK title
    if re.search(r"[一-鿿]", tail):
        cn_title = _extract_leading_cjk_title(tail)
        if cn_title and _looks_like_numbered_heading_cn(number, cn_title):
            return number, cn_title, 0.70

    return None


def _leading_uppercase_heading(text: str) -> str:
    tokens = text.split()
    heading_tokens: list[str] = []
    for token in tokens:
        stripped = token.strip(" ,;:()[]{}")
        if not stripped:
            continue
        has_alpha = any(char.isalpha() for char in stripped)
        is_upperish = not has_alpha or stripped.upper() == stripped
        if not is_upperish:
            break
        heading_tokens.append(stripped)
        if len(" ".join(heading_tokens)) > 120:
            break

    candidate = _clean_heading_title(" ".join(heading_tokens))
    if _looks_like_heading_text(candidate) and len(candidate.split()) >= 2:
        return candidate
    return ""


def _heading_before_body_boundary(text: str) -> str:
    match = _BODY_START_BOUNDARY_RE.search(text)
    if not match:
        return ""

    candidate = _clean_heading_title(text[: match.start()])
    if _looks_like_heading_text(candidate):
        return candidate
    return ""


def _is_uppercase_heading(text: str) -> bool:
    letters = [char for char in str(text or "") if char.isalpha()]
    if len(letters) < 4:
        return False
    uppercase_letters = [char for char in letters if char.upper() == char]
    return len(uppercase_letters) / len(letters) >= 0.82


def _repair_pdf_heading_title(text: str) -> str:
    cleaned = _clean_heading_title(text)
    cleaned = re.sub(r"(?<=[A-Za-z])-\s+(?=[A-Za-z])", "", cleaned)
    cleaned = re.sub(r"\b([A-Za-z])\s+([a-z]{2,})\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", r"\1\2", cleaned)
    return _clean_heading_title(cleaned)


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


def _candidate_sort_key(candidate: OutlineCandidate) -> tuple[float, float, float, float, float]:
    page = candidate.page_index if candidate.page_index is not None else 10**9
    bbox = candidate.bbox or {}
    x = float(bbox.get("x") or 10**9)
    y = candidate.anchor_y if candidate.anchor_y is not None else float(bbox.get("y") or 10**9)
    column = _infer_two_column_index(x)
    return (page, column, y, x, float(candidate.order))


def _infer_two_column_index(x: float) -> int:
    if x >= 10**8:
        return 2
    return 0 if x < 250 else 1


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


def _split_heading_number(text: str, explicit_number: str = "") -> tuple[str, str]:
    normalized_explicit = _normalize_heading_number(explicit_number)
    cleaned = _clean_heading_title(text)
    number = normalized_explicit

    match = _NUMBERED_HEADING_RE_WITH_CN.match(cleaned)
    if match:
        parsed_number = _normalize_heading_number(match.group("number"))
        if parsed_number:
            number = number or parsed_number
            return number, _clean_heading_title(match.group("title"))

    # Try Chinese chapter pattern (第一章 研究背景)
    ch_match = _CHAPTER_RE.match(cleaned)
    if ch_match:
        remaining = _clean_inline_text(cleaned[ch_match.end():])
        if remaining:
            return number, remaining

    # Try Chinese digit prefix (一、引言 / 二、相关工作)
    cn_digit_match = _CHINESE_DIGIT_RE.match(cleaned)
    if cn_digit_match:
        cn_number = _chinese_digit_to_arabic(cn_digit_match.group(1))
        after = _clean_inline_text(cleaned[cn_digit_match.end():])
        if cn_number and after:
            return cn_number, after

    # Try mixed EN number + CN title (1.1 研究背景)
    mixed_match = _MIXED_CN_EN_HEADING_RE.match(cleaned)
    if mixed_match:
        parsed_number = _normalize_heading_number(mixed_match.group("number"))
        parsed_title = _clean_heading_title(mixed_match.group("title"))
        if parsed_number and parsed_title:
            return parsed_number, parsed_title

    if number:
        escaped = re.escape(number).replace(r"\.", r"[.\-]")
        cleaned = re.sub(rf"^\s*{escaped}(?:[.)])?\s+", "", cleaned, flags=re.IGNORECASE).strip()

    return number, cleaned


def _normalize_heading_number(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    # Chinese digit → Arabic
    cn_arabic = _chinese_digit_to_arabic(text)
    if cn_arabic and cn_arabic.isdigit():
        return cn_arabic

    for pattern in (_DIGIT_NUMBER_RE, _ALPHA_NUMBER_RE, _ROMAN_NUMBER_RE):
        match = pattern.match(text)
        if match:
            return match.group(1).replace("-", ".").rstrip(".").upper()
    return ""


def _infer_level(heading_number: str, fallback_level: int) -> int:
    number = _normalize_heading_number(heading_number)
    if not number:
        return max(1, min(6, fallback_level))

    if re.match(r"^\d", number):
        return max(1, min(6, len([part for part in number.split(".") if part])))
    if _is_roman_section_number(number):
        return 1
    if re.match(r"^[A-Z]$", number):
        return max(2, min(6, fallback_level))
    return max(1, min(6, fallback_level))


def _is_roman_section_number(number: str) -> bool:
    normalized = str(number or "").strip().upper()
    if not re.fullmatch(r"[IVXLC]+", normalized):
        return False
    if len(normalized) == 1:
        return normalized in {"I", "V", "X"}
    return True


def _build_display_title(raw_title: str, heading_number: str) -> str:
    title = _clean_heading_title(raw_title)
    number = _normalize_heading_number(heading_number)
    if not number:
        return title

    prefix = f"{number}." if re.match(r"^[A-Z]$|^[IVXLC]+$", number, re.IGNORECASE) else number
    if title.lower().startswith(prefix.lower()):
        return title
    return f"{prefix} {title}".strip()


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


def _strip_page_from_box(box: dict | None) -> dict | None:
    if not box:
        return None
    return {
        "x": round(float(box.get("x") or 0), 2),
        "y": round(float(box.get("y") or 0), 2),
        "width": round(float(box.get("width") or 0), 2),
        "height": round(float(box.get("height") or 0), 2),
    }


def _looks_like_heading_text(text: str) -> bool:
    cleaned = _clean_heading_title(text)
    if not cleaned or len(cleaned) > 120:
        return False
    if cleaned.endswith((".", ",", ";", ":")) and not _COMMON_UNNUMBERED_HEADING_RE.match(cleaned.rstrip(".:")):
        return False
    words = cleaned.split()
    return 1 <= len(words) <= 14


def _looks_like_numbered_heading(number: str, title: str) -> bool:
    cleaned = _clean_heading_title(title)
    normalized_number = _normalize_heading_number(number)
    if not normalized_number or not _looks_like_heading_text(cleaned):
        return False

    if re.fullmatch(r"\d{3,}", normalized_number):
        return False

    if not any(char.isalpha() for char in cleaned):
        return False

    if re.fullmatch(r"\d+", normalized_number) and _looks_like_numbered_sentence_item(cleaned):
        return False

    if _COMMON_UNNUMBERED_HEADING_RE.match(cleaned):
        return True

    if _is_uppercase_heading(cleaned):
        return True

    word_tokens = re.findall(r"[A-Za-z][A-Za-z-]{2,}|[\u4e00-\u9fff]{2,}", cleaned)
    if len(word_tokens) >= 2:
        return True

    if re.fullmatch(r"[IVXLC]+|[A-Z]", normalized_number, re.IGNORECASE) and len(word_tokens) >= 1:
        return True

    return False


def _looks_like_numbered_sentence_item(title: str) -> bool:
    cleaned = _clean_heading_title(title)
    if not cleaned or _is_uppercase_heading(cleaned) or _COMMON_UNNUMBERED_HEADING_RE.match(cleaned):
        return False

    words = cleaned.split()
    lowered = cleaned.lower()
    sentence_starters = (
        "we ",
        "our ",
        "this ",
        "these ",
        "those ",
        "inspired ",
        "based ",
        "given ",
        "using ",
        "unlike ",
        "to ",
        "for ",
        "by ",
    )
    if lowered.startswith(sentence_starters):
        return True

    if len(words) >= 9:
        return True

    if re.search(r"\b(we|our|this paper|we conduct|we propose|we show|we evaluate|we demonstrate)\b", lowered):
        return True

    if re.search(r"\b(is|are|was|were|be|being|been|has|have|had|can|could|will|would|should)\b", lowered):
        return True

    return False


def _clean_inline_text(text: Any) -> str:
    return re.sub(r"\s+", " ", _normalize_ligatures(str(text or ""))).strip()


def _normalize_ligatures(text: str) -> str:
    return str(text or "").translate(
        str.maketrans(
            {
                "ﬀ": "ff",
                "ﬁ": "fi",
                "ﬂ": "fl",
                "ﬃ": "ffi",
                "ﬄ": "ffl",
            }
        )
    )


def _clean_heading_title(text: Any) -> str:
    cleaned = _clean_inline_text(text)
    return cleaned.strip(" \t\r\n:-")


def _normalize_merge_text(text: str) -> str:
    text = _clean_heading_title(text).lower()
    text = re.sub(r"^\d+(?:\.\d+)*(?:[.)])?\s+", "", text)
    text = re.sub(r"^[a-zivxlc]+(?:[.)])\s+", "", text, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text).strip()


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


def _stable_source_key(prefix: str, text: str, bbox: dict | None, index: int) -> str:
    page = "" if not bbox else str(bbox.get("pageIndex", ""))
    y = "" if not bbox else str(round(float(bbox.get("y") or 0), 1))
    digest = hashlib.sha1(f"{text}|{page}|{y}|{index}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"
