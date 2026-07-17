"""Socratic guided-learning session service."""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List
from llm.client import get_llm
from rag.store import get_rag, retrieve_hybrid_for_vector
from schemas.requests import SocraticQuestionRequest, SocraticSessionStartRequest, SocraticSessionAnswerRequest
from services.evidence_service import format_evidence_context, normalize_evidence_items
from services.retrieval_judge_service import judge_evidence_quality
from services.safety_service import build_guarded_messages
from services.trace_service import record_counter, sanitize_text, trace_step
_logger = logging.getLogger(__name__)


# ── helpers (inlined from chat_service) ──

def _stringify_paper_skeleton(paper_skeleton: Dict[str, Any] | None) -> str:
    if not paper_skeleton:
        return "暂无可用的论文结构摘要。"

    lines = []
    for section, summary in paper_skeleton.items():
        lines.append(f"- {section}: {summary}")
    return "\n".join(lines)



def _call_guarded_llm(prompt: str, extra_system_instruction: str = "") -> str:
    return get_llm()._call(
        prompt,
        messages=build_guarded_messages(prompt, extra_system_instruction=extra_system_instruction),
    )



def _retrieve_current_paper_evidence(
    retrieval_query: str,
    pdf_id: str | None = None,
    current_top_k: int = 5,
    current_limit: int = 5,
) -> List[Dict[str, Any]]:
    if not pdf_id:
        return []

    try:
        with trace_step(
            "retrieve_current_paper",
            input_size=len(str(retrieval_query or "")),
            meta={"pdfId": sanitize_text(pdf_id, max_chars=80)},
        ) as step:
            record_counter("retrievalCalls")
            rag = get_rag()
            clean_pdf_id = rag.normalize_id(pdf_id)
            raw_results = rag.retrieve(retrieval_query, top_k=current_top_k, filter_metadata={"id": clean_pdf_id})
            normalized = normalize_evidence_items(
                raw_results,
                source_type="current_paper",
                pdf_id=clean_pdf_id,
                limit=current_limit,
            )
            step["outputSize"] = len(normalized)
            return normalized
    except Exception as error:
        _logger.error(f"PDF RAG retrieval failed: {error}")
        return []



# ── socratic session ──

def _get_socratic_topic(index: int) -> Dict[str, Any]:
    normalized_index = max(1, min(int(index or 1), SOCRATIC_TOTAL_QUESTIONS))
    return SOCRATIC_TOPIC_AXES.get(normalized_index, SOCRATIC_TOPIC_AXES[SOCRATIC_TOTAL_QUESTIONS])


def _normalize_socratic_match_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split())


def _normalize_socratic_strings(value: Any, limit: int = 5, max_chars: int = 32) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    elif value is None:
        raw_items = []
    else:
        raw_items = [value]

    normalized = []
    seen = set()
    for item in raw_items:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text[:max_chars])
        if len(normalized) >= limit:
            break

    return normalized


def _contains_socratic_terms(normalized_text: str, terms: List[str]) -> bool:
    for term in terms:
        normalized_term = _normalize_socratic_match_text(term)
        if normalized_term and normalized_term in normalized_text:
            return True
    return False


def _compact_socratic_evidence_quality(judge_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "verdict": str(judge_result.get("verdict") or "INCORRECT"),
        "confidence": float(judge_result.get("confidence") or 0),
        "reason": str(judge_result.get("reason") or "").strip(),
    }


def _format_socratic_evidence_quality(evidence_quality: Dict[str, Any]) -> str:
    verdict = str(evidence_quality.get("verdict") or "").upper()
    label = SOCRATIC_EVIDENCE_LABELS.get(verdict, "证据判断")
    confidence = evidence_quality.get("confidence")
    confidence_text = "未知"
    if isinstance(confidence, (int, float)):
        confidence_text = f"{float(confidence):.2f}"
    reason = str(evidence_quality.get("reason") or "暂无额外说明。").strip()
    return f"{label}（confidence={confidence_text}）：{reason}"


