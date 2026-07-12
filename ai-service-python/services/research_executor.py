import copy
from typing import Any, Dict, List

from services.evidence_service import format_evidence_context, normalize_evidence_items
from services.external_query_planner import build_external_academic_queries
from services.query_service import build_retrieval_queries
from services.safety_service import MAX_RETRIEVAL_RETRIES, external_search_degradation_reason
from services.trace_service import record_counter, sanitize_text, trace_step
from services.tool_registry import get_tool_registry


def research_sub_question(
    sub_question: str,
    question: str,
    pdf_id: str,
    paper_skeleton: Dict[str, Any],
    documents: List[Dict[str, Any]],
    *,
    allow_web_search: bool = False,
) -> Dict[str, Any]:
    research_context = build_planning_context(question, paper_skeleton, documents)
    with trace_step(
        "research_query_plan",
        input_size=len(str(research_context or "")),
        meta={"subQuestion": sanitize_text(sub_question, max_chars=120)},
    ) as step:
        query_plan = build_retrieval_queries(sub_question, context=research_context, task_type="research")
        step["outputSize"] = len(query_plan.get("keywords") or [])

    current_evidence = retrieve_current_paper_evidence(
        query_plan.get("rewritten") or query_plan.get("original") or sub_question,
        pdf_id=pdf_id,
    )
    combined_evidence = merge_evidence_lists(current_evidence)
    with trace_step("research_judge_current", input_size=len(combined_evidence)) as step:
        judge = judge_research_evidence(sub_question, combined_evidence, keywords=query_plan.get("keywords") or [])
        step["outputSize"] = len(judge.get("missingAspects") or [])
        annotate_judge_step(step, judge, "try_library" if should_try_library(judge) else "stop")

    library_evidence: List[Dict[str, Any]] = []
    retry_reason = ""
    if should_try_library(judge):
        library_evidence = retrieve_library_evidence(
            query_plan.get("rewritten") or query_plan.get("original") or sub_question,
            exclude_pdf_id=pdf_id,
        )
        combined_evidence = merge_evidence_lists(current_evidence, library_evidence)
        with trace_step("research_judge_library", input_size=len(combined_evidence)) as step:
            judge = judge_research_evidence(sub_question, combined_evidence, keywords=query_plan.get("keywords") or [])
            step["outputSize"] = len(judge.get("missingAspects") or [])
            annotate_judge_step(step, judge, "retry" if should_retry(judge) else "stop")

    if should_retry(judge):
        retry_reason = clean_text(judge.get("retryReason"))
        retry_query = build_retry_query(sub_question, query_plan, judge)
        record_counter("retryCount")
        with trace_step(
            "research_retry_retrieval",
            input_size=len(str(retry_query or "")),
            meta={"missingAspects": judge.get("missingAspects") or []},
        ):
            retry_current = retrieve_current_paper_evidence(retry_query, pdf_id=pdf_id)
            retry_library = retrieve_library_evidence(retry_query, exclude_pdf_id=pdf_id)
        combined_evidence = merge_evidence_lists(current_evidence, library_evidence, retry_current, retry_library)
        with trace_step("research_judge_retry", input_size=len(combined_evidence)) as step:
            judge = judge_research_evidence(
                sub_question,
                combined_evidence,
                keywords=[*(query_plan.get("keywords") or []), *(judge.get("missingAspects") or [])],
            )
            step["outputSize"] = len(judge.get("missingAspects") or [])
            annotate_judge_step(step, judge, "stop")

    external_degradation = ""
    if should_try_external(judge):
        missing = normalize_missing_aspects(judge.get("missingAspects"))
        with trace_step(
            "research_external_search",
            input_size=len(missing),
            meta={"missingAspects": missing},
        ) as ext_step:
            external_result = retrieve_external_academic_evidence(
                research_question=question,
                sub_question=sub_question,
                missing_aspects=missing,
            )
            external_evidence = external_result.get("items") or []
            external_degradation = external_result.get("degradation") or ""
            ext_step["outputSize"] = len(external_evidence)
            ext_step["meta"] = {
                **ext_step.get("meta", {}),
                "status": external_result.get("status"),
                "degradation": external_degradation,
            }
            if external_evidence:
                combined_evidence = merge_evidence_lists(combined_evidence, external_evidence)
                with trace_step("research_judge_external", input_size=len(combined_evidence)) as judge_step:
                    judge = judge_research_evidence(
                        sub_question,
                        combined_evidence,
                        keywords=[
                            *(query_plan.get("keywords") or []),
                            *(judge.get("missingAspects") or []),
                        ],
                    )
                    judge_step["outputSize"] = len(judge.get("missingAspects") or [])
                    annotate_judge_step(judge_step, judge, "stop")

    web_search_used = False
    if should_try_web_search(judge, allow_web_search=allow_web_search):
        missing = normalize_missing_aspects(judge.get("missingAspects"))
        with trace_step(
            "research_web_search",
            input_size=len(missing),
            meta={"missingAspects": missing},
        ) as web_step:
            web_result = retrieve_web_search_evidence(
                research_question=question,
                missing_aspects=missing,
            )
            web_evidence = web_result.get("items") or []
            web_degradation = web_result.get("degradation") or ""
            web_step["outputSize"] = len(web_evidence)
            web_step["meta"] = {
                **web_step.get("meta", {}),
                "status": web_result.get("status"),
                "degradation": web_degradation,
            }
            if web_evidence:
                combined_evidence = merge_evidence_lists(combined_evidence, web_evidence)
                web_search_used = True
                with trace_step("research_judge_web", input_size=len(combined_evidence)) as judge_step:
                    judge = judge_research_evidence(
                        sub_question,
                        combined_evidence,
                        keywords=[
                            *(query_plan.get("keywords") or []),
                            *(judge.get("missingAspects") or []),
                        ],
                    )
                    judge_step["outputSize"] = len(judge.get("missingAspects") or [])
                    annotate_judge_step(judge_step, judge, "stop")

    summary = build_finding_summary(sub_question, combined_evidence, judge)
    return {
        "subQuestion": sub_question,
        "summary": summary,
        "verdict": str(judge.get("verdict") or "INCORRECT"),
        "judgeScore": normalize_judge_score(judge.get("judgeScore")),
        "coverage": normalize_judge_coverage(judge.get("coverage")),
        "missingAspects": normalize_missing_aspects(judge.get("missingAspects")),
        "retryReason": retry_reason,
        "externalSearchDegradation": external_degradation,
        "webSearchUsed": web_search_used,
        "sourceIds": [str(item.get("sourceId")) for item in combined_evidence if item.get("sourceId")][:6],
        "sources": combined_evidence[:6],
    }


