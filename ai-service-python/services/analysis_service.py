import os
import shutil
import tempfile
import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup
from fastapi import UploadFile

try:
    from PyPDF2 import PdfReader
except ImportError:  # pragma: no cover - deployment dependency guard
    PdfReader = None

from core.document_parser import extract_translation_layout_index, parse_tei_xml
from core.outline_extractor import OUTLINE_VERSION, build_document_outline
from llm.client import get_llm
from rag.store import get_rag, is_rag_available, normalize_id, preload_rag
from schemas.requests import BackgroundKnowledgeRequest, DeepAnalysisRequest
from services.background_knowledge_service import get_background_knowledge as build_background_knowledge
from services.evidence_service import (
    build_field_sentence_source_map,
    compact_evidence_for_response,
    format_evidence_context,
    normalize_evidence_items,
)
from services.math_markdown import MATH_MARKDOWN_GUIDELINE
from services.query_service import build_retrieval_queries
from services.retrieval_judge_service import judge_evidence_quality
from services.safety_service import (
    MAX_RETRIEVAL_RETRIES,
    build_guarded_messages,
    summarize_safety_results,
    wrap_untrusted_context,
)
from services.trace_service import finalize_trace, record_counter, record_metric, sanitize_text, start_trace, trace_step
from services.utils import parse_json_from_llm

import logging
_logger = logging.getLogger(__name__)


_grobid_client = None
ANALYSIS_CHUNK_SIZE = 1200
ANALYSIS_CHUNK_OVERLAP = 200
ANALYSIS_RETRIEVAL_LIMIT = 4
ANALYSIS_RESPONSE_SOURCE_LIMIT = 10
CLAIM_SUPPORT_LIMIT = 6
PAPER_NOT_INDEXED_ERROR_CODE = "paper_not_indexed"
RAG_INDEX_UNAVAILABLE_ERROR_CODE = "rag_index_unavailable"
PAPER_NOT_INDEXED_MESSAGE = "当前论文尚未完成全文索引，请重新上传或重新解析后再试。"
RAG_INDEX_EMPTY_MESSAGE = "论文已解析，但没有可入库的正文片段，批判阅读暂不可用。请重新上传，或确认 PDF 是可提取文字的版本。"
RAG_INDEX_UNAVAILABLE_MESSAGE = "论文已解析，但全文索引服务暂不可用，批判阅读暂不可用。请稍后重新解析或重启 AI 服务后再试。"
PARSE_STATUS_PARSED = "parsed"
PARSE_STATUS_SCANNED_OR_LOW_TEXT = "scanned_or_low_text"
LOW_TEXT_PARSE_MESSAGE = "检测到的 PDF 文本量过低，可能是扫描件。请先执行 OCR 或更换文字版 PDF。"
ANALYSIS_AXIS_CONFIGS = (
    {
        "key": "contributions",
        "label": "贡献与创新",
        "question": "这篇论文显式宣称了哪些贡献、创新点或核心主张？",
        "seed_terms": ["贡献", "创新", "主张", "贡献点", "claim", "contribution", "novelty"],
    },
    {
        "key": "methods",
        "label": "方法与机制",
        "question": "这篇论文的方法、模型设计或关键机制是什么？这些设计的直接证据是否清楚？",
        "seed_terms": ["方法", "模型", "机制", "模块", "流程", "method", "architecture", "framework"],
    },
    {
        "key": "experiments",
        "label": "实验与结果",
        "question": "这篇论文提供了哪些实验、指标、对比或结果来支撑结论？",
        "seed_terms": ["实验", "结果", "指标", "评估", "对比", "ablation", "benchmark", "metric", "evaluation"],
    },
    {
        "key": "limitations",
        "label": "局限与风险",
        "question": "这篇论文提到了哪些局限、风险、失败情形或尚未验证的部分？",
        "seed_terms": ["局限", "不足", "风险", "失败", "future work", "limitation", "weakness", "risk"],
    },
)
VALID_SUPPORT_LEVELS = {"SUPPORTED", "PARTIAL", "UNSUPPORTED"}
SUPPORT_SIGNAL_TERMS = [
    "experiment",
    "experiments",
    "experimental",
    "result",
    "results",
    "evaluation",
    "metric",
    "benchmark",
    "baseline",
    "comparison",
    "ablation",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "auc",
    "提升",
    "提高",
    "优于",
    "实验",
    "结果",
    "指标",
    "评估",
    "基准",
    "对比",
    "消融",
    "准确率",
]
TABLE_FIGURE_LABEL_RE = re.compile(
    r"\b(?:table|fig\.?|figure)\s*[:.]?\s*\d+[a-z]?\b|(?:表|图)\s*[:：]?\s*\d+[a-z]?",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"[+-]?\d+(?:\.\d+)?\s*[%％]")
