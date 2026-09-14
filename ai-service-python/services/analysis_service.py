import os
import shutil
import tempfile
from typing import Any

from bs4 import BeautifulSoup
from fastapi import UploadFile

from core.pdf_quality import (
    PARSE_STATUS_SCANNED_OR_LOW_TEXT,
    _build_axis_terms,
    _build_low_text_upload_response,
    _build_parse_diagnostics,
    _build_section_outline,
    _count_non_whitespace_characters,
    _extract_authors,
    _extract_pdf_text_stats,
    _extract_title,
    _score_document,
    get_grobid_client,
)

try:
    from PyPDF2 import PdfReader
except ImportError:  # pragma: no cover - deployment dependency guard
    PdfReader = None

import logging

from core.document_parser import extract_translation_layout_index, parse_tei_xml
from core.outline_extractor import OUTLINE_VERSION, build_document_outline
from core.smart_chunker import normalize_section_titles
from llm.client import get_llm
from rag.store import get_rag, is_rag_available, normalize_id, retrieve_fused_evidence
from schemas.requests import BackgroundKnowledgeRequest, DeepAnalysisRequest
from services.background_knowledge_service import (
    get_background_knowledge as build_background_knowledge,
)

# critical_reading 不再反向导入本模块，所以这条边可以放在文件顶部。
# 以前它卡在第 970 行（所有定义之后）才能跑：那时 critical_reading 在顶部
# from services.analysis_service import ...，而本模块又在中途 from services.critical_reading
# import ...，两边互为前提，只能靠“先导 analysis_service”的导入顺序续命 ——
# 单独 import services.critical_reading 必报 ImportError(partially initialized)，
# 既无法单独跑它的单测，也让每个探测脚本都得先写一行无关的 import。
from services.critical_reading import (
    ANALYSIS_RESPONSE_SOURCE_LIMIT,
    _attach_numeric_evidence_to_claims,
    _build_claim_support_items,
    _build_contribution_assessment,
    _build_evidence_graph,
    _collect_response_sources,
    _generate_structured_critical_report,
)
from services.evidence_service import (
    _deduplicate_evidence,
    _merge_evidence_lists,
    build_field_sentence_source_map,
    compact_evidence_for_response,
    normalize_evidence_items,
)
from services.retrieval_judge_service import judge_evidence_quality
from services.safety_service import (
    MAX_RETRIEVAL_RETRIES,
    summarize_safety_results,
    wrap_untrusted_context,
)
from services.trace_service import (
    finalize_trace,
    record_counter,
    record_metric,
    sanitize_text,
    start_trace,
    trace_step,
)
from services.utils import parse_json_from_llm

_logger = logging.getLogger(__name__)

_grobid_client = None
ANALYSIS_CHUNK_SIZE = 1200
ANALYSIS_CHUNK_OVERLAP = 200
ANALYSIS_RETRIEVAL_LIMIT = 4
# 轴证据单条正文上限，与 _load_analysis_source 预加载 documents 时保持一致。
ANALYSIS_EVIDENCE_MAX_TEXT_CHARS = 1800
# 精读上下文预算。旧实现是 6 个关键词桶 × [:2500] 字符（约 3.75k token），
# 实测某篇论文只有 38.6% 的正文进入模型，被扔掉的 57.8% 里包含整个“提出方法”章节。
# DeepSeek 系长上下文模型，这里按 120k 字符（约 30k token）给足空间。
FULL_PAPER_CONTEXT_MAX_CHARS = 120_000
FULL_PAPER_SECTION_MAX_CHARS = 8_000
FULL_PAPER_SECTION_MIN_CHARS = 40
_TRIM_MARKER = "\n...[section trimmed]...\n"
PAPER_NOT_INDEXED_ERROR_CODE = "paper_not_indexed"
RAG_INDEX_UNAVAILABLE_ERROR_CODE = "rag_index_unavailable"
PAPER_NOT_INDEXED_MESSAGE = "当前论文尚未完成全文索引，请重新上传或重新解析后再试。"
RAG_INDEX_EMPTY_MESSAGE = "论文已解析，但没有可入库的正文片段，批判阅读暂不可用。请重新上传，或确认 PDF 是可提取文字的版本。"
RAG_INDEX_UNAVAILABLE_MESSAGE = "论文已解析，但全文索引服务暂不可用，批判阅读暂不可用。请稍后重新解析或重启 AI 服务后再试。"
ANALYSIS_AXIS_CONFIGS = (
    {
        "key": "contributions",
        "label": "贡献与创新",
        "question": "这篇论文显式宣称了哪些贡献、创新点或核心主张？",
        # 实际用于检索的英文问句，与 question 分开：question 面向用户与 LLM prompt，
        # retrieval_question 面向检索层。取值不是随手写的，见 _build_axis_query_plan。
        "retrieval_question": (
            "What contributions, innovations and core claims does this paper make?"
        ),
        "seed_terms": ["贡献", "创新", "主张", "贡献点", "claim", "contribution", "novelty"],
    },
    {
        "key": "methods",
        "label": "方法与机制",
        "question": "这篇论文的方法、模型设计或关键机制是什么？这些设计的直接证据是否清楚？",
        "retrieval_question": (
            "What is the method, model design and key mechanism, "
            "and what direct evidence supports it?"
        ),
        "seed_terms": ["方法", "模型", "机制", "模块", "流程", "method", "architecture", "framework"],
    },
    {
        "key": "experiments",
        "label": "实验与结果",
        "question": "这篇论文提供了哪些实验、指标、对比或结果来支撑结论？",
        "retrieval_question": (
            "What experiments, metrics, comparisons and results support the conclusions?"
        ),
        "seed_terms": ["实验", "结果", "指标", "评估", "对比", "ablation", "benchmark", "metric", "evaluation"],
    },
    {
        "key": "limitations",
        "label": "局限与风险",
        "question": "这篇论文提到了哪些局限、风险、失败情形或尚未验证的部分？",
        "retrieval_question": (
            "What limitations, risks, failure cases and unverified aspects are reported?"
        ),
        "seed_terms": ["局限", "不足", "风险", "失败", "future work", "limitation", "weakness", "risk"],
    },
)
VALID_SUPPORT_LEVELS = {"SUPPORTED", "PARTIAL", "UNSUPPORTED"}

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

    def to_response(self) -> dict[str, Any]:
        response: dict[str, Any] = {
            "status": "error",
            "errorCode": self.error_code,
            "message": self.message,
        }
        if self.pdf_id:
            response["pdfId"] = self.pdf_id
        if self.trace_id:
            response["traceId"] = self.trace_id
        return response


