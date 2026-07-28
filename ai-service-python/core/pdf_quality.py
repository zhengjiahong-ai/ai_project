from __future__ import annotations

import logging
import os
import re
from typing import Any

from rag.store import normalize_id
from services.evidence_service import format_evidence_context
from services.safety_service import wrap_untrusted_context

# These constants are needed by _build_low_text_upload_response
PAPER_NOT_INDEXED_ERROR_CODE = "paper_not_indexed"
RAG_INDEX_EMPTY_MESSAGE = "论文已解析，但没有可入库的正文片段，批判阅读暂不可用。请重新上传，或确认 PDF 是可提取文字的版本。"

_logger = logging.getLogger(__name__)

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

PARSE_STATUS_PARSED = "parsed"
PARSE_STATUS_SCANNED_OR_LOW_TEXT = "scanned_or_low_text"
LOW_TEXT_PARSE_MESSAGE = "检测到的 PDF 文本量过低，可能是扫描件。请先执行 OCR 或更换文字版 PDF。"

def get_grobid_client():
    global _grobid_client

    if _grobid_client is None:
        from grobid_client.grobid_client import GrobidClient

        _grobid_client = GrobidClient(
            grobid_server=os.environ.get("GROBID_SERVER_URL", "http://grobid:8070"),
            batch_size=1,
            sleep_time=1,
            timeout=60,
        )

    return _grobid_client

def startup_warmup() -> None:
    _logger.info("Starting AI service warmup...")
    try:
        from services.analysis_service import preload_rag
        preload_rag()
        _logger.info("RAG backend is ready.")
    except Exception as error:
        _logger.info(f"RAG warmup skipped: {error}")

def _extract_title(parsed_sections: list[dict], fallback_name: str) -> str:
    if parsed_sections and parsed_sections[0].get("section") == "Front Matter (Metadata)":
        for line in parsed_sections[0].get("content", "").splitlines():
            if line.startswith("Title:"):
                title = line.replace("Title:", "", 1).strip()
                if title:
                    return title
    return fallback_name

def _extract_authors(parsed_sections: list[dict]) -> list[str]:
    if not parsed_sections or parsed_sections[0].get("section") != "Front Matter (Metadata)":
        return []

    for line in parsed_sections[0].get("content", "").splitlines():
        if line.startswith("Authors:"):
            authors = line.replace("Authors:", "", 1).strip()
            return [author.strip() for author in authors.split(",") if author.strip()]

    return []

def _build_section_outline(parsed_sections: list[dict]) -> list[dict]:
    outline: list[dict] = []
    seen: set[str] = set()

    for section in parsed_sections or []:
        title = str(section.get("section") or "").strip()
        if not title or title.lower() == "unknown" or title == "Front Matter (Metadata)":
            continue

        normalized = " ".join(title.lower().split())
        normalized_key = "|".join(
            [
                normalized,
                str(section.get("pageIndex") if section.get("pageIndex") is not None else ""),
                str(section.get("parentId") or ""),
            ]
        )
        if normalized_key in seen:
            continue
        seen.add(normalized_key)

        content = str(section.get("content") or "").strip()
        outline.append(
            {
                "id": section.get("id") or f"section-{len(outline) + 1}",
                "title": title,
                "type": "section",
                "order": len(outline) + 1,
                "preview": content[:180],
                "pageIndex": section.get("pageIndex"),
                "page": section.get("page"),
                "level": section.get("level") or 1,
                "nestedLevel": section.get("nestedLevel") or section.get("level") or 1,
                "parentId": section.get("parentId"),
                "headingNumber": section.get("headingNumber"),
            }
        )

    return outline

def _count_non_whitespace_characters(value: str) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))

def _extract_pdf_text_stats(file_path: str) -> dict[str, int]:
    if PdfReader is None:
        raise RuntimeError("PyPDF2 is required to diagnose PDF text content.")
    reader = PdfReader(file_path)
    extracted_text: list[str] = []
    for page in reader.pages:
        try:
            extracted_text.append(page.extract_text() or "")
        except Exception as error:
            _logger.error(f"PDF text extraction skipped one page: {error}")
    return {
        "pageCount": len(reader.pages),
        "textCharCount": _count_non_whitespace_characters("\n".join(extracted_text)),
    }

