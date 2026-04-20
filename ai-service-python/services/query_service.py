from typing import Any, Dict, List, Optional

from llm.client import get_llm
from services.utils import parse_json_from_llm


MAX_KEYWORDS = 8


def rewrite_academic_query(
    question: str,
    context: Optional[str] = None,
    task_type: str = "chat",
) -> Dict[str, Any]:
    original = _clean_query(question)
    if not original:
        return _fallback_plan(original, task_type)

    prompt = f"""
You are rewriting a user question for academic paper retrieval.
Return valid JSON only.

JSON shape:
{{
  "rewritten": "concise academic retrieval query",
  "keywords": ["keyword1", "keyword2"]
}}

Rules:
- Preserve the user's intent.
- Prefer technical terms, method names, datasets, metrics, claims, and paper section cues.
- Do not answer the question.
- Use English keywords when they appear in the input; otherwise keep concise Chinese terms.
- Keep rewritten under 160 characters.

Task type: {task_type}

Question:
{original}

Context:
{(context or "")[:1200]}
"""

    try:
        raw = get_llm()._call(prompt)
        payload = parse_json_from_llm(raw)
        rewritten = _clean_query(payload.get("rewritten")) or original
        keywords = _normalize_keywords(payload.get("keywords"), rewritten)
        return {
            "original": original,
            "rewritten": rewritten,
            "keywords": keywords,
            "taskType": _normalize_task_type(task_type),
            "source": "llm",
        }
    except Exception as error:
        print(f"academic query rewrite fell back to original query: {error}")
        return _fallback_plan(original, task_type)


def build_retrieval_queries(
    question: str,
    context: Optional[str] = None,
    task_type: str = "chat",
) -> Dict[str, Any]:
    return rewrite_academic_query(question, context=context, task_type=task_type)


def _fallback_plan(question: str, task_type: str) -> Dict[str, Any]:
    original = _clean_query(question)
    return {
        "original": original,
        "rewritten": original,
        "keywords": _normalize_keywords([], original),
        "taskType": _normalize_task_type(task_type),
        "source": "fallback",
    }


def _normalize_keywords(value: Any, fallback_text: str = "") -> List[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.replace("，", ",").split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = []

    keywords: List[str] = []
    seen = set()
    for item in raw_items:
        cleaned = item.strip(" \t\r\n,.;:，。；：、")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(cleaned[:80])
        if len(keywords) >= MAX_KEYWORDS:
            return keywords

    if not keywords and fallback_text:
        for token in _tokenize_fallback_keywords(fallback_text):
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(token)
            if len(keywords) >= MAX_KEYWORDS:
                break

    return keywords


def _tokenize_fallback_keywords(text: str) -> List[str]:
    cleaned = _clean_query(text)
    if not cleaned:
        return []

    separators = ",.;:，。；：、()[]{}<>《》/\\|!?！？\n\t"
    for separator in separators:
        cleaned = cleaned.replace(separator, " ")

    return [
        token.strip()
        for token in cleaned.split()
        if len(token.strip()) >= 2
    ]


def _clean_query(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_task_type(value: Any) -> str:
    text = str(value or "chat").strip() or "chat"
    return text[:40]