def _trim_section_text(text: str, limit: int) -> str:
    """按 6:4 保留章节首尾，避免只截开头导致小节结论被切掉。"""
    if limit <= 0 or len(text) <= limit:
        return text

    body_budget = max(0, limit - len(_TRIM_MARKER))
    head_budget = int(body_budget * 0.6)
    tail_budget = body_budget - head_budget
    if tail_budget <= 0:
        return text[:body_budget].rstrip()

    return f"{text[:head_budget].rstrip()}{_TRIM_MARKER}{text[-tail_budget:].lstrip()}"


def _build_full_paper_context(parsed_sections, abstract: str = "") -> str:
    """把论文全部正文章节拼成精读上下文，超预算时等比压缩而不是整节丢弃。"""
    blocks: list[tuple[str, str]] = []
    if abstract and abstract.strip():
        blocks.append(("ABSTRACT", abstract.strip()))

    for section in normalize_section_titles(parsed_sections):
        content = str(section.get("content") or "").strip()
        if len(content) < FULL_PAPER_SECTION_MIN_CHARS:
            continue
        title = str(section.get("section") or "").strip() or "Body Text"
        blocks.append((title, content))

    if not blocks:
        return ""

    total_chars = sum(len(content) for _, content in blocks)
    per_section_limit = FULL_PAPER_SECTION_MAX_CHARS
    if total_chars > FULL_PAPER_CONTEXT_MAX_CHARS:
        # 等比压缩每个章节的配额，保证每一节都还有内容进入模型
        per_section_limit = max(
            FULL_PAPER_SECTION_MIN_CHARS,
            int(FULL_PAPER_CONTEXT_MAX_CHARS / len(blocks)),
        )

    _logger.info(
        "精读上下文覆盖 %d 个章节，原文 %d 字符，单节配额 %d 字符。",
        len(blocks),
        total_chars,
        per_section_limit,
    )

    context = ""
    for title, content in blocks:
        context += f"### Section: {title}\nContent: {_trim_section_text(content, per_section_limit)}\n\n"
    return context


async def analyze_pdf(file: UploadFile) -> dict[str, Any]:
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

        # 精读上下文直接覆盖全部正文章节。
        # 旧实现先用关键词把章节分到 6 个桶（intro/method/result/discuss/conclu），
        # 匹配不上的整节丢弃，再对每个桶 [:2500] 硬截断；
        # 实测某篇论文只有 38.6% 的正文进入模型，被扔掉的包括
        # “C. Problem Formulation”、“D. Reflection Coefficients Optimization” 等整节贡献。
        # sections_for_summary 仅作为摘要 JSON 的键约定与空文本兜底分支使用。
        combined_context = _build_full_paper_context(
            parsed_sections,
            abstract=sections_for_summary["abstract"],
        )

        paper_structure: dict[str, Any] = {}
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

def get_background_knowledge(request: BackgroundKnowledgeRequest) -> dict[str, Any]:
    return build_background_knowledge(request)

