from typing import Any, Iterable, List

from services.safety_service import sanitize_external_academic_query_text


MAX_EXTERNAL_QUERIES = 5
MAX_EXTERNAL_QUERY_CHARS = 256
MAX_EXTERNAL_QUERY_INPUT_ITEMS = 8

_RESEARCH_QUESTION_CHARS = 96
_SUB_QUESTION_CHARS = 80
_MISSING_ASPECT_CHARS = 72


def build_external_academic_queries(
    research_question: Any,
    planner_sub_questions: Any,
    missing_aspects: Any,
) -> List[str]:
    normalized_missing_aspects = _normalize_items(missing_aspects, _MISSING_ASPECT_CHARS)
    if not normalized_missing_aspects:
        return []

    normalized_question = sanitize_external_academic_query_text(
        research_question,
        max_chars=_RESEARCH_QUESTION_CHARS,
    )
    normalized_sub_questions = _normalize_items(planner_sub_questions, _SUB_QUESTION_CHARS) or [""]

    queries = []
    seen = set()
    for sub_question in normalized_sub_questions:
        for missing_aspect in normalized_missing_aspects:
            query = " ".join(
                part for part in (normalized_question, sub_question, missing_aspect) if part
            )[:MAX_EXTERNAL_QUERY_CHARS].rstrip()
            key = query.casefold()
            if not query or key in seen:
                continue
            seen.add(key)
            queries.append(query)
            if len(queries) >= MAX_EXTERNAL_QUERIES:
                return queries
    return queries


def _normalize_items(value: Any, max_chars: int) -> List[str]:
    if isinstance(value, str):
        items: Iterable[Any] = [value]
    elif isinstance(value, (list, tuple)):
        items = value[:MAX_EXTERNAL_QUERY_INPUT_ITEMS]
    else:
        items = []

    normalized_items = []
    seen = set()
    for item in items:
        normalized = sanitize_external_academic_query_text(item, max_chars=max_chars)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        normalized_items.append(normalized)
    return normalized_items
