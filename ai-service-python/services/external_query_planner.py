from collections.abc import Iterable
from typing import Any

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
    search_keywords: Any = None,
) -> list[str]:
    # Prioritize LLM-generated search keywords when available
    normalized_keywords = _normalize_items(search_keywords, _MISSING_ASPECT_CHARS) if search_keywords else []
    if normalized_keywords:
        normalized_question = sanitize_external_academic_query_text(
            research_question,
            max_chars=_RESEARCH_QUESTION_CHARS,
        )
        queries = []
        seen = set()
        for kw in normalized_keywords:
            query = f"{normalized_question} {kw}"[:MAX_EXTERNAL_QUERY_CHARS].rstrip()
            key = query.casefold()
            if not query or key in seen:
                continue
            seen.add(key)
            queries.append(query)
            if len(queries) >= MAX_EXTERNAL_QUERIES:
                return queries
        if queries:
            return queries

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


def build_llm_academic_queries(
    research_question: Any,
    evidence_gaps: Any,
    *,
    temperature: float = 0.3,
    max_queries: int = 3,
) -> list[str]:
    """Use LLM (flash model) to generate precise academic search queries.

    Given a research question and evidence gaps (missing aspects), the LLM
    generates 1-3 precise academic queries with keywords and expected source
    types. On any failure, falls back to the deterministic
    build_external_academic_queries().

    Args:
        research_question: The main research question.
        evidence_gaps: List of missing aspects / knowledge gaps.
        temperature: LLM temperature (default 0.3).
        max_queries: Maximum number of queries to return (1-5).

    Returns:
        List of deduplicated, sanitized queries, each ≤256 chars.
    """
    normalized_question = sanitize_external_academic_query_text(
        research_question,
        max_chars=_RESEARCH_QUESTION_CHARS,
    )
    gap_items = _normalize_items(evidence_gaps, _MISSING_ASPECT_CHARS) if evidence_gaps else []

    prompt = (
        "You are a research query optimizer for academic paper search. "
        "Given a research question and evidence gaps, generate precise "
        "academic search queries.\n\n"
        f"Research question: {normalized_question[:96]}\n\n"
        f"Evidence gaps to fill:\n"
        + "\n".join(f"- {g}" for g in (gap_items or ["general search"]))
        + "\n\n"
        "Instructions:\n"
        f"- Generate 1-{max_queries} queries, one per line\n"
        "- Each query should combine key terminology with expected source type\n"
        "- Prioritize academic terms and precise keyword combinations\n"
        "- Each query must be ≤250 characters\n"
        "- Focus on filling the specific knowledge gaps\n"
        "- Do not include URLs or special characters\n"
        "- Output only the queries, no numbering or explanation"
    )

    raw_output = ""
    try:
        from llm.client import DeepSeekLLM
        llm = DeepSeekLLM(model="deepseek-v4-flash", temperature=temperature)
        raw_output = llm._call(prompt)
    except Exception:
        return _fallback_academic_queries(research_question, evidence_gaps, max_queries)

    if not raw_output or not raw_output.strip():
        return _fallback_academic_queries(research_question, evidence_gaps, max_queries)

    queries: list[str] = []
    seen: set = set()
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading numbering like "1.", "1)", "-", "*"
        while line and (line[0].isdigit() or line[0] in ".-*#) "):
            if line[0] in ".) ":
                line = line[1:].strip()
                break
            line = line[1:].strip()
        if not line:
            continue

        query = sanitize_external_academic_query_text(line, max_chars=MAX_EXTERNAL_QUERY_CHARS)
        if not query:
            continue
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= max_queries:
            break

    if not queries:
        return _fallback_academic_queries(research_question, evidence_gaps, max_queries)

    return queries


