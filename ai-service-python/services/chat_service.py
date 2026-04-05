import json
import re
from typing import Any, Dict, List

from llm.client import get_llm
from rag.store import get_rag, retrieve_hybrid_for_vector
from schemas.requests import (
    ChatRequest,
    SocraticQuestionRequest,
    SocraticSessionAnswerRequest,
    SocraticSessionStartRequest,
    TermExplainRequest,
)


SOCRATIC_TOTAL_QUESTIONS = 5
SOCRATIC_MASTERY_LEVELS = ("需加强", "一般", "较好")


def _stringify_paper_skeleton(paper_skeleton: Dict[str, Any] | None) -> str:
    if not paper_skeleton:
        return "暂无可用的论文结构摘要。"

    lines = []
    for section, summary in paper_skeleton.items():
        lines.append(f"- {section}: {summary}")
    return "\n".join(lines)


def _build_pdf_context(pdf_id: str | None, query: str, top_k: int = 4) -> str:
    if not pdf_id:
        return ""

    try:
        clean_pdf_id = get_rag().normalize_id(pdf_id)
        rag_results = get_rag().retrieve(query, top_k=top_k, filter_metadata={"id": clean_pdf_id})
    except Exception as error:
        print(f"Socratic PDF retrieval failed: {error}")
        return ""

    if not rag_results:
        return ""

    lines = ["\n论文证据片段："]
    for item in rag_results:
        lines.append(f"- {item.get('text', '')[:500]}")
    return "\n".join(lines)


def _build_literature_context(query: str, top_k: int = 3) -> str:
    rag_results = retrieve_hybrid_for_vector(query, top_k=top_k)
    if not rag_results:
        return ""

    lines = ["\n相关文献线索："]
    for item in rag_results:
        lines.append(f"- {item.get('text', '')[:400]}")
    return "\n".join(lines)