PLUS_MINUS_RE = re.compile(r"[+-]?\d+(?:\.\d+)?\s*(?:±|\+/-)\s*\d+(?:\.\d+)?")
DECIMAL_RE = re.compile(r"(?<![A-Za-z])\b[+-]?\d+\.\d+\b")
METRIC_ALIASES = {
    "accuracy": ["accuracy", "acc", "准确率"],
    "f1": ["f1", "f1-score", "f1 score", "f1值", "f1 值"],
    "precision": ["precision", "精确率", "精度"],
    "recall": ["recall", "召回率"],
    "auc": ["auc"],
    "bleu": ["bleu"],
    "rouge": ["rouge"],
    "map": ["map", "mAP"],
    "latency": ["latency", "延迟"],
    "throughput": ["throughput", "吞吐"],
    "performance": ["performance", "性能"],
}
NUMERIC_CHANGE_TERMS = [
    "improve",
    "improves",
    "improved",
    "gain",
    "gains",
    "increase",
    "increases",
    "decrease",
    "decreases",
    "提升",
    "提高",
    "增加",
    "下降",
    "降低",
]


class PaperNotIndexedError(RuntimeError):
    def __init__(
        self,
        pdf_id: str | None = None,
        message: str = PAPER_NOT_INDEXED_MESSAGE,
        error_code: str = PAPER_NOT_INDEXED_ERROR_CODE,
    ):
        super().__init__(message)
        self.pdf_id = pdf_id
        self.message = message
        self.error_code = error_code
        self.trace_id: str | None = None

    def to_response(self) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "status": "error",
            "errorCode": self.error_code,
            "message": self.message,
        }
        if self.pdf_id:
            response["pdfId"] = self.pdf_id
        if self.trace_id:
            response["traceId"] = self.trace_id
        return response


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


def _extract_pdf_text_stats(file_path: str) -> Dict[str, int]:
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
) -> Dict[str, Any]:
    threshold = min(max(200, max(0, int(page_count or 0)) * 50), 2000)
    max_text_char_count = max(
        max(0, int(pdf_text_char_count or 0)),
        max(0, int(tei_text_char_count or 0)),
    )
    diagnostics: Dict[str, Any] = {
        "parseStatus": PARSE_STATUS_PARSED
        if max_text_char_count >= threshold
        else PARSE_STATUS_SCANNED_OR_LOW_TEXT,
        "textThreshold": threshold,
    }
    if diagnostics["parseStatus"] == PARSE_STATUS_SCANNED_OR_LOW_TEXT:
        diagnostics["parseMessage"] = LOW_TEXT_PARSE_MESSAGE
    return diagnostics


def _build_low_text_upload_response(filename: str, pdf_stats: Dict[str, int]) -> Dict[str, Any]:
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