def _fallback_academic_queries(
    research_question: Any,
    evidence_gaps: Any,
    max_queries: int,
) -> list[str]:
    """LLM 不可用时的确定性回退，必须仍然满足 build_llm_academic_queries 的契约。

    直接把 build_external_academic_queries() 的结果原样返回会违背 docstring 里写明的
    两条承诺（max_queries 是返回条数上限、返回值非空）：那个函数按
    MAX_EXTERNAL_QUERIES=5 截断、根本不认 max_queries，而 missing_aspects 为空时
    它返回 []。实测账户欠费（HTTP 402）走回退时，
    test_llm_academic_respects_max_queries 拿到 4 条（断言 <= 2）、
    test_llm_academic_empty_gaps_returns_queries 拿到 0 条（断言 >= 1）；账户恢复后
    这两个用例又“通过”了 —— 只是活 LLM 恰好守约，缺陷被账户余额掩盖了。
    """
    limit = max(1, min(int(max_queries or MAX_EXTERNAL_QUERIES), MAX_EXTERNAL_QUERIES))
    queries = build_external_academic_queries(
        research_question=research_question,
        planner_sub_questions=None,
        missing_aspects=evidence_gaps,
    )[:limit]
    if queries:
        return queries

    # 缺口为空时也要给出可用的检索式：研究问题本身就是最保守的那一条。
    question = sanitize_external_academic_query_text(
        research_question,
        max_chars=MAX_EXTERNAL_QUERY_CHARS,
    )
    return [question] if question else []


def _normalize_items(value: Any, max_chars: int) -> list[str]:
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


MAX_WEB_SEARCH_QUERIES = 5
MAX_WEB_SEARCH_QUERY_CHARS = 300
# refine_search_queries 的 docstring 承诺 1-3 条，比 build_web_search_queries 的 5 条上限更严。
MAX_REFINED_WEB_QUERIES = 3
_WEB_RESEARCH_QUESTION_CHARS = 120
_WEB_MISSING_ASPECT_CHARS = 180


def build_web_search_queries(
    research_question: Any,
    missing_aspects: Any,
    search_keywords: Any = None,
) -> list[str]:
    """Build web search queries from research question and missing aspects.

    Returns deduplicated, sanitized queries suitable for the search_web tool.
    Each query is capped at MAX_WEB_SEARCH_QUERY_CHARS (300).
    When search_keywords (from LLM plan) are provided, they are used with priority.
    """
    from services.safety_service import sanitize_web_search_query_text

    # Prioritize LLM-generated search keywords when available
    normalized_keywords = _normalize_web_aspects(search_keywords, _WEB_MISSING_ASPECT_CHARS) if search_keywords else []
    if normalized_keywords:
        normalized_question = sanitize_web_search_query_text(
            research_question,
            max_chars=_WEB_RESEARCH_QUESTION_CHARS,
        )
        queries = []
        seen = set()
        for kw in normalized_keywords:
            query = f"{normalized_question} {kw}"[:MAX_WEB_SEARCH_QUERY_CHARS].rstrip()
            key = query.casefold()
            if not query or key in seen:
                continue
            seen.add(key)
            queries.append(query)
            if len(queries) >= MAX_WEB_SEARCH_QUERIES:
                return queries
        if queries:
            return queries

    normalized_missing = _normalize_web_aspects(missing_aspects, _WEB_MISSING_ASPECT_CHARS)
    if not normalized_missing:
        return []

    normalized_question = sanitize_web_search_query_text(
        research_question,
        max_chars=_WEB_RESEARCH_QUESTION_CHARS,
    )

    queries = []
    seen = set()
    for missing_aspect in normalized_missing:
        query = " ".join(
            part for part in (normalized_question, missing_aspect) if part
        )[:MAX_WEB_SEARCH_QUERY_CHARS].rstrip()
        key = query.casefold()
        if not query or key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= MAX_WEB_SEARCH_QUERIES:
            return queries
    return queries