def _extract_json_payload(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _call_json_llm(prompt: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        raw_text = get_llm()._call(prompt)
        return _extract_json_payload(raw_text)
    except Exception as error:
        print(f"Structured Socratic generation failed: {error}")
        return fallback


def _normalize_mastery_level(level: Any) -> str:
    text = str(level or "").strip()
    if text in SOCRATIC_MASTERY_LEVELS:
        return text
    if any(keyword in text for keyword in ("较好", "扎实", "准确", "清晰", "深入")):
        return "较好"
    if any(keyword in text for keyword in ("需加强", "薄弱", "不足", "偏弱", "错误")):
        return "需加强"
    return "一般"


def _default_intro(reading_progress: str) -> str:
    return (
        f"我会根据你当前的阅读进度“{reading_progress}”来逐步提问。"
        "你先用自己的话作答，我会判断你的掌握程度，再决定下一步如何引导你。"
    )


def _fallback_question(index: int) -> str:
    fallback_questions = {
        1: "请先用你自己的话概括：这篇论文想解决什么问题，为什么这个问题值得研究？",
        2: "作者提出的方法或模型核心思路是什么？它和已有做法相比，最关键的变化在哪里？",
        3: "这篇论文的方法是如何一步步发挥作用的？请你结合关键模块或流程解释一下。",
        4: "作者用了哪些实验或证据来支撑自己的结论？这些证据是否足够有说服力？",
        5: "如果你来继续这项研究，这篇论文还有哪些局限、风险或可以改进的地方？",
    }
    return fallback_questions.get(index, fallback_questions[SOCRATIC_TOTAL_QUESTIONS])


def _fallback_evaluation(answer: str) -> Dict[str, str]:
    answer_length = len((answer or "").strip())
    if answer_length < 40:
        return {
            "masteryLevel": "需加强",
            "feedback": "你的回答还比较简略，说明目前对这一点的理解还不够稳定。",
            "hint": "可以补充这项工作的研究目标、关键术语以及作者为什么这样设计。",
        }
    if answer_length < 120:
        return {
            "masteryLevel": "一般",
            "feedback": "你已经抓到了一部分重点，但论证链条和关键细节还可以更完整。",
            "hint": "尝试把“问题是什么、方法怎么做、证据是否支持结论”连成一条完整逻辑链。",
        }
    return {
        "masteryLevel": "较好",
        "feedback": "你的回答已经比较完整，说明你对这一部分的理解较为扎实。",
        "hint": "接下来可以继续关注方法细节、证据强度，以及论文可能的局限性。",
    }


def _format_turns(turns: List[Dict[str, Any]]) -> str:
    if not turns:
        return "暂无历史轮次。"

    lines = []
    for turn in turns:
        lines.append(
            f"第{turn.get('index', '?')}题\n"
            f"问题：{turn.get('question', '')}\n"
            f"用户回答：{turn.get('answer', '')}\n"
            f"掌握度：{turn.get('masteryLevel', '未评估')}\n"
            f"反馈：{turn.get('feedback', '')}\n"
            f"提示：{turn.get('hint', '')}"
        )
    return "\n\n".join(lines)


def _fallback_final_summary(turns: List[Dict[str, Any]]) -> str:
    if not turns:
        return "本轮引导学习已完成。你已经开始梳理论文的问题、方法、证据与局限，建议再结合原文细读关键方法与实验部分。"

    mastery_counts = {level: 0 for level in SOCRATIC_MASTERY_LEVELS}
    for turn in turns:
        mastery_counts[_normalize_mastery_level(turn.get("masteryLevel"))] += 1

    strongest_turn = max(turns, key=lambda item: len(str(item.get("answer", "")).strip()))
    weakest_turn = min(turns, key=lambda item: len(str(item.get("answer", "")).strip()))

    return (
        "本轮引导学习已完成。"
        f"整体来看，你的回答中“较好”有 {mastery_counts['较好']} 题，“一般”有 {mastery_counts['一般']} 题，“需加强”有 {mastery_counts['需加强']} 题。"
        f"你相对表达最充分的部分是第 {strongest_turn.get('index', '?')} 题，"
        f"而第 {weakest_turn.get('index', '?')} 题还可以继续补强。"
        "建议你回到论文原文，重点对照方法设计动机、实验论证链条和局限性讨论，再进行第二轮复盘。"
    )


def start_socratic_session(request: SocraticSessionStartRequest) -> Dict[str, Any]:
    reading_progress = (request.readingProgress or "").strip()
    if not reading_progress:
        raise ValueError("Reading progress cannot be empty.")

    paper_skeleton = request.paperSkeleton or {}
    skeleton_text = _stringify_paper_skeleton(paper_skeleton)
    paper_context = _build_pdf_context(request.pdfId, "论文研究问题 核心方法 主要结论")
    literature_context = _build_literature_context(
        f"为论文设计第一道苏格拉底式引导问题。阅读进度：{reading_progress}"
    )

    fallback = {
        "intro": _default_intro(reading_progress),
        "currentQuestion": _fallback_question(1),
    }
    prompt = f"""
你是一位擅长苏格拉底式提问的中文学术导师。你要开启一轮固定 5 题的引导式学习，但当前只生成开场引导和第 1 题。

要求：
1. 根据论文结构和阅读进度决定第一问。
2. 第一问要开放式，优先检查用户是否真正理解论文要解决的问题与研究价值。
3. 不要直接给答案，不要列出后续题目。
4. 输出严格 JSON，不要输出任何额外解释。

JSON 格式：
{{
  "intro": "1-2句中文引导语",
  "currentQuestion": "当前要问给用户的第一题"
}}

论文结构摘要：
{skeleton_text}

当前阅读进度：
{reading_progress}
{paper_context}
{literature_context}
"""
    payload = _call_json_llm(prompt, fallback)
    intro = str(payload.get("intro") or fallback["intro"]).strip()
    current_question = str(payload.get("currentQuestion") or fallback["currentQuestion"]).strip()

    return {
        "status": "success",
        "intro": intro,
        "totalQuestions": SOCRATIC_TOTAL_QUESTIONS,
        "currentIndex": 1,
        "currentQuestion": current_question,
    }


def answer_socratic_question(request: SocraticSessionAnswerRequest) -> Dict[str, Any]:
    current_question = (request.currentQuestion or "").strip()
    user_answer = (request.userAnswer or "").strip()
    reading_progress = (request.readingProgress or "").strip()

    if not current_question:
        raise ValueError("Current question cannot be empty.")
    if not user_answer:
        raise ValueError("User answer cannot be empty.")

    current_index = max(1, min(int(request.currentIndex or 1), SOCRATIC_TOTAL_QUESTIONS))
    paper_skeleton = request.paperSkeleton or {}
    completed_turns = [turn.model_dump() for turn in (request.turns or [])]
    skeleton_text = _stringify_paper_skeleton(paper_skeleton)
    turns_text = _format_turns(completed_turns)
    paper_context = _build_pdf_context(request.pdfId, f"{current_question}\n{user_answer}")
    literature_context = _build_literature_context(
        f"评估用户对论文的理解并生成下一问。当前问题：{current_question}。用户回答：{user_answer}"
    )
    is_final_question = current_index >= SOCRATIC_TOTAL_QUESTIONS
    terminal_field_prompt = '"finalSummary": "最终总结"' if is_final_question else '"nextQuestion": "下一题"'

    fallback_evaluation = _fallback_evaluation(user_answer)
    fallback_payload: Dict[str, Any] = {
        **fallback_evaluation,
        "nextQuestion": _fallback_question(current_index + 1),
    }
    if is_final_question:
        current_turn = {
            "index": current_index,
            "question": current_question,
            "answer": user_answer,
            **fallback_evaluation,
        }
        fallback_payload["finalSummary"] = _fallback_final_summary([*completed_turns, current_turn])

    prompt = f"""
你是一位中文学术导师，正在进行固定 5 轮的苏格拉底式引导学习。
你的任务是：根据当前问题与用户回答，判断用户掌握程度，给出简短反馈和提示，并决定下一步。

严格要求：
1. masteryLevel 只能是“需加强”“一般”“较好”三者之一。
2. feedback 用 1-2 句中文指出用户理解得怎样，重点哪里还薄弱或哪里已经比较到位。
3. hint 用 1 句中文提示用户下一步该如何思考。
4. 如果当前不是最后一题，生成 nextQuestion；如果已经是第 5 题，则生成 finalSummary。
5. nextQuestion 必须基于用户当前暴露的薄弱点推进，而不是简单重复上一个问题。
6. 输出严格 JSON，不要输出任何额外解释。

当前是第 {current_index} / {SOCRATIC_TOTAL_QUESTIONS} 题。

JSON 格式：
{{
  "masteryLevel": "需加强|一般|较好",
  "feedback": "简短评语",
  "hint": "下一步提示",
  {terminal_field_prompt}
}}

论文结构摘要：
{skeleton_text}

当前阅读进度：
{reading_progress or "未提供"}

历史轮次：
{turns_text}

当前问题：
{current_question}

用户当前回答：
{user_answer}
{paper_context}
{literature_context}
"""
    payload = _call_json_llm(prompt, fallback_payload)

    evaluation = {
        "masteryLevel": _normalize_mastery_level(payload.get("masteryLevel")),
        "feedback": str(payload.get("feedback") or fallback_evaluation["feedback"]).strip(),
        "hint": str(payload.get("hint") or fallback_evaluation["hint"]).strip(),
    }

    if is_final_question:
        final_summary = str(payload.get("finalSummary") or fallback_payload["finalSummary"]).strip()
        return {
            "status": "success",
            "evaluation": evaluation,
            "finalSummary": final_summary,
            "isComplete": True,
        }

    next_index = current_index + 1
    next_question = str(payload.get("nextQuestion") or fallback_payload["nextQuestion"]).strip()
    return {
        "status": "success",
        "evaluation": evaluation,
        "nextQuestion": next_question,
        "nextIndex": next_index,
        "isComplete": False,
    }


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

    prompt = f"""你是一位学术论文阅读助手。
请结合论文摘要结构、相关证据片段和对话历史，用中文回答用户问题。

{skeleton_str}

{context}

对话历史：
{history_str}
用户：{message}
助手："""

    reply = get_llm()._call(prompt)
    return {"status": "success", "message": reply or ""}