async def analyze_pdf(file: UploadFile) -> Dict[str, Any]:
    input_dir = tempfile.mkdtemp()
    output_dir = tempfile.mkdtemp()

    try:
        file_path = os.path.join(input_dir, "target_paper.pdf")
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        pdf_stats = _extract_pdf_text_stats(file_path)

        get_grobid_client().process(
            "processFulltextDocument",
            input_path=input_dir,
            output=output_dir,
            consolidate_citations=False,
            tei_coordinates=True,
        )

        xml_files = [name for name in os.listdir(output_dir) if name.endswith(".tei.xml")]
        if not xml_files:
            diagnostics = _build_parse_diagnostics(
                page_count=pdf_stats.get("pageCount", 0),
                pdf_text_char_count=pdf_stats.get("textCharCount", 0),
                tei_text_char_count=0,
            )
            if diagnostics["parseStatus"] == PARSE_STATUS_SCANNED_OR_LOW_TEXT:
                return _build_low_text_upload_response(file.filename or "uploaded.pdf", pdf_stats)
            raise RuntimeError("GROBID did not produce a TEI XML file.")

        tei_file = os.path.join(output_dir, xml_files[0])
        parsed_sections = parse_tei_xml(tei_file)
        tei_text_char_count = sum(
            _count_non_whitespace_characters(section.get("content", ""))
            for section in parsed_sections
        )
        parse_diagnostics = _build_parse_diagnostics(
            page_count=pdf_stats.get("pageCount", 0),
            pdf_text_char_count=pdf_stats.get("textCharCount", 0),
            tei_text_char_count=tei_text_char_count,
        )
        translation_layout_index = extract_translation_layout_index(tei_file)
        outline_version = OUTLINE_VERSION
        try:
            section_outline = build_document_outline(tei_file, file_path)
        except Exception as error:
            _logger.error(f"outline extraction failed, falling back to parsed sections: {error}")
            outline_version = "legacy-fallback"
            section_outline = _build_section_outline(parsed_sections)

        sections_for_summary = {
            "abstract": "",
            "introduction": "",
            "methods": "",
            "results": "",
            "discussion": "",
            "conclusion": "",
        }

        with open(tei_file, "r", encoding="utf-8") as handle:
            soup = BeautifulSoup(handle, "xml")
            abstract_tag = soup.find("abstract")
            if abstract_tag:
                sections_for_summary["abstract"] = abstract_tag.get_text(separator=" ", strip=True)

        for section in parsed_sections:
            heading = section.get("section", "").lower()
            content = section.get("content", "")

            if any(keyword in heading for keyword in ["intro", "background", "preliminar"]):
                sections_for_summary["introduction"] += content
            elif any(keyword in heading for keyword in ["method", "approach", "model", "design", "implementation"]):
                sections_for_summary["methods"] += content
            elif any(keyword in heading for keyword in ["result", "experiment", "evaluation", "finding"]):
                sections_for_summary["results"] += content
            elif any(keyword in heading for keyword in ["discuss", "limitation", "related work"]):
                sections_for_summary["discussion"] += content
            elif any(keyword in heading for keyword in ["conclu", "summary", "future"]):
                sections_for_summary["conclusion"] += content

        combined_context = ""
        for name, text in sections_for_summary.items():
            if len(text.strip()) > 50:
                combined_context += f"### Section: {name.upper()}\nContent: {text.strip()[:2500]}\n\n"

        paper_structure: Dict[str, Any] = {}
        if combined_context:
            summary_prompt = f"""
You are a rigorous paper reader.
Summarize each paper section below in concise Chinese.
Return valid JSON only with these keys:
abstract, introduction, methods, results, discussion, conclusion.

Paper context:
{combined_context}
"""
            raw_response = get_llm()._call(summary_prompt)
            section_summaries = parse_json_from_llm(raw_response)

            try:
                structure_prompt = f"""
You are an academic paper structure analyst.
Extract the following JSON from the paper context below.
Return valid JSON only.

{{
    "research_problem": "",
    "core_hypothesis": "",
    "method_framework": [],
    "claimed_contributions": [],
    "experimental_logic": "",
    "limitations": ""
}}

Paper context:
{combined_context}
"""
                structure_raw = get_llm()._call(structure_prompt)
                paper_structure = parse_json_from_llm(structure_raw)
                paper_structure["outlineVersion"] = outline_version
                paper_structure["sections"] = section_outline
            except Exception as error:
                _logger.error(f"paper_structure generation failed: {error}")
                paper_structure = {
                    "error": "structure_parse_failed",
                    "raw": str(error)[:500],
                    "outlineVersion": outline_version,
                    "sections": section_outline,
                }
        else:
            section_summaries = {
                key: "未能从论文中提取足够文本，请确认 PDF 是否为可解析的文字版。"
                for key in sections_for_summary
            }
            paper_structure = {
                "error": "no_content",
                "raw": "No usable text was extracted from the paper.",
                "outlineVersion": outline_version,
                "sections": section_outline,
            }

        clean_pdf_id = normalize_id(file.filename)
        title = _extract_title(parsed_sections, file.filename)
        authors = _extract_authors(parsed_sections)
        rag_indexed = True
        rag_message = None
        rag_error_code = None
        rag_chunk_count = 0
        try:
            rag = get_rag()
            if not is_rag_available(rag):
                raise RuntimeError("RAG backend is unavailable.")

            rag_chunk_count = rag.add_sections_to_db(
                parsed_sections,
                file_path,
                {"id": clean_pdf_id, "title": title},
            )
            _logger.info(f"Indexed paper {title} ({clean_pdf_id}) into RAG with {rag_chunk_count} chunks.")
            if rag_chunk_count <= 0:
                rag_indexed = False
                rag_error_code = PAPER_NOT_INDEXED_ERROR_CODE
                rag_message = RAG_INDEX_EMPTY_MESSAGE
            else:
                indexed_documents = rag.get_documents_by_metadata({"id": clean_pdf_id}, limit=1)
                if not indexed_documents:
                    rag_indexed = False
                    rag_error_code = PAPER_NOT_INDEXED_ERROR_CODE
                    rag_message = "论文正文索引写入后校验未命中，批判阅读暂不可用。请重新上传或重新解析后再试。"
        except Exception as error:
            _logger.error(f"RAG indexing failed: {error}")
            rag_indexed = False
            rag_error_code = RAG_INDEX_UNAVAILABLE_ERROR_CODE
            rag_message = f"{RAG_INDEX_UNAVAILABLE_MESSAGE}（{error}）"

        response = {
            "status": "success",
            "paper_skeleton": section_summaries,
            "paper_structure": paper_structure,
            "translationLayoutIndex": translation_layout_index,
            "pdfId": clean_pdf_id,
            "title": title,
            "authors": authors,
            "ragIndexed": rag_indexed,
            "ragChunkCount": rag_chunk_count,
            "parseStatus": parse_diagnostics["parseStatus"],
        }
        if parse_diagnostics.get("parseMessage"):
            response["parseMessage"] = parse_diagnostics["parseMessage"]
        if rag_message:
            response["message"] = rag_message
        if rag_error_code:
            response["ragErrorCode"] = rag_error_code
        return response
    finally:
        if os.path.exists(input_dir):
            shutil.rmtree(input_dir)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)