def _normalize_web_aspects(value: Any, max_chars: int) -> list[str]:
    """Normalize missing aspects into web-searchable query terms."""
    from services.safety_service import sanitize_web_search_query_text

    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = value[:MAX_EXTERNAL_QUERY_INPUT_ITEMS]
    else:
        items = []

    normalized = []
    seen = set()
    for item in items:
        text = sanitize_web_search_query_text(item, max_chars=max_chars)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _fallback_web_queries(research_question: Any, missing_aspects: Any) -> list[str]:
    """refine_search_queries 的确定性回退，同样要守住“1-3 条、非空”的契约。

    与 _fallback_academic_queries 同一类缺陷：build_web_search_queries() 按
    MAX_WEB_SEARCH_QUERIES=5 截断（超过 docstring 承诺的 3 条），且
    missing_aspects 为空时返回 []（违背“至少 1 条”）。
    """
    from services.safety_service import sanitize_web_search_query_text

    queries = build_web_search_queries(
        research_question=research_question,
        missing_aspects=missing_aspects,
    )[:MAX_REFINED_WEB_QUERIES]
    if queries:
        return queries

    question = sanitize_web_search_query_text(
        research_question,
        max_chars=MAX_WEB_SEARCH_QUERY_CHARS,
    )
    return [question] if question else []


def refine_search_queries(
    research_question: str,
    previous_results: list,
    missing_aspects: list,
    *,
    temperature: float = 0.3,
) -> list[str]:
    """Use LLM (flash model) to generate refined web search queries.

    Based on previous round results and remaining missing aspects,
    the LLM generates 1-3 precise search queries prioritizing academic
    terminology and keyword combinations.

    On LLM failure, falls back to deterministic build_web_search_queries().

    Args:
        research_question: The main research question.
        previous_results: List of {title, description/abstract} from prior searches.
        missing_aspects: Aspects still uncovered.
        temperature: LLM temperature (default 0.3).

    Returns:
        List of 1-3 sanitized, deduplicated queries, each ≤300 chars.
    """
    from services.safety_service import sanitize_web_search_query_text

    if not previous_results:
        return _fallback_web_queries(research_question, missing_aspects)

    # Build a summary of previous results for the LLM
    result_lines = []
    for i, item in enumerate(previous_results[:5]):
        title = str(item.get("title") or "")[:200]
        desc = str(item.get("description") or item.get("abstract") or "")[:200]
        if title:
            result_lines.append(f"{i + 1}. {title}")
            if desc:
                result_lines.append(f"   Description: {desc}")

    missing_text = ", ".join(missing_aspects[:5]) if missing_aspects else "none specified"

    prompt = (
        f"You are a research query optimizer. Based on previous web search results "
        f"and remaining knowledge gaps, generate 1-3 refined search queries.\n\n"
        f"Research question: {research_question[:200]}\n\n"
        f"Previous search results:\n{chr(10).join(result_lines)}\n\n"
        f"Remaining missing aspects: {missing_text}\n\n"
        f"Instructions:\n"
        f"- Generate 1-3 queries, one per line\n"
        f"- Prioritize academic terms and precise keyword combinations\n"
        f"- Each query must be ≤300 characters\n"
        f"- Focus on filling the specific knowledge gaps\n"
        f"- Do not include URLs or special characters\n"
        f"- Output only the queries, no numbering or explanation"
    )

    raw_output = ""
    try:
        from llm.client import DeepSeekLLM
        llm = DeepSeekLLM(model="deepseek-v4-flash", temperature=temperature)
        raw_output = llm._call(prompt)
    except Exception:
        return _fallback_web_queries(research_question, missing_aspects)

    if not raw_output or not raw_output.strip():
        return _fallback_web_queries(research_question, missing_aspects)

    # Parse response: one query per line, strip numbering/bullets
    queries = []
    seen = set()
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading numbering like "1.", "1)", "-", "*"
        while line and (line[0].isdigit() or line[0] in ".-*#) "):
            if line[0] in ".) ":
                line = line[1:].strip()
                break
            line = line[1:].strip()
        if not line:
            continue

        # Sanitize and truncate
        query = sanitize_web_search_query_text(line, max_chars=300)
        if not query:
            continue
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= 3:
            break

    if not queries:
        return _fallback_web_queries(research_question, missing_aspects)

    return queries
