from typing import Any, Dict

from llm.client import get_llm
from rag.store import get_rag, retrieve_hybrid_for_vector
from schemas.requests import ChatRequest, SocraticQuestionRequest, TermExplainRequest


def generate_socratic_questions(request: SocraticQuestionRequest) -> Dict[str, Any]:
    rag_query = (
        f"Generate Socratic questions for a paper. "
        f"Reading progress: {request.reading_progress}. "
        f"Paper content: {request.paper_content[:300]}"
    )
    rag_results = retrieve_hybrid_for_vector(rag_query, top_k=3)

    rag_context = "\n\nAdditional literature context:\n"
    for result in rag_results:
        rag_context += f"- {result.get('text', '')[:400]}\n"

    prompt = f"""
You are an academic mentor.
Generate 5 Socratic questions in Chinese based on the paper content, reading progress, and optional related literature.

Paper content:
{request.paper_content}

Reading progress:
{request.reading_progress}

{rag_context}
"""
    questions_text = get_llm()._call(prompt)

    return {
        "status": "success",
        "questions": [item.strip() for item in questions_text.splitlines() if item.strip()],
        "rag_sources": rag_results,
    }


def explain_term(request: TermExplainRequest) -> Dict[str, Any]:
    rag_query = f"Explain the term '{request.term}' with the following context: {request.context[:200]}"

    rewrite_prompt = f"""
You are helping a research retrieval system.
Rewrite the following question into a concise academic search query.

Question:
{rag_query}
"""

    try:
        rewritten_query = get_llm()._call(rewrite_prompt).strip()
    except Exception:
        rewritten_query = rag_query

    rag_results = retrieve_hybrid_for_vector(rewritten_query, top_k=3)
    rag_context = ""
    if rag_results:
        rag_context = "\n\nAdditional literature context:\n"
        for result in rag_results:
            rag_context += f"- {result.get('text', '')[:600]}\n"

    prompt = f"""
You are an academic research assistant.
Explain the technical term "{request.term}" in Chinese using the provided context.

Paper context:
{request.context}

Additional literature:
{rag_context}

Keep the answer within 5 sentences.
"""
    explanation = get_llm()._call(prompt)

    return {
        "status": "success",
        "term": request.term,
        "explanation": explanation,
        "rag_sources": rag_results,
    }


def chat(request: ChatRequest) -> Dict[str, Any]:
    message = request.message or ""
    if not message.strip():
        raise ValueError("Message cannot be empty.")

    history = request.history or []
    paper_skeleton = request.paperSkeleton or {}
    context = ""

    if request.pdfId:
        try:
            clean_pdf_id = get_rag().normalize_id(request.pdfId)
            rag_results = get_rag().retrieve(message, top_k=12, filter_metadata={"id": clean_pdf_id})
            if rag_results:
                context = "\n\nPaper evidence:\n" + "\n".join(f"- {item['text']}" for item in rag_results)
        except Exception as error:
            print(f"Chat RAG retrieval failed: {error}")

    history_str = ""
    for item in history[-5:]:
        role = item.get("role", "")
        role_name = "用户" if role == "user" else "助手"
        history_str += f"{role_name}: {item.get('content', '')}\n"

    skeleton_str = ""
    if paper_skeleton:
        skeleton_str = "\nPaper summary:\n"
        for section, summary in paper_skeleton.items():
            skeleton_str += f"- {section}: {summary}\n"

    prompt = f"""你是一个学术论文阅读助手。
请结合论文摘要结构、相关证据片段和对话历史，用中文回答用户问题。

{skeleton_str}

{context}

对话历史：
{history_str}
用户：{message}
助手："""

    reply = get_llm()._call(prompt)
    return {"status": "success", "message": reply or ""}