def _chunk_text(text: str, chunk_size: int = ANALYSIS_CHUNK_SIZE, overlap: int = ANALYSIS_CHUNK_OVERLAP) -> list[str]:
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

def _build_inline_documents(paper_content: str) -> list[dict[str, Any]]:
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

def _load_analysis_source(request: DeepAnalysisRequest) -> tuple[list[dict[str, Any]], str, str | None, str]:
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

def _build_analysis_context(documents: list[dict[str, Any]], max_docs: int = 4, max_chars: int = 2400) -> str:
    parts = []
    for item in documents[:max_docs]:
        text = str(item.get("text") or "").strip()
        if text:
            parts.append(text[:600])
    return "\n\n".join(parts)[:max_chars]

def _build_axis_query(query_plan: dict[str, Any], axis: dict[str, Any]) -> str:
    """组轴检索查询：优先用规划器改写后的检索式，退回轴问题原文。

    刻意不把 keywords 全拼进去：向量检索要的是简洁自然查询，堆词会稀释语义；
    精确术语召回交给 BM25 那一路（HybridRetriever 内部已按论文分片建索引）。
    """
    for candidate in (query_plan.get("rewritten"), query_plan.get("original"), axis.get("question")):
        query = " ".join(str(candidate or "").split())
        if query:
            return query[:300]
    return ""


def _build_axis_query_plan(axis: dict[str, Any]) -> dict[str, Any]:
    """给批判分析的轴构造确定性检索计划，全程不调 LLM。

    这里原本调 build_retrieval_queries（LLM 改写），实测证明它是整条链路不可复现的
    入口：同一 prompt 在 temperature=0 下连打 4 次得到 3 种不同查询，关掉 thinking
    或把 reasoning_effort 降到 low 都一样 —— 温度为 0 只能让封闭式分类（证据判定，
    实测 3/3 一致）可复现，开放式生成本质上不可复现。轴查询在最上游，它一变证据就
    变，下游每个 prompt 跟着变，于是两次独立冷跑给出 5 vs 6 条主张、风险分 25 vs 18。

    换成固定英文问句不是退让，实测反而更好（2308.04079v1.pdf，top_k=8，四轴章节
    覆盖合计）：固定问句 31，LLM 改写最好 23、最差 20。两个原因：

    1. 检索本来就被 filter_metadata 限定在这一篇论文内，不需要 LLM 去“理解问题”；
       实测给查询加论文标题前缀还会拉低多样性（标题只稀释语义）。
    2. 问句是纯英文的，core.query_rewriter.rewrite_query 只在查询含 CJK 时才动 LLM，
       于是 HybridRetriever 内部那第二层翻译改写也不再触发，连带消掉第二个抖动源。

    keywords 直接用轴自带的 seed_terms（本来就是常量）。下游 _normalize_terms 与
    _build_axis_terms 都会去重，所以与调用点里已有的 seed_terms 拼接不会重复计分，
    query_plan 的字段形状也与 LLM 版逐键一致。
    """
    question = " ".join(str(axis.get("question") or "").split())
    retrieval_question = " ".join(str(axis.get("retrieval_question") or "").split())
    keywords = [
        " ".join(str(term or "").split())
        for term in (axis.get("seed_terms") or [])
        if " ".join(str(term or "").split())
    ]
    return {
        "original": question,
        "rewritten": retrieval_question or question,
        "keywords": keywords,
        "taskType": "critical",
        "source": "axis-fixed",
    }


def _retrieve_axis_evidence(
    documents: list[dict[str, Any]],
    query_plan: dict[str, Any],
    axis: dict[str, Any],
    limit: int = ANALYSIS_RETRIEVAL_LIMIT,
    pdf_id: str | None = None,
) -> list[dict[str, Any]]:
    """按轴取证据。

    有 pdf_id 时走真检索：HybridRetriever 的向量 + BM25 + 融合，按论文分片建索引，
    中文轴问题会被自动改写成英文，similarity 是真实余弦。

    旧实现在预加载的 documents 上做子串计数，similarity 由 0.42 + coverage*0.4 合成，
    既不反映语义相关性，也让“轴问题中文 × 论文英文”这个组合恒零命中：
    实测 3DGS(2308.04079v1) 那篇 5 条主张里 3 条被判 UNSUPPORTED，而支撑原句
    就在返回的 10 条证据里（chunk-2 写着 sparse points produced during camera
    calibration），支持等级实际由“主张里有没有英文专名”决定。

    内联 paper_content 路径从未入库、没有可检索的索引，保留词项匹配兜底。
    """
    query = _build_axis_query(query_plan, axis)
    with trace_step(
        f"axis_{axis.get('key')}_retrieve",
        input_size=len(documents),
        meta={
            "label": axis.get("label"),
            "scoped": bool(pdf_id),
            "query": sanitize_text(query, max_chars=120),
        },
    ) as step:
        if pdf_id and query:
            record_counter("retrievalCalls")
            retrieved = retrieve_fused_evidence(query, top_k=limit, filter_metadata={"id": pdf_id})
            evidence = normalize_evidence_items(
                retrieved,
                source_type="current_paper",
                pdf_id=pdf_id,
                limit=limit,
                max_text_chars=ANALYSIS_EVIDENCE_MAX_TEXT_CHARS,
            )
            step["outputSize"] = len(evidence)
            return evidence

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

            metadata = dict(item.get("metadata") or {})
            metadata["matched_terms"] = matched_terms[:8]
            scored_items.append({
                **item,
                "metadata": metadata,
                "score": round(score, 3),
            })

        scored_items.sort(key=lambda current: float(current.get("score") or 0), reverse=True)
        deduped = _deduplicate_evidence(scored_items, limit=limit)
        step["outputSize"] = len(deduped)
        return deduped