def _resolve_socratic_expected_aspects(
    topic: Dict[str, Any],
    evidence_items: List[Dict[str, Any]],
    paper_skeleton: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    source_text = "\n".join(
        [
            *(item.get("text", "") for item in evidence_items if item.get("text")),
            *(str(summary or "") for summary in (paper_skeleton or {}).values()),
        ]
    )
    normalized_source_text = _normalize_socratic_match_text(source_text)
    aspects = list(topic.get("aspects") or [])
    if not normalized_source_text:
        return aspects

    matched_aspects = []
    for aspect in aspects:
        aspect_terms = [str(aspect.get("name") or ""), *(aspect.get("terms") or [])]
        if _contains_socratic_terms(normalized_source_text, aspect_terms):
            matched_aspects.append(aspect)

    return matched_aspects or aspects


def _evaluate_socratic_answer_coverage(
    topic: Dict[str, Any],
    answer: str,
    evidence_items: List[Dict[str, Any]],
    paper_skeleton: Dict[str, Any] | None = None,
) -> tuple[List[str], List[str]]:
    expected_aspects = _resolve_socratic_expected_aspects(topic, evidence_items, paper_skeleton=paper_skeleton)
    normalized_answer = _normalize_socratic_match_text(answer)

    covered = []
    missing = []
    for aspect in expected_aspects:
        aspect_name = str(aspect.get("name") or "").strip()
        aspect_terms = [aspect_name, *(aspect.get("terms") or [])]
        if aspect_name and _contains_socratic_terms(normalized_answer, aspect_terms):
            covered.append(aspect_name)
        elif aspect_name:
            missing.append(aspect_name)

    return (
        _normalize_socratic_strings(covered, limit=5, max_chars=20),
        _normalize_socratic_strings(missing, limit=5, max_chars=20),
    )


def _build_socratic_evidence_bundle(
    topic: Dict[str, Any],
    pdf_id: str | None = None,
    paper_skeleton: Dict[str, Any] | None = None,
    question: str | None = None,
) -> Dict[str, Any]:
    evidence_items = _retrieve_current_paper_evidence(
        topic.get("retrievalQuery") or topic.get("defaultQuestion") or "",
        pdf_id=pdf_id,
        current_top_k=4,
        current_limit=4,
    )
    evidence_quality = _compact_socratic_evidence_quality(
        judge_evidence_quality(
            question or topic.get("defaultQuestion") or topic.get("label") or "",
            evidence_items,
            keywords=topic.get("keywords") or [],
        )
    )
    expected_aspects = _resolve_socratic_expected_aspects(topic, evidence_items, paper_skeleton=paper_skeleton)
    return {
        "items": evidence_items,
        "context": format_evidence_context(
            evidence_items,
            title=f"当前论文证据（{topic.get('label', 'Socratic')}）",
            max_items=4,
            max_text_chars=360,
        ),
        "evidenceQuality": evidence_quality,
        "expectedAspects": [str(item.get("name") or "").strip() for item in expected_aspects if item.get("name")],
    }


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
        _logger.error(f"Structured Socratic generation failed: {error}")
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
        f"我会根据你当前的阅读进度“{reading_progress}”来逐步提问，并尽量对照当前论文中的关键证据。"
        "你先用自己的话作答，我会判断你的掌握程度，再决定下一步如何引导你。"
    )


def _fallback_question(index: int, previous_missing_aspects: List[str] | None = None) -> str:
    topic = _get_socratic_topic(index)
    question = str(topic.get("defaultQuestion") or "").strip()
    missing_aspects = _normalize_socratic_strings(previous_missing_aspects, limit=2, max_chars=20)
    if not missing_aspects:
        return question

    return (
        f"{question} 作答时请顺手补上你上一题里还没有说清楚的"
        f"{'、'.join(missing_aspects)}。"
    )