def get_background_knowledge(request: BackgroundKnowledgeRequest) -> Dict[str, Any]:
    return build_background_knowledge(request)


def _chunk_text(text: str, chunk_size: int = ANALYSIS_CHUNK_SIZE, overlap: int = ANALYSIS_CHUNK_OVERLAP) -> List[str]:
    value = str(text or "").strip()
    if not value:
        return []

    chunks = []
    start = 0
    while start < len(value):
        end = min(len(value), start + chunk_size)
        chunk = value[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(value):
            break
        next_start = max(0, end - overlap)
        if next_start <= start:
            next_start = end
        start = next_start
    return chunks


def _build_inline_documents(paper_content: str) -> List[Dict[str, Any]]:
    documents = []
    for index, chunk in enumerate(_chunk_text(paper_content)):
        documents.append({
            "sourceId": f"inline-{index + 1}",
            "text": chunk,
            "metadata": {"chunk_index": index, "source": "paper_content"},
            "chunkIndex": index,
            "sourceType": "current_paper",
        })
    return normalize_evidence_items(documents, source_type="current_paper", max_text_chars=1800)


def _load_analysis_source(request: DeepAnalysisRequest) -> tuple[List[Dict[str, Any]], str, str | None, str]:
    with trace_step(
        "load_analysis_source",
        meta={"hasInlineContent": bool(request.paper_content), "pdfId": sanitize_text(request.pdf_id, max_chars=80)},
    ) as step:
        if request.paper_content and request.paper_content.strip():
            documents = _build_inline_documents(request.paper_content)
            if not documents:
                raise ValueError("No usable paper_content was provided for deep analysis.")
            paper_content = "\n\n".join(item.get("text", "") for item in documents)
            step["outputSize"] = len(documents)
            return documents, "paper_content", None, paper_content

        if request.pdf_id:
            record_counter("retrievalCalls")
            normalized_id = normalize_id(request.pdf_id)
            rag = get_rag()
            if not is_rag_available(rag):
                raise PaperNotIndexedError(
                    normalized_id,
                    RAG_INDEX_UNAVAILABLE_MESSAGE,
                    RAG_INDEX_UNAVAILABLE_ERROR_CODE,
                )
            raw_documents = rag.get_documents_by_metadata({"id": normalized_id}, limit=400)
            documents = normalize_evidence_items(
                raw_documents,
                source_type="current_paper",
                pdf_id=normalized_id,
                max_text_chars=1800,
            )
            if not documents:
                raise PaperNotIndexedError(normalized_id)

            paper_content = "\n\n".join(item.get("text", "") for item in documents)
            step["outputSize"] = len(documents)
            return documents, "pdf_id", normalized_id, paper_content

        raise ValueError("Either paper_content or pdf_id is required.")


def resolve_paper_content(request: DeepAnalysisRequest) -> tuple[str, str, str | None]:
    _, resolved_from, normalized_id, paper_content = _load_analysis_source(request)
    return paper_content, resolved_from, normalized_id


def _build_analysis_context(documents: List[Dict[str, Any]], max_docs: int = 4, max_chars: int = 2400) -> str:
    parts = []
    for item in documents[:max_docs]:
        text = str(item.get("text") or "").strip()
        if text:
            parts.append(text[:600])
    return "\n\n".join(parts)[:max_chars]


def _extract_query_terms(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{1,31}|[\u4e00-\u9fff]{2,12}", str(text or ""))
    results = []
    seen = set()
    for token in tokens:
        values = [token]
        if re.fullmatch(r"[\u4e00-\u9fff]{9,12}", token):
            values = [token[:8], token[-8:]]
        for value in values:
            cleaned = str(value).strip()
            if len(cleaned) < 2:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(cleaned)
    return results[:12]


def _deduplicate_evidence(items: List[Dict[str, Any]], limit: int | None = None) -> List[Dict[str, Any]]:
    deduped = []
    seen = set()
    for item in items:
        text_key = " ".join(str(item.get("text") or "").lower().split())
        if not text_key or text_key in seen:
            continue
        seen.add(text_key)
        deduped.append(item)
        if limit is not None and len(deduped) >= limit:
            break
    return deduped


def _merge_evidence_lists(*groups: List[Dict[str, Any]], limit: int | None = None) -> List[Dict[str, Any]]:
    merged = []
    for group in groups:
        merged.extend(group or [])
    return _deduplicate_evidence(merged, limit=limit)


def _build_axis_terms(query_plan: Dict[str, Any], axis: Dict[str, Any]) -> List[str]:
    terms = []
    seen = set()
    for raw in [
        *(query_plan.get("keywords") or []),
        *axis.get("seed_terms", []),
        *_extract_query_terms(query_plan.get("rewritten") or ""),
        *_extract_query_terms(query_plan.get("original") or ""),
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


def _score_document(text: str, terms: List[str]) -> tuple[float, List[str]]:
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


def _retrieve_axis_evidence(
    documents: List[Dict[str, Any]],
    query_plan: Dict[str, Any],
    axis: Dict[str, Any],
    limit: int = ANALYSIS_RETRIEVAL_LIMIT,
) -> List[Dict[str, Any]]:
    with trace_step(
        f"axis_{axis.get('key')}_retrieve",
        input_size=len(documents),
        meta={"label": axis.get("label")},
    ) as step:
        record_counter("retrievalCalls")
        terms = _build_axis_terms(query_plan, axis)
        if not terms:
            step["outputSize"] = 0
            return []

        scored_items = []
        for item in documents:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            score, matched_terms = _score_document(text, terms)
            if score <= 0:
                continue

            coverage = len(matched_terms) / len(terms) if terms else 0.0
            similarity = min(0.95, 0.42 + coverage * 0.4 + min(score / 12, 0.12))
            metadata = dict(item.get("metadata") or {})
            metadata["matched_terms"] = matched_terms[:8]

            scored_item = {
                **item,
                "metadata": metadata,
                "score": round(score, 3),
                "similarity": round(max(float(item.get("similarity") or 0), similarity), 3),
            }
            scored_items.append(scored_item)

        scored_items.sort(
            key=lambda current: (float(current.get("score") or 0), float(current.get("similarity") or 0)),
            reverse=True,
        )
        deduped = _deduplicate_evidence(scored_items, limit=limit)
        step["outputSize"] = len(deduped)
        return deduped


def _should_retry_retrieval(judge_result: Dict[str, Any]) -> bool:
    return MAX_RETRIEVAL_RETRIES > 0 and bool(judge_result.get("shouldRetry")) and (
        judge_result.get("verdict") != "CORRECT" or float(judge_result.get("confidence") or 0) < 0.68
    )


def _build_retry_query(question: str, query_plan: Dict[str, Any], axis: Dict[str, Any], judge_result: Dict[str, Any]) -> str:
    parts = [
        query_plan.get("original") or question,
        query_plan.get("rewritten") or "",
        *(query_plan.get("keywords") or []),
        *axis.get("seed_terms", []),
        *(judge_result.get("missingAspects") or []),
    ]

    unique_parts = []
    seen = set()
    for part in parts:
        text = " ".join(str(part or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_parts.append(text)

    return " ".join(unique_parts)[:500] or question


def _analyze_axis(
    axis: Dict[str, Any],
    documents: List[Dict[str, Any]],
    analysis_context: str,
) -> Dict[str, Any]:
    question = axis["question"]
    with trace_step(
        f"axis_{axis.get('key')}_query_plan",
        input_size=len(str(analysis_context or "")),
        meta={"label": axis.get("label")},
    ) as step:
        query_plan = build_retrieval_queries(question, context=analysis_context, task_type="critical")
        step["outputSize"] = len(query_plan.get("keywords") or [])
    evidence = _retrieve_axis_evidence(documents, query_plan, axis)
    with trace_step(
        f"axis_{axis.get('key')}_judge",
        input_size=len(evidence),
        meta={"label": axis.get("label")},
    ) as step:
        judge = judge_evidence_quality(
            question,
            evidence,
            keywords=[*(query_plan.get("keywords") or []), *axis.get("seed_terms", [])],
        )
        step["outputSize"] = len(judge.get("missingAspects") or [])

    if _should_retry_retrieval(judge):
        retry_query = _build_retry_query(question, query_plan, axis, judge)
        retry_plan = {
            **query_plan,
            "rewritten": retry_query,
            "keywords": [*(query_plan.get("keywords") or []), *(judge.get("missingAspects") or [])],
        }
        with trace_step(
            f"axis_{axis.get('key')}_retry",
            input_size=len(str(retry_query or "")),
            meta={"missingAspects": judge.get("missingAspects") or []},
        ):
            retry_evidence = _retrieve_axis_evidence(documents, retry_plan, axis)
        if retry_evidence:
            evidence = _merge_evidence_lists(evidence, retry_evidence, limit=6)
        with trace_step(
            f"axis_{axis.get('key')}_judge_retry",
            input_size=len(evidence),
            meta={"label": axis.get("label")},
        ) as step:
            judge = judge_evidence_quality(
                question,
                evidence,
                keywords=[*(retry_plan.get("keywords") or []), *axis.get("seed_terms", [])],
            )
            step["outputSize"] = len(judge.get("missingAspects") or [])
        query_plan = {
            **retry_plan,
            "source": query_plan.get("source"),
        }

    return {
        "key": axis["key"],
        "label": axis["label"],
        "question": question,
        "queryPlan": query_plan,
        "judge": judge,
        "evidence": evidence,
    }


def _format_axis_prompt_block(axis_result: Dict[str, Any]) -> str:
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


def _normalize_list_items(value: Any, fallback: List[str]) -> List[str]:
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


def _normalize_text_value(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").strip().split())
    return text or fallback


def _axis_result_map(axis_results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item["key"]: item for item in axis_results}


def _fallback_claimed_contributions(axis_results: List[Dict[str, Any]]) -> str:
    contributions = _axis_result_map(axis_results).get("contributions", {})
    evidence = contributions.get("evidence") or []
    if not evidence:
        return "当前证据不足，无法稳定提炼作者显式宣称的贡献。"

    lines = ["根据当前论文证据，作者可能宣称的贡献包括："]
    for item in evidence[:3]:
        lines.append(f"- {str(item.get('text') or '')[:120]}")
    return "\n".join(lines)


def _fallback_evidence_based_contributions(axis_results: List[Dict[str, Any]]) -> str:
    axis_map = _axis_result_map(axis_results)
    evidence = _merge_evidence_lists(
        axis_map.get("contributions", {}).get("evidence") or [],
        axis_map.get("methods", {}).get("evidence") or [],
        axis_map.get("experiments", {}).get("evidence") or [],
        limit=4,
    )
    if not evidence:
        return "当前证据不足，尚无法确认哪些贡献真正被方法和实验稳定支撑。"

    lines = ["从当前证据看，较可能成立的真实贡献包括："]
    for item in evidence[:3]:
        lines.append(f"- {str(item.get('text') or '')[:120]}")
    return "\n".join(lines)


def _fallback_weaknesses(axis_results: List[Dict[str, Any]]) -> List[str]:
    axis_map = _axis_result_map(axis_results)
    weaknesses = []
    if (axis_map.get("methods", {}).get("judge") or {}).get("verdict") != "CORRECT":
        weaknesses.append("方法细节证据不足，关键设计是否必要仍需进一步核对。")
    if (axis_map.get("experiments", {}).get("judge") or {}).get("verdict") != "CORRECT":
        weaknesses.append("实验与结果证据覆盖不足，结论支撑力度仍然有限。")
    if (axis_map.get("limitations", {}).get("judge") or {}).get("verdict") != "CORRECT":
        weaknesses.append("局限性或失败情形披露不充分，风险边界不够清晰。")
    return weaknesses


def _fallback_overclaim_risks(axis_results: List[Dict[str, Any]]) -> List[str]:
    axis_map = _axis_result_map(axis_results)
    risks = []
    if (axis_map.get("contributions", {}).get("judge") or {}).get("verdict") != "CORRECT":
        risks.append("作者主张的贡献点本身证据覆盖不足，存在表述过强的风险。")
    if (axis_map.get("contributions", {}).get("judge") or {}).get("verdict") == "CORRECT" and (
        axis_map.get("experiments", {}).get("judge") or {}
    ).get("verdict") != "CORRECT":
        risks.append("论文的贡献表述可能超出当前实验或对比证据能够直接支撑的范围。")
    if (axis_map.get("methods", {}).get("judge") or {}).get("verdict") != "CORRECT":
        risks.append("部分方法创新点缺少足够机制性证据，可能存在贡献重包装风险。")
    return risks


def _fallback_missing_evidence(axis_results: List[Dict[str, Any]]) -> List[str]:
    missing = []
    seen = set()
    for axis_result in axis_results:
        judge = axis_result.get("judge") or {}
        if judge.get("verdict") == "CORRECT":
            continue
        aspects = judge.get("missingAspects") or []
        text = f"{axis_result.get('label')}：{'、'.join(str(item) for item in aspects[:3])}" if aspects else f"{axis_result.get('label')}：相关证据不足"
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        missing.append(text[:160])
    return missing


from services.critical_reading import (
    _attach_numeric_evidence_to_claims,
    _build_claim_support_items,
    _build_contribution_assessment,
    _collect_response_sources,
    _generate_structured_critical_report,
)

def deep_analysis(request: DeepAnalysisRequest) -> Dict[str, Any]:
    trace_id = start_trace(
        "critical",
        request_meta={
            "pdfId": sanitize_text(request.pdf_id, max_chars=80),
            "hasInlineContent": bool(request.paper_content),
        },
    )
    try:
        documents, resolved_from, normalized_id, paper_content = _load_analysis_source(request)
        analysis_context = _build_analysis_context(documents)
        axis_results = [
            _analyze_axis(axis_config, documents, analysis_context or paper_content[:2400])
            for axis_config in ANALYSIS_AXIS_CONFIGS
        ]
        report = _generate_structured_critical_report(axis_results, analysis_context or paper_content[:2400], resolved_from)
        claims = _build_claim_support_items(report, axis_results, use_llm=True)
        assessment = _build_contribution_assessment(report, claims, axis_results)
        response_sources = _collect_response_sources(axis_results)
        rag_sources = compact_evidence_for_response(
            response_sources,
            max_items=ANALYSIS_RESPONSE_SOURCE_LIMIT,
            max_text_chars=700,
        )
        numeric_evidence_summary = _attach_numeric_evidence_to_claims(claims, rag_sources)
        sentence_source_fields = {
            "claimed_contributions": report["claimed_contributions"],
            "evidence_based_contributions": report["evidence_based_contributions"],
            "weaknesses": report["weaknesses"],
            "overclaim_risks": report["overclaim_risks"],
            "missing_evidence": report["missing_evidence"],
            "critical_analysis": report["critical_analysis"],
            "contributionScore": assessment["contributionScore"]["summary"],
            "riskScore": assessment["riskScore"]["summary"],
            "noveltyDimensions": [dimension["detail"] for dimension in assessment["noveltyDimensions"]],
        }
        for claim in claims:
            sentence_source_fields[f"claims.{claim['id']}"] = claim.get("claim", "")

        response = {
            "status": "success",
            "claimed_contributions": report["claimed_contributions"],
            "evidence_based_contributions": report["evidence_based_contributions"],
            "inferred_real_contributions": report["inferred_real_contributions"],
            "weaknesses": report["weaknesses"],
            "overclaim_risks": report["overclaim_risks"],
            "missing_evidence": report["missing_evidence"],
            "critical_analysis": report["critical_analysis"],
            "claims": claims,
            "contributionScore": assessment["contributionScore"],
            "riskScore": assessment["riskScore"],
            "noveltyDimensions": assessment["noveltyDimensions"],
            "numericEvidenceSummary": numeric_evidence_summary,
            "citationGraph": None,
            "rag_sources": rag_sources,
            "sentenceSourceMap": build_field_sentence_source_map(sentence_source_fields, rag_sources),
            "resolved_from": resolved_from,
            "pdf_id": normalized_id,
            "traceId": trace_id,
        }
        record_metric("axisCount", len(axis_results))
        record_metric("responseSources", len(response_sources))
        record_metric("numericEvidenceCandidates", numeric_evidence_summary["candidateCount"])
        finalize_trace(
            "success",
            response_meta={
                "resolvedFrom": resolved_from,
                "axisCount": len(axis_results),
                "responseSources": len(response_sources),
                **summarize_safety_results(
                    wrap_untrusted_context("Analysis source content", paper_content[:3200], max_tokens=1800),
                    wrap_untrusted_context("Analysis overview", analysis_context or paper_content[:2400], max_tokens=1400),
                ),
            },
        )
        return response
    except PaperNotIndexedError as error:
        error.trace_id = trace_id
        finalize_trace("error", error=error)
        raise
    except Exception as error:
        finalize_trace("error", error=error)
        raise
