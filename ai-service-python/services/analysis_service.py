import os
import shutil
import tempfile
from typing import Any, Dict

from bs4 import BeautifulSoup
from fastapi import UploadFile

from core.document_parser import parse_tei_xml
from llm.client import get_llm
from rag.store import get_rag, preload_rag
from schemas.requests import BackgroundKnowledgeRequest, DeepAnalysisRequest
from services.math_markdown import MATH_MARKDOWN_GUIDELINE
from services.utils import parse_json_from_llm


_grobid_client = None


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
    print("Starting AI service warmup...")
    try:
        preload_rag()
        print("RAG backend is ready.")
    except Exception as error:
        print(f"RAG warmup skipped: {error}")


def _extract_title(parsed_sections: list[dict], fallback_name: str) -> str:
    if parsed_sections and parsed_sections[0].get("section") == "Front Matter (Metadata)":
        for line in parsed_sections[0].get("content", "").splitlines():
            if line.startswith("Title:"):
                title = line.replace("Title:", "", 1).strip()
                if title:
                    return title
    return fallback_name


async def analyze_pdf(file: UploadFile) -> Dict[str, Any]:
    input_dir = tempfile.mkdtemp()
    output_dir = tempfile.mkdtemp()

    try:
        file_path = os.path.join(input_dir, "target_paper.pdf")
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        get_grobid_client().process(
            "processFulltextDocument",
            input_path=input_dir,
            output=output_dir,
            consolidate_citations=False,
            tei_coordinates=True,
        )

        xml_files = [name for name in os.listdir(output_dir) if name.endswith(".tei.xml")]
        if not xml_files:
            raise RuntimeError("GROBID did not produce a TEI XML file.")

        tei_file = os.path.join(output_dir, xml_files[0])
        parsed_sections = parse_tei_xml(tei_file)

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
            except Exception as error:
                print(f"paper_structure generation failed: {error}")
                paper_structure = {
                    "error": "structure_parse_failed",
                    "raw": str(error)[:500],
                }
        else:
            section_summaries = {
                key: "未能从论文中提取足够文本，请确认 PDF 是否为可解析的文字版。"
                for key in sections_for_summary
            }
            paper_structure = {
                "error": "no_content",
                "raw": "No usable text was extracted from the paper.",
            }

        clean_pdf_id = get_rag().normalize_id(file.filename)
        title = _extract_title(parsed_sections, file.filename)
        rag_indexed = True
        rag_message = None
        try:
            count = get_rag().add_sections_to_db(
                parsed_sections,
                file_path,
                {"id": clean_pdf_id, "title": title},
            )
            print(f"Indexed paper {title} ({clean_pdf_id}) into RAG with {count} chunks.")
        except Exception as error:
            print(f"RAG indexing failed: {error}")
            rag_indexed = False
            rag_message = f"Paper parsed successfully, but RAG indexing failed: {error}"

        response = {
            "status": "success",
            "paper_skeleton": section_summaries,
            "paper_structure": paper_structure,
            "pdfId": clean_pdf_id,
            "ragIndexed": rag_indexed,
        }
        if rag_message:
            response["message"] = rag_message
        return response
    finally:
        if os.path.exists(input_dir):
            shutil.rmtree(input_dir)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)


def get_background_knowledge(request: BackgroundKnowledgeRequest) -> Dict[str, Any]:
    prompt = f"""
Recommend prerequisite knowledge for reading a paper.

Paper topic: {request.paper_topic}
User knowledge level: {request.user_knowledge_level}

Return a short ordered list, one item per line.
"""

    background_knowledge = get_llm()._call(prompt)

    return {
        "status": "success",
        "paper_topic": request.paper_topic,
        "user_knowledge_level": request.user_knowledge_level,
        "background_knowledge": [item.strip() for item in background_knowledge.splitlines() if item.strip()],
    }


def resolve_paper_content(request: DeepAnalysisRequest) -> tuple[str, str, str | None]:
    if request.paper_content and request.paper_content.strip():
        return request.paper_content, "paper_content", None

    if request.pdf_id:
        normalized_id = get_rag().normalize_id(request.pdf_id)
        documents = get_rag().get_documents_by_metadata({"id": normalized_id})
        if not documents:
            raise ValueError(f"No indexed paper content found for pdf_id={normalized_id}")

        paper_content = "\n\n".join(item["text"] for item in documents)
        return paper_content, "pdf_id", normalized_id

    raise ValueError("Either paper_content or pdf_id is required.")


def deep_analysis(request: DeepAnalysisRequest) -> Dict[str, Any]:
    paper_content, resolved_from, normalized_id = resolve_paper_content(request)
    math_markdown_guideline = MATH_MARKDOWN_GUIDELINE

    step1_prompt = f"""
从论文内容中提取作者显式宣称的贡献点，请用列表形式回答。
{math_markdown_guideline}

论文内容：
{paper_content[:4000]}
"""
    claimed = get_llm()._call(step1_prompt)

    step2_prompt = f"""
忽略作者自述，根据方法和实验内容推断论文真正成立的贡献。
{math_markdown_guideline}

论文内容：
{paper_content[:4000]}
"""
    real = get_llm()._call(step2_prompt)

    step3_prompt = f"""
对比下面两部分内容，并给出批判性阅读结论：

作者宣称的贡献：
{claimed}

推断出的真实贡献：
{real}

请重点指出：
1. 是否存在夸大
2. 是否存在伪创新或贡献重包装
3. 哪些论证链路仍然薄弱
{math_markdown_guideline}
"""
    critique = get_llm()._call(step3_prompt)

    return {
        "status": "success",
        "claimed_contributions": claimed,
        "inferred_real_contributions": real,
        "critical_analysis": critique,
        "resolved_from": resolved_from,
        "pdf_id": normalized_id,
    }