def _build_parse_diagnostics(
    *, page_count: int, pdf_text_char_count: int, tei_text_char_count: int
) -> dict[str, Any]:
    threshold = min(max(200, max(0, int(page_count or 0)) * 50), 2000)
    max_text_char_count = max(
        max(0, int(pdf_text_char_count or 0)),
        max(0, int(tei_text_char_count or 0)),
    )
    diagnostics: dict[str, Any] = {
        "parseStatus": PARSE_STATUS_PARSED
        if max_text_char_count >= threshold
        else PARSE_STATUS_SCANNED_OR_LOW_TEXT,
        "textThreshold": threshold,
    }
    if diagnostics["parseStatus"] == PARSE_STATUS_SCANNED_OR_LOW_TEXT:
        diagnostics["parseMessage"] = LOW_TEXT_PARSE_MESSAGE
    return diagnostics

def _build_low_text_upload_response(filename: str, pdf_stats: dict[str, int]) -> dict[str, Any]:
    diagnostics = _build_parse_diagnostics(
        page_count=pdf_stats.get("pageCount", 0),
        pdf_text_char_count=pdf_stats.get("textCharCount", 0),
        tei_text_char_count=0,
    )
    empty_section_message = "未能从论文中提取足够文本，请先执行 OCR 或更换文字版 PDF。"
    return {
        "status": "success",
        "paper_skeleton": {
            key: empty_section_message
            for key in ("abstract", "introduction", "methods", "results", "discussion", "conclusion")
        },
        "paper_structure": {
            "error": "no_content",
            "raw": "No usable text was extracted from the paper.",
            "outlineVersion": "unavailable",
            "sections": [],
        },
        "translationLayoutIndex": {},
        "pdfId": normalize_id(filename),
        "title": filename,
        "authors": [],
        "ragIndexed": False,
        "ragChunkCount": 0,
        "ragErrorCode": PAPER_NOT_INDEXED_ERROR_CODE,
        "message": RAG_INDEX_EMPTY_MESSAGE,
        "parseStatus": diagnostics["parseStatus"],
        "parseMessage": diagnostics["parseMessage"],
    }

def _build_axis_terms(query_plan: dict[str, Any], axis: dict[str, Any]) -> list[str]:
    from services.analysis_service import (
        _extract_query_terms as _extract_query_terms_local,
    )
    terms = []
    seen = set()
    for raw in [
        *(query_plan.get("keywords") or []),
        *axis.get("seed_terms", []),
        *(_extract_query_terms_local(query_plan.get("rewritten") or "")),
        *(_extract_query_terms_local(query_plan.get("original") or "")),
    ]:
        term = " ".join(str(raw or "").strip().split())
        if len(term) < 2:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term[:80])
        if len(terms) >= 12:
            break
    return terms

def _score_document(text: str, terms: list[str]) -> tuple[float, list[str]]:
    lowered = str(text or "").lower()
    matched_terms = []
    for term in terms:
        if term.lower() in lowered:
            matched_terms.append(term)

    if not matched_terms:
        return 0.0, []

    coverage = len(matched_terms) / len(terms) if terms else 0.0
    score = len(matched_terms) * 1.6
    score += coverage * 2.0
    score += min(len(lowered) / 1200, 1.0) * 0.4
    return score, matched_terms

def _format_axis_prompt_block(axis_result: dict[str, Any]) -> str:
    judge = axis_result.get("judge") or {}
    evidence_block = format_evidence_context(
        axis_result.get("evidence") or [],
        title=f"{axis_result.get('label')}证据",
        max_items=4,
        max_text_chars=450,
    ) or "\n\n证据片段：\n- 当前未检索到相关证据。"
    evidence_safety = wrap_untrusted_context(
        f"{axis_result.get('label')} evidence",
        evidence_block,
        max_tokens=1200,
    )

    return (
        f"## {axis_result.get('label')}\n"
        f"问题：{axis_result.get('question')}\n"
        f"queryPlan: {axis_result.get('queryPlan')}\n"
        f"judge: verdict={judge.get('verdict')} confidence={judge.get('confidence')} "
        f"reason={judge.get('reason')} missing={judge.get('missingAspects')}\n"
        f"{evidence_safety['wrapped']}\n"
    )

def _normalize_list_items(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    elif isinstance(value, str):
        raw_items = [
            line.strip("-* 0123456789.、 \t")
            for line in value.splitlines()
        ]
    else:
        raw_items = []

    items = []
    seen = set()
    for item in raw_items or fallback:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text[:160])
        if len(items) >= 6:
            break
    return items