def retrieve_current_paper_evidence(query: str, pdf_id: str, top_k: int = 8, limit: int = 5) -> List[Dict[str, Any]]:
    response = invoke_tool(
        "retrieve_current_paper",
        {
            "pdfId": pdf_id,
            "query": query,
            "topK": top_k,
            "limit": limit,
            "maxTextChars": 700,
        },
    )
    return list(response.get("items") or [])


def retrieve_library_evidence(query: str, exclude_pdf_id: str | None = None, top_k: int = 5, limit: int = 4) -> List[Dict[str, Any]]:
    response = invoke_tool(
        "retrieve_library",
        {
            "query": query,
            "excludePdfId": exclude_pdf_id,
            "topK": top_k,
            "limit": limit,
            "maxTextChars": 700,
        },
    )
    return list(response.get("items") or [])


def merge_evidence_lists(*groups: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for group in groups:
        for item in group or []:
            normalized = normalize_evidence_items([item], limit=1, max_text_chars=700)
            if not normalized:
                continue
            current = ensure_stable_source_ids(normalized, fallback_prefix="source")[0]
            key = (str(current.get("sourceId") or ""), str(current.get("text") or "")[:180])
            if key in seen:
                continue
            seen.add(key)
            merged.append(current)
            if len(merged) >= limit:
                return merged
    return merged


def ensure_stable_source_ids(items: List[Dict[str, Any]], fallback_prefix: str) -> List[Dict[str, Any]]:
    stabilized: List[Dict[str, Any]] = []
    for index, item in enumerate(items or []):
        current = copy.deepcopy(item)
        base = str(current.get("sourceId") or "").strip()
        if not base or base.startswith("source-"):
            pdf_id = slugify(current.get("pdfId") or fallback_prefix or "source")
            chunk_index = current.get("chunkIndex")
            if chunk_index is not None:
                base = f"{pdf_id}-chunk-{chunk_index}"
            else:
                base = f"{pdf_id}-{index + 1}"
        current["sourceId"] = base[:80]
        stabilized.append(current)
    return stabilized


def build_retry_query(sub_question: str, query_plan: Dict[str, Any], judge_result: Dict[str, Any]) -> str:
    parts = [
        query_plan.get("original") or sub_question,
        query_plan.get("rewritten") or "",
        *(query_plan.get("keywords") or []),
        *(judge_result.get("missingAspects") or []),
    ]

    unique_parts = []
    seen = set()
    for part in parts:
        text = clean_text(part)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_parts.append(text)
    return " ".join(unique_parts)[:500] or sub_question


def build_finding_summary(sub_question: str, evidence: List[Dict[str, Any]], judge_result: Dict[str, Any]) -> str:
    verdict = str(judge_result.get("verdict") or "INCORRECT")
    missing_aspects = normalize_missing_aspects(judge_result.get("missingAspects"))
    preview = evidence_preview(evidence)
    if verdict == "CORRECT":
        return f"围绕“{sub_question}”，现有证据基本充分。关键信息包括：{preview or '已检索到可支撑回答的当前论文或补充文献证据。'}"
    if verdict == "AMBIGUOUS":
        suffix = f"；但仍缺少 {', '.join(missing_aspects)} 等关键信息" if missing_aspects else "；但关键论证仍不够完整"
        return f"围绕“{sub_question}”，现有证据部分相关。已观察到：{preview or '检索到了部分线索'}{suffix}。"
    if missing_aspects:
        return f"围绕“{sub_question}”，当前证据不足，仍缺少 {', '.join(missing_aspects)} 等直接依据。"
    return f"围绕“{sub_question}”，当前没有检索到足够直接的证据。"


def build_planning_context(question: str, paper_skeleton: Dict[str, Any], documents: List[Dict[str, Any]]) -> str:
    skeleton_text = (read_paper_skeleton(paper_skeleton, max_sections=6, max_chars_per_section=220).get("text") or "")[:1200]
    evidence_text = format_evidence_context(documents, title="当前论文证据", max_items=4, max_text_chars=260)
    return (
        f"Main question: {question}\n"
        f"Paper skeleton:\n{skeleton_text}\n"
        f"{evidence_text[:1800]}"
    )


def read_paper_skeleton(
    paper_skeleton: Dict[str, Any],
    *,
    max_sections: int = 6,
    max_chars_per_section: int = 220,
) -> Dict[str, Any]:
    return invoke_tool(
        "read_paper_skeleton",
        {
            "paperSkeleton": paper_skeleton or {},
            "maxSections": max_sections,
            "maxCharsPerSection": max_chars_per_section,
        },
    )


def judge_research_evidence(question: str, evidence_items: List[Dict[str, Any]], keywords: List[str] | None = None) -> Dict[str, Any]:
    return invoke_tool(
        "judge_evidence",
        {
            "question": question,
            "evidenceItems": evidence_items,
            "keywords": keywords or [],
        },
    )


def annotate_judge_step(step: Dict[str, Any], judge_result: Dict[str, Any], decision: str) -> None:
    meta = dict(step.get("meta") or {})
    coverage = normalize_judge_coverage(judge_result.get("coverage"))
    meta.update(
        {
            "verdict": str(judge_result.get("verdict") or "INCORRECT"),
            "judgeScore": normalize_judge_score(judge_result.get("judgeScore")),
            "coverageScore": coverage.get("score"),
            "missingAspects": normalize_missing_aspects(judge_result.get("missingAspects")),
            "retryReason": clean_text(judge_result.get("retryReason")),
            "decision": decision if decision in {"stop", "try_library", "retry"} else "stop",
        }
    )
    step["meta"] = meta


def should_try_library(judge_result: Dict[str, Any]) -> bool:
    return str(judge_result.get("verdict") or "") != "CORRECT" or float(judge_result.get("confidence") or 0) < 0.68


def should_retry(judge_result: Dict[str, Any]) -> bool:
    return MAX_RETRIEVAL_RETRIES > 0 and bool(judge_result.get("shouldRetry")) and (
        str(judge_result.get("verdict") or "") != "CORRECT" or float(judge_result.get("confidence") or 0) < 0.68
    )


def should_try_external(judge_result: Dict[str, Any]) -> bool:
    if str(judge_result.get("verdict") or "") == "CORRECT":
        return False
    return bool(normalize_missing_aspects(judge_result.get("missingAspects")))


def should_try_web_search(judge_result: Dict[str, Any], *, allow_web_search: bool = False) -> bool:
    """Web search triggers only when academic+external is insufficient."""
    if not allow_web_search:
        return False
    if str(judge_result.get("verdict") or "") == "CORRECT":
        return False
    return bool(normalize_missing_aspects(judge_result.get("missingAspects")))


def retrieve_web_search_evidence(
    research_question: str,
    missing_aspects: list,
    limit_per_query: int = 4,
) -> Dict[str, Any]:
    from services.external_query_planner import build_web_search_queries

    queries = build_web_search_queries(
        research_question=research_question,
        missing_aspects=missing_aspects,
    )
    if not queries:
        return {"status": "no_queries", "items": [], "degradation": ""}

    all_items: list = []
    final_status = "success"
    degradation = ""

    for query in queries:
        try:
            response = invoke_tool(
                "search_web",
                {"query": query, "limit": limit_per_query},
            )
        except Exception:
            final_status = "failed"
            degradation = external_search_degradation_reason(final_status)
            break

        status = str(response.get("status") or "failed")
        if status == "success":
            items = list(response.get("items") or [])
            all_items.extend(items)
        else:
            final_status = status
            degradation = external_search_degradation_reason(status, response.get("reason"))
            break

    return {
        "status": final_status,
        "items": all_items,
        "degradation": degradation,
    }


def retrieve_external_academic_evidence(
    research_question: str,
    sub_question: str,
    missing_aspects: list,
    limit_per_query: int = 3,
) -> Dict[str, Any]:
    queries = build_external_academic_queries(
        research_question=research_question,
        planner_sub_questions=[sub_question],
        missing_aspects=missing_aspects,
    )
    if not queries:
        return {"status": "no_queries", "items": [], "degradation": ""}

    all_items: list = []
    final_status = "success"
    degradation = ""

    for query in queries:
        try:
            response = invoke_tool(
                "retrieve_external_academic",
                {"query": query, "limit": limit_per_query},
            )
        except Exception:
            final_status = "failed"
            degradation = external_search_degradation_reason(final_status)
            break

        status = str(response.get("status") or "failed")
        if status == "success":
            items = list(response.get("items") or [])
            all_items.extend(items)
        else:
            final_status = status
            degradation = external_search_degradation_reason(status, response.get("reason"))
            break

    return {
        "status": final_status,
        "items": all_items,
        "degradation": degradation,
    }


def normalize_judge_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def normalize_judge_coverage(value: Any) -> Dict[str, Any]:
    coverage = value if isinstance(value, dict) else {}
    return {
        "score": round(max(0.0, min(1.0, coerce_float(coverage.get("score"), 0.0))), 2),
        "matchedAspects": max(0, coerce_int(coverage.get("matchedAspects"), 0)),
        "totalAspects": max(0, coerce_int(coverage.get("totalAspects"), 0)),
        "evidenceCount": max(0, coerce_int(coverage.get("evidenceCount"), 0)),
        "sourceTypes": normalize_text_list(coverage.get("sourceTypes"), limit=6),
    }


def normalize_missing_aspects(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items = []
    seen = set()
    for raw_item in value:
        text = clean_text(raw_item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text[:80])
        if len(items) >= 5:
            break
    return items


def normalize_text_list(value: Any, limit: int = 5) -> List[str]:
    if isinstance(value, str):
        raw_items = [line.strip("-* 0123456789.、 \t") for line in value.splitlines()]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    items = []
    seen = set()
    for raw_item in raw_items:
        text = clean_text(raw_item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text[:160])
        if limit and len(items) >= limit:
            break
    return items


def evidence_preview(evidence: List[Dict[str, Any]]) -> str:
    snippets = []
    for item in evidence[:2]:
        text = clean_text(item.get("text"))
        if text:
            snippets.append(text[:100])
    return "；".join(snippets)


def invoke_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = get_tool_registry().invoke(name, payload)
    return response if isinstance(response, dict) else {}


def coerce_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def coerce_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def slugify(value: Any) -> str:
    import re

    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.strip("-") or "source"