def _should_retry_retrieval(judge_result: dict[str, Any]) -> bool:
    return MAX_RETRIEVAL_RETRIES > 0 and bool(judge_result.get("shouldRetry")) and (
        judge_result.get("verdict") != "CORRECT" or float(judge_result.get("confidence") or 0) < 0.68
    )

def _build_retry_query(question: str, query_plan: dict[str, Any], axis: dict[str, Any], judge_result: dict[str, Any]) -> str:
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
    axis: dict[str, Any],
    documents: list[dict[str, Any]],
    pdf_id: str | None = None,
) -> dict[str, Any]:
    question = axis["question"]
    # 确定性构造，不再调 LLM（理由见 _build_axis_query_plan）。保留 trace step 是为了
    # 让“这一轴实际用了哪条检索式”可观测 —— 排查证据分布问题时必须看得见它。
    query_plan = _build_axis_query_plan(axis)
    with trace_step(
        f"axis_{axis.get('key')}_query_plan",
        input_size=len(str(query_plan.get("rewritten") or "")),
        meta={
            "label": axis.get("label"),
            "query": query_plan.get("rewritten"),
            "source": query_plan.get("source"),
        },
    ) as step:
        step["outputSize"] = len(query_plan.get("keywords") or [])
    evidence = _retrieve_axis_evidence(documents, query_plan, axis, pdf_id=pdf_id)
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
            retry_evidence = _retrieve_axis_evidence(documents, retry_plan, axis, pdf_id=pdf_id)
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

def deep_analysis(request: DeepAnalysisRequest) -> dict[str, Any]:
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
            _analyze_axis(
                axis_config,
                documents,
                pdf_id=normalized_id,
            )
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

        evidence_graph = _build_evidence_graph(claims, rag_sources)
        contribution_basis = assessment["contributionScore"]["basis"]

        response = {
            "status": "success",
            "claimed_contributions": report["claimed_contributions"],
            "evidence_based_contributions": report["evidence_based_contributions"],
            "weaknesses": report["weaknesses"],
            "overclaim_risks": report["overclaim_risks"],
            "missing_evidence": report["missing_evidence"],
            "critical_analysis": report["critical_analysis"],
            "claims": claims,
            "contributionScore": assessment["contributionScore"],
            "riskScore": assessment["riskScore"],
            "noveltyDimensions": assessment["noveltyDimensions"],
            "numericEvidenceSummary": numeric_evidence_summary,
            # citationGraph 继续给 None：真实引用网络需 Semantic Scholar，而本项目
            # 未配 API key（匿名请求实测 429），且项目约定无 key 时不启用该 provider。
            # 前端卡片叫“证据关系图”，它真正需要的是下面这个离线构造的主张—证据图。
            "citationGraph": None,
            "evidenceGraph": evidence_graph,
            "rag_sources": rag_sources,
            "sentenceSourceMap": build_field_sentence_source_map(sentence_source_fields, rag_sources),
            "resolved_from": resolved_from,
            "pdf_id": normalized_id,
            "traceId": trace_id,
        }
        record_metric("axisCount", len(axis_results))
        record_metric("responseSources", len(response_sources))
        record_metric("numericEvidenceCandidates", numeric_evidence_summary["candidateCount"])
        # 把本次结果的核心量写进 trace，让改前/改后能直接对比而不必重跑一次 160s。
        record_metric("claimCount", len(claims))
        record_metric("supportedClaims", contribution_basis["supportedClaims"])
        record_metric("unsupportedClaims", contribution_basis["unsupportedClaims"])
        record_metric("contributionScore", assessment["contributionScore"]["score"])
        record_metric("riskScore", assessment["riskScore"]["score"])
        record_metric("evidenceGraphNodes", len(evidence_graph["nodes"]) if evidence_graph else 0)
        record_metric("evidenceGraphLinks", len(evidence_graph["links"]) if evidence_graph else 0)
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