def _fallback_evaluation(
    answer: str,
    missing_aspects: List[str] | None = None,
    evidence_quality: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    answer_length = len((answer or "").strip())
    normalized_missing = _normalize_socratic_strings(missing_aspects, limit=2, max_chars=20)
    missing_text = "、".join(normalized_missing) if normalized_missing else "关键概念和论证链条"
    evidence_verdict = str((evidence_quality or {}).get("verdict") or "").upper()

    if evidence_verdict == "INCORRECT":
        mastery_level = "需加强" if answer_length < 80 else "一般"
        return {
            "masteryLevel": mastery_level,
            "feedback": "当前论文里与这一题直接相关的证据还不够充分，暂时无法完整核对你的回答；从你现有的表述看，关键逻辑还可以更明确。",
            "hint": f"建议先回到原文核对 {missing_text}，再用论文中的具体表述或实验依据支撑你的回答。",
        }

    if evidence_verdict == "AMBIGUOUS":
        mastery_level = "需加强" if answer_length < 50 else "一般"
        return {
            "masteryLevel": mastery_level,
            "feedback": f"你已经抓到了一部分重点，但当前可用证据只部分覆盖这一题，尤其还缺少对 {missing_text} 的明确说明。",
            "hint": f"下一步可以补上 {missing_text}，并尽量把说法对齐到论文原文。",
        }

    if answer_length < 40:
        return {
            "masteryLevel": "需加强",
            "feedback": f"你的回答还比较简略，说明目前对这一点的理解还不够稳定，尤其是 {missing_text} 还没有说清楚。",
            "hint": f"可以补充 {missing_text}，并说明作者为什么这样设计。",
        }
    if answer_length < 120:
        return {
            "masteryLevel": "一般",
            "feedback": f"你已经抓到了一部分重点，但论证链条和关键细节还可以更完整，目前还缺少对 {missing_text} 的明确说明。",
            "hint": f"尝试把 {missing_text} 补进你的表述，并把“问题是什么、方法怎么做、证据是否支持结论”连成一条完整逻辑链。",
        }
    return {
        "masteryLevel": "较好",
        "feedback": "你的回答已经比较完整，说明你对这一部分的理解较为扎实。",
        "hint": f"接下来可以继续关注 {missing_text}，以及论文可能的局限性。",
    }


def _format_turns(turns: List[Dict[str, Any]]) -> str:
    if not turns:
        return "暂无历史轮次。"

    lines = []
    for turn in turns:
        evidence_quality = turn.get("evidenceQuality") if isinstance(turn.get("evidenceQuality"), dict) else {}
        covered_aspects = _normalize_socratic_strings(turn.get("coveredAspects"), limit=4, max_chars=20)
        missing_aspects = _normalize_socratic_strings(turn.get("missingAspects"), limit=4, max_chars=20)
        lines.append(
            f"第{turn.get('index', '?')}题\n"
            f"问题：{turn.get('question', '')}\n"
            f"用户回答：{turn.get('answer', '')}\n"
            f"掌握度：{turn.get('masteryLevel', '未评估')}\n"
            f"反馈：{turn.get('feedback', '')}\n"
            f"提示：{turn.get('hint', '')}\n"
            f"证据判断：{_format_socratic_evidence_quality(evidence_quality) if evidence_quality else '未提供'}\n"
            f"已覆盖要点：{'、'.join(covered_aspects) if covered_aspects else '暂无'}\n"
            f"仍需补强：{'、'.join(missing_aspects) if missing_aspects else '暂无'}"
        )
    return "\n\n".join(lines)


def _resolve_socratic_section_name(
    paper_skeleton: Dict[str, Any] | None,
    preferred_sections: List[str],
    fallback_label: str,
) -> str:
    if not paper_skeleton:
        return fallback_label

    normalized_sections = {
        _normalize_socratic_match_text(section_name): str(section_name)
        for section_name in paper_skeleton.keys()
    }
    for preferred in preferred_sections:
        for alias in SOCRATIC_SECTION_ALIASES.get(preferred, [preferred]):
            normalized_alias = _normalize_socratic_match_text(alias)
            for normalized_section, section_name in normalized_sections.items():
                if normalized_alias and normalized_alias in normalized_section:
                    return section_name

    return fallback_label


def _build_review_suggestions(
    turns: List[Dict[str, Any]],
    paper_skeleton: Dict[str, Any] | None = None,
    max_items: int = 3,
) -> List[str]:
    if not turns:
        return []

    def sort_key(turn: Dict[str, Any]) -> tuple[int, int, int, int]:
        evidence_quality = turn.get("evidenceQuality") if isinstance(turn.get("evidenceQuality"), dict) else {}
        verdict = str(evidence_quality.get("verdict") or "").upper()
        evidence_rank = 0 if verdict == "INCORRECT" else 1 if verdict == "AMBIGUOUS" else 2
        mastery_rank = {"需加强": 0, "一般": 1, "较好": 2}.get(_normalize_mastery_level(turn.get("masteryLevel")), 1)
        missing_count = len(_normalize_socratic_strings(turn.get("missingAspects"), limit=4, max_chars=20))
        return (evidence_rank, mastery_rank, -missing_count, int(turn.get("index") or 0))

    suggestions = []
    seen = set()
    for turn in sorted(turns, key=sort_key):
        topic = _get_socratic_topic(int(turn.get("index") or 1))
        section_name = _resolve_socratic_section_name(
            paper_skeleton,
            topic.get("reviewSections") or [],
            str(topic.get("reviewSectionLabel") or "原文相关部分"),
        )
        focus_items = _normalize_socratic_strings(
            turn.get("missingAspects") or topic.get("keywords") or [],
            limit=2,
            max_chars=20,
        )
        focus_text = "、".join(focus_items) if focus_items else "关键证据点"
        evidence_quality = turn.get("evidenceQuality") if isinstance(turn.get("evidenceQuality"), dict) else {}
        if str(evidence_quality.get("verdict") or "").upper() == "INCORRECT":
            suggestion = f"建议回读“{section_name}”部分，重点核对 {focus_text}；当前这一题可用证据仍不足。"
        else:
            suggestion = f"建议回读“{section_name}”部分，重点对照 {focus_text}。"

        suggestion_key = suggestion.lower()
        if suggestion_key in seen:
            continue
        seen.add(suggestion_key)
        suggestions.append(suggestion)
        if len(suggestions) >= max_items:
            break

    return suggestions


def _fallback_final_summary(
    turns: List[Dict[str, Any]],
    review_suggestions: List[str] | None = None,
) -> str:
    if not turns:
        return "本轮引导学习已完成。你已经开始梳理论文的问题、方法、证据与局限，建议再结合原文细读关键方法与实验部分。"

    mastery_counts = {level: 0 for level in SOCRATIC_MASTERY_LEVELS}
    for turn in turns:
        mastery_counts[_normalize_mastery_level(turn.get("masteryLevel"))] += 1

    strongest_turn = max(turns, key=lambda item: len(str(item.get("answer", "")).strip()))
    weakest_turn = min(turns, key=lambda item: len(str(item.get("answer", "")).strip()))
    insufficient_count = sum(
        1
        for turn in turns
        if str((turn.get("evidenceQuality") or {}).get("verdict") or "").upper() == "INCORRECT"
    )
    ambiguous_count = sum(
        1
        for turn in turns
        if str((turn.get("evidenceQuality") or {}).get("verdict") or "").upper() == "AMBIGUOUS"
    )

    summary = (
        "本轮引导学习已完成。"
        f"整体来看，你的回答中“较好”有 {mastery_counts['较好']} 题，“一般”有 {mastery_counts['一般']} 题，“需加强”有 {mastery_counts['需加强']} 题。"
        f"你相对表达最充分的部分是第 {strongest_turn.get('index', '?')} 题，"
        f"而第 {weakest_turn.get('index', '?')} 题还可以继续补强。"
    )
    if insufficient_count:
        summary += f" 另外有 {insufficient_count} 题当前论文证据不足，建议先回到原文核对再继续复盘。"
    elif ambiguous_count:
        summary += f" 其中有 {ambiguous_count} 题的证据只部分相关，还需要再对照原文补强。"

    if review_suggestions:
        summary += f" 你可以优先按以下方向回读：{'；'.join(review_suggestions[:2])}"

    return summary


def start_socratic_session(request: SocraticSessionStartRequest) -> Dict[str, Any]:
    reading_progress = (request.readingProgress or "").strip()
    if not reading_progress:
        raise ValueError("Reading progress cannot be empty.")

    paper_skeleton = request.paperSkeleton or {}
    skeleton_text = _stringify_paper_skeleton(paper_skeleton)
    current_topic = _get_socratic_topic(1)
    evidence_bundle = _build_socratic_evidence_bundle(
        current_topic,
        pdf_id=request.pdfId,
        paper_skeleton=paper_skeleton,
    )
    focus_text = "、".join(
        _normalize_socratic_strings(
            evidence_bundle.get("expectedAspects") or current_topic.get("keywords") or [],
            limit=3,
            max_chars=20,
        )
    )
    fallback = {
        "intro": _default_intro(reading_progress),
        "currentQuestion": _fallback_question(1),
    }
    prompt = f"""
你是一位擅长苏格拉底式提问的中文学术导师。你要开启一轮固定 5 题的引导式学习，但当前只生成开场引导和第 1 题。

要求：
1. 当前必须围绕“{current_topic.get('label', '研究问题与价值')}”出第 1 题，顺序不能跳题。
2. 第一问要开放式，优先检查用户是否真正理解论文要解决的问题与研究价值。
3. 尽量利用当前论文证据，但如果证据不足，只能据实提示，不得编造论文细节。
4. 不要直接给答案，不要列出后续题目。
5. 输出严格 JSON，不要输出任何额外解释。

JSON 格式：
{{
  "intro": "1-2句中文引导语",
  "currentQuestion": "当前要问给用户的第一题"
}}

论文结构摘要：
{skeleton_text}

当前阅读进度：
{reading_progress}

当前题轴：
{current_topic.get("label", "研究问题与价值")}

优先核对点：
{focus_text or "研究问题、研究动机、研究价值"}

当前论文证据判断：
{_format_socratic_evidence_quality(evidence_bundle.get("evidenceQuality") or {})}
{evidence_bundle.get("context") or ""}
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
    current_topic = _get_socratic_topic(current_index)
    next_topic = _get_socratic_topic(min(current_index + 1, SOCRATIC_TOTAL_QUESTIONS))
    evidence_bundle = _build_socratic_evidence_bundle(
        current_topic,
        pdf_id=request.pdfId,
        paper_skeleton=paper_skeleton,
        question=current_question,
    )
    covered_aspects, missing_aspects = _evaluate_socratic_answer_coverage(
        current_topic,
        user_answer,
        evidence_bundle.get("items") or [],
        paper_skeleton=paper_skeleton,
    )
    evidence_quality = evidence_bundle.get("evidenceQuality") or {}
    is_final_question = current_index >= SOCRATIC_TOTAL_QUESTIONS

    fallback_evaluation = _fallback_evaluation(
        user_answer,
        missing_aspects=missing_aspects,
        evidence_quality=evidence_quality,
    )
    fallback_payload: Dict[str, Any] = {
        **fallback_evaluation,
        "nextQuestion": _fallback_question(current_index + 1, previous_missing_aspects=missing_aspects),
    }
    if is_final_question:
        current_turn = {
            "index": current_index,
            "question": current_question,
            "answer": user_answer,
            "coveredAspects": covered_aspects,
            "missingAspects": missing_aspects,
            "evidenceQuality": evidence_quality,
            **fallback_evaluation,
        }
        review_suggestions = _build_review_suggestions([*completed_turns, current_turn], paper_skeleton=paper_skeleton)
        fallback_payload["reviewSuggestions"] = review_suggestions
        fallback_payload["finalSummary"] = _fallback_final_summary(
            [*completed_turns, current_turn],
            review_suggestions=review_suggestions,
        )

    terminal_field_prompt = (
        '"finalSummary": "最终总结",\n'
        '  "reviewSuggestions": ["建议回读章节/概念/证据点"]'
        if is_final_question
        else '"nextQuestion": "下一题"'
    )
    next_topic_instruction = ""
    if not is_final_question:
        next_focus = "、".join(
            _normalize_socratic_strings(
                [item.get("name") for item in next_topic.get("aspects", [])],
                limit=3,
                max_chars=20,
            )
        )
        previous_gap_text = "、".join(missing_aspects[:2]) if missing_aspects else "当前暴露出的薄弱点"
        next_topic_instruction = f"""
下一题固定题轴：
{next_topic.get("label", "下一题")}

下一题默认问题：
{next_topic.get("defaultQuestion", "")}

下一题重点要点：
{next_focus or "关键概念"}

如果自然衔接，请在下一题里提醒用户补上上一题仍薄弱的 {previous_gap_text}，但问题主体必须保持在“{next_topic.get('label', '下一题')}”。
"""

    prompt = f"""
你是一位中文学术导师，正在进行固定 5 轮的苏格拉底式引导学习。
你的任务是：根据当前问题与用户回答，判断用户掌握程度，给出简短反馈和提示，并决定下一步。

严格要求：
1. 当前是第 {current_index} / {SOCRATIC_TOTAL_QUESTIONS} 题，题轴固定为“{current_topic.get('label', '')}”，不得跳出当前题轴乱评估。
2. masteryLevel 只能是“需加强”“一般”“较好”三者之一。
3. feedback 用 1-2 句中文指出用户理解得怎样，重点哪里还薄弱或哪里已经比较到位。
4. hint 用 1 句中文提示用户下一步该如何思考。
5. 如果当前不是最后一题，nextQuestion 必须围绕下一题固定题轴；如果已经是第 5 题，则生成 finalSummary 与最多 3 条 reviewSuggestions。
6. 当当前论文证据不足或只部分相关时，feedback、hint 和 finalSummary 必须明确说明是“证据不足/证据部分相关”，不能把缺失的信息说成用户答错或论文已有结论。
7. 输出严格 JSON，不要输出任何额外解释。

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

当前题轴：
{current_topic.get("label", "")}

当前题目应关注的要点：
{'、'.join(evidence_bundle.get('expectedAspects') or current_topic.get('keywords') or [])}

当前论文证据判断：
{_format_socratic_evidence_quality(evidence_quality)}
{evidence_bundle.get("context") or ""}

用户回答已覆盖：
{'、'.join(covered_aspects) if covered_aspects else "暂无明显覆盖"}

用户回答仍缺：
{'、'.join(missing_aspects) if missing_aspects else "暂无明显缺口"}
{next_topic_instruction}

当前问题：
{current_question}

用户当前回答：
{user_answer}
"""
    payload = _call_json_llm(prompt, fallback_payload)

    evaluation = {
        "masteryLevel": _normalize_mastery_level(payload.get("masteryLevel")),
        "feedback": str(payload.get("feedback") or fallback_evaluation["feedback"]).strip(),
        "hint": str(payload.get("hint") or fallback_evaluation["hint"]).strip(),
        "coveredAspects": covered_aspects,
        "missingAspects": missing_aspects,
        "evidenceQuality": evidence_quality,
    }

    if is_final_question:
        review_suggestions = _normalize_socratic_strings(
            payload.get("reviewSuggestions") or fallback_payload.get("reviewSuggestions") or [],
            limit=3,
            max_chars=120,
        )
        final_summary = str(payload.get("finalSummary") or fallback_payload["finalSummary"]).strip()
        return {
            "status": "success",
            "evaluation": evaluation,
            "finalSummary": final_summary,
            "reviewSuggestions": review_suggestions,
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


