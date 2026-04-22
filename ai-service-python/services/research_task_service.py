import copy
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from llm.client import get_llm
from rag.store import get_rag, retrieve_hybrid_results
from schemas.requests import ResearchTaskCreateRequest
from services.evidence_service import format_evidence_context, normalize_evidence_items
from services.query_service import build_retrieval_queries
from services.retrieval_judge_service import judge_evidence_quality
from services.utils import parse_json_from_llm


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
PLANNING_STAGE = "planning"
RETRIEVING_STAGE = "retrieving"
JUDGING_STAGE = "judging"
SYNTHESIZING_STAGE = "synthesizing"
DONE_STAGE = "done"

_TASKS: Dict[str, Dict[str, Any]] = {}
_TASK_CONTEXTS: Dict[str, Dict[str, Any]] = {}
_TASK_CANCELLATIONS: set[str] = set()
_TASK_LOCK = threading.RLock()
_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2)


class ResearchTaskNotFoundError(Exception):
    pass


def create_research_task(
    request: ResearchTaskCreateRequest,
    start_async: bool = True,
) -> Dict[str, Any]:
    question = " ".join(str(request.question or "").strip().split())
    pdf_id = " ".join(str(request.pdfId or "").strip().split())
    if not question:
        raise ValueError("Question cannot be empty.")
    if not pdf_id:
        raise ValueError("pdfId cannot be empty.")

    task_id = str(uuid.uuid4())
    task = {
        "taskId": task_id,
        "status": "pending",
        "stage": PLANNING_STAGE,
        "progress": 0.0,
        "question": question,
        "pdfId": pdf_id,
        "plan": [],
        "findings": [],
        "report": "",
        "error": "",
    }

    with _TASK_LOCK:
        _TASKS[task_id] = copy.deepcopy(task)
        _TASK_CONTEXTS[task_id] = {
            "paperSkeleton": copy.deepcopy(request.paperSkeleton or {}),
        }
        _TASK_CANCELLATIONS.discard(task_id)

    if start_async:
        _TASK_EXECUTOR.submit(run_research_task_now, task_id)

    return {"status": "success", "task": _copy_task_snapshot(task_id)}


def get_research_task(task_id: str) -> Dict[str, Any]:
    return {"status": "success", "task": _copy_task_snapshot(task_id)}


def cancel_research_task(task_id: str) -> Dict[str, Any]:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise ResearchTaskNotFoundError("Research task not found.")
        if str(task.get("status") or "") in TERMINAL_STATUSES:
            return {"status": "success", "task": copy.deepcopy(task)}

        _TASK_CANCELLATIONS.add(task_id)
        cancelled = {
            **task,
            "status": "cancelled",
            "stage": DONE_STAGE,
        }
        _TASKS[task_id] = cancelled
        return {"status": "success", "task": copy.deepcopy(cancelled)}


def clear_research_tasks() -> None:
    with _TASK_LOCK:
        _TASKS.clear()
        _TASK_CONTEXTS.clear()
        _TASK_CANCELLATIONS.clear()


def run_research_task_now(task_id: str) -> Dict[str, Any]:
    task = _copy_task_snapshot(task_id)
    context = _copy_task_context(task_id)
    _run_research_task(
        task_id,
        question=str(task.get("question") or ""),
        pdf_id=str(task.get("pdfId") or ""),
        paper_skeleton=context.get("paperSkeleton") or {},
    )
    return _copy_task_snapshot(task_id)


def _run_research_task(task_id: str, question: str, pdf_id: str, paper_skeleton: Dict[str, Any]) -> None:
    if _is_cancelled(task_id):
        return

    _update_task_snapshot(task_id, status="running", stage=PLANNING_STAGE, progress=0.0)

    try:
        documents, normalized_pdf_id = _load_current_paper_documents(pdf_id)
        if not documents:
            _fail_task(task_id, "Current paper has not been indexed yet.")
            return
        if _is_cancelled(task_id):
            return

        brief, sub_questions = _build_research_plan(question, paper_skeleton, documents)
        _update_task_snapshot(task_id, stage=PLANNING_STAGE, progress=0.2, plan=sub_questions)
        if _is_cancelled(task_id):
            return

        findings: List[Dict[str, Any]] = []
        total = max(len(sub_questions), 1)
        for index, sub_question in enumerate(sub_questions):
            if _is_cancelled(task_id):
                return

            base_progress = round(0.2 + (index / total) * 0.6, 2)
            _update_task_snapshot(task_id, stage=RETRIEVING_STAGE, progress=base_progress)

            finding = _research_sub_question(
                sub_question=sub_question,
                question=question,
                pdf_id=normalized_pdf_id,
                paper_skeleton=paper_skeleton,
                documents=documents,
            )
            if _is_cancelled(task_id):
                return

            findings.append(finding)
            done_progress = round(0.2 + ((index + 1) / total) * 0.6, 2)
            _update_task_snapshot(
                task_id,
                stage=JUDGING_STAGE,
                progress=done_progress,
                findings=copy.deepcopy(findings),
            )

        if _is_cancelled(task_id):
            return

        _update_task_snapshot(task_id, stage=SYNTHESIZING_STAGE, progress=0.9, findings=copy.deepcopy(findings))
        report = _build_research_report(question, brief, sub_questions, findings)
        if _is_cancelled(task_id):
            return

        _update_task_snapshot(
            task_id,
            status="succeeded",
            stage=DONE_STAGE,
            progress=1.0,
            findings=copy.deepcopy(findings),
            report=report,
            error="",
        )
    except Exception as error:
        _fail_task(task_id, str(error))


def _research_sub_question(
    sub_question: str,
    question: str,
    pdf_id: str,
    paper_skeleton: Dict[str, Any],
    documents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    research_context = _build_planning_context(question, paper_skeleton, documents)
    query_plan = build_retrieval_queries(sub_question, context=research_context, task_type="research")

    current_evidence = _retrieve_current_paper_evidence(
        query_plan.get("rewritten") or query_plan.get("original") or sub_question,
        pdf_id=pdf_id,
    )
    combined_evidence = _merge_evidence_lists(current_evidence)
    judge = judge_evidence_quality(sub_question, combined_evidence, keywords=query_plan.get("keywords") or [])

    library_evidence: List[Dict[str, Any]] = []
    if _should_try_library(judge):
        library_evidence = _retrieve_library_evidence(
            query_plan.get("rewritten") or query_plan.get("original") or sub_question,
            exclude_pdf_id=pdf_id,
        )
        combined_evidence = _merge_evidence_lists(current_evidence, library_evidence)
        judge = judge_evidence_quality(sub_question, combined_evidence, keywords=query_plan.get("keywords") or [])

    if _should_retry(judge):
        retry_query = _build_retry_query(sub_question, query_plan, judge)
        retry_current = _retrieve_current_paper_evidence(retry_query, pdf_id=pdf_id)
        retry_library = _retrieve_library_evidence(retry_query, exclude_pdf_id=pdf_id)
        combined_evidence = _merge_evidence_lists(current_evidence, library_evidence, retry_current, retry_library)
        judge = judge_evidence_quality(
            sub_question,
            combined_evidence,
            keywords=[*(query_plan.get("keywords") or []), *(judge.get("missingAspects") or [])],
        )

    summary = _build_finding_summary(sub_question, combined_evidence, judge)
    return {
        "subQuestion": sub_question,
        "summary": summary,
        "verdict": str(judge.get("verdict") or "INCORRECT"),
        "missingAspects": _normalize_missing_aspects(judge.get("missingAspects")),
        "sourceIds": [str(item.get("sourceId")) for item in combined_evidence if item.get("sourceId")][:6],
    }


def _load_current_paper_documents(pdf_id: str) -> Tuple[List[Dict[str, Any]], str]:
    normalized_id = get_rag().normalize_id(pdf_id)
    documents = get_rag().get_documents_by_metadata({"id": normalized_id}, limit=120)
    normalized = normalize_evidence_items(
        documents,
        source_type="current_paper",
        pdf_id=normalized_id,
        limit=80,
        max_text_chars=900,
    )
    return _ensure_stable_source_ids(normalized, fallback_prefix=normalized_id or "current-paper"), normalized_id


def _build_research_plan(
    question: str,
    paper_skeleton: Dict[str, Any],
    documents: List[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    fallback_brief, fallback_sub_questions = _fallback_plan(question)
    prompt = f"""
You are planning a deep research task for an academic paper assistant.
Return valid JSON only.

JSON shape:
{{
  "brief": "short Chinese research brief",
  "subQuestions": ["子问题 1", "子问题 2", "子问题 3"]
}}

Rules:
- Focus on the current paper first.
- Produce 3 to 5 Chinese sub-questions.
- Keep each sub-question concrete and answerable with current-paper evidence plus optional library supplements.
- Do not mention web search, agents, or external browsing.

Main question:
{question}

Paper skeleton:
{_stringify_paper_skeleton(paper_skeleton)}

Current paper evidence:
{format_evidence_context(documents, title="当前论文线索", max_items=4, max_text_chars=260)}
"""

    try:
        payload = parse_json_from_llm(get_llm()._call(prompt))
        brief = _clean_text(payload.get("brief")) or fallback_brief
        sub_questions = _normalize_sub_questions(payload.get("subQuestions"), fallback_sub_questions)
        return brief, sub_questions
    except Exception as error:
        print(f"research task planner fell back to heuristic plan: {error}")
        return fallback_brief, fallback_sub_questions


def _retrieve_current_paper_evidence(query: str, pdf_id: str, top_k: int = 8, limit: int = 5) -> List[Dict[str, Any]]:
    results = get_rag().retrieve(query, top_k=top_k, filter_metadata={"id": pdf_id})
    normalized = normalize_evidence_items(
        results,
        source_type="current_paper",
        pdf_id=pdf_id,
        limit=limit,
        max_text_chars=700,
    )
    return _ensure_stable_source_ids(normalized, fallback_prefix=pdf_id or "current-paper")


def _retrieve_library_evidence(query: str, exclude_pdf_id: str | None = None, top_k: int = 5, limit: int = 4) -> List[Dict[str, Any]]:
    hybrid_results = retrieve_hybrid_results(query, top_k=top_k)
    vector = hybrid_results.get("vector", []) if isinstance(hybrid_results, dict) else []
    bm25 = hybrid_results.get("bm25", []) if isinstance(hybrid_results, dict) else []
    normalized = normalize_evidence_items([*vector, *bm25], source_type="library", limit=limit * 2, max_text_chars=700)

    filtered: List[Dict[str, Any]] = []
    seen = set()
    normalized_exclude = get_rag().normalize_id(exclude_pdf_id) if exclude_pdf_id else None
    for item in _ensure_stable_source_ids(normalized, fallback_prefix="library"):
        item_pdf_id = get_rag().normalize_id(item.get("pdfId")) if item.get("pdfId") else None
        if normalized_exclude and item_pdf_id == normalized_exclude:
            continue
        key = (str(item.get("sourceId") or ""), str(item.get("text") or "")[:120])
        if key in seen:
            continue
        seen.add(key)
        filtered.append(item)
        if len(filtered) >= limit:
            break
    return filtered


def _merge_evidence_lists(*groups: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for group in groups:
        for item in group or []:
            normalized = normalize_evidence_items([item], limit=1, max_text_chars=700)
            if not normalized:
                continue
            current = _ensure_stable_source_ids(normalized, fallback_prefix="source")[0]
            key = (str(current.get("sourceId") or ""), str(current.get("text") or "")[:180])
            if key in seen:
                continue
            seen.add(key)
            merged.append(current)
            if len(merged) >= limit:
                return merged
    return merged


def _ensure_stable_source_ids(items: List[Dict[str, Any]], fallback_prefix: str) -> List[Dict[str, Any]]:
    stabilized: List[Dict[str, Any]] = []
    for index, item in enumerate(items or []):
        current = copy.deepcopy(item)
        base = str(current.get("sourceId") or "").strip()
        if not base or base.startswith("source-"):
            pdf_id = _slugify(current.get("pdfId") or fallback_prefix or "source")
            chunk_index = current.get("chunkIndex")
            if chunk_index is not None:
                base = f"{pdf_id}-chunk-{chunk_index}"
            else:
                base = f"{pdf_id}-{index + 1}"
        current["sourceId"] = base[:80]
        stabilized.append(current)
    return stabilized


def _build_retry_query(sub_question: str, query_plan: Dict[str, Any], judge_result: Dict[str, Any]) -> str:
    parts = [
        query_plan.get("original") or sub_question,
        query_plan.get("rewritten") or "",
        *(query_plan.get("keywords") or []),
        *(judge_result.get("missingAspects") or []),
    ]

    unique_parts = []
    seen = set()
    for part in parts:
        text = _clean_text(part)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_parts.append(text)
    return " ".join(unique_parts)[:500] or sub_question


def _build_finding_summary(sub_question: str, evidence: List[Dict[str, Any]], judge_result: Dict[str, Any]) -> str:
    verdict = str(judge_result.get("verdict") or "INCORRECT")
    missing_aspects = _normalize_missing_aspects(judge_result.get("missingAspects"))
    preview = _evidence_preview(evidence)
    if verdict == "CORRECT":
        return f"围绕“{sub_question}”，现有证据基本充分。关键信息包括：{preview or '已检索到可支撑回答的当前论文或补充文献证据。'}"
    if verdict == "AMBIGUOUS":
        suffix = f"；但仍缺少 {', '.join(missing_aspects)} 等关键信息" if missing_aspects else "；但关键论证仍不够完整"
        return f"围绕“{sub_question}”，现有证据部分相关。已观察到：{preview or '检索到了部分线索'}{suffix}。"
    if missing_aspects:
        return f"围绕“{sub_question}”，当前证据不足，仍缺少 {', '.join(missing_aspects)} 等直接依据。"
    return f"围绕“{sub_question}”，当前没有检索到足够直接的证据。"


def _build_research_report(
    question: str,
    brief: str,
    sub_questions: List[str],
    findings: List[Dict[str, Any]],
) -> str:
    lines = [
        "## 研究 brief",
        brief,
        "",
        "## 子问题结论",
    ]

    for index, finding in enumerate(findings, start=1):
        lines.extend([
            f"### {index}. {finding.get('subQuestion')}",
            f"- 结论：{finding.get('summary')}",
            f"- 证据判断：{finding.get('verdict')}",
            f"- 证据来源：{', '.join(finding.get('sourceIds') or []) or '未检索到稳定证据来源'}",
        ])
        if finding.get("missingAspects"):
            lines.append(f"- 缺失点：{', '.join(finding.get('missingAspects') or [])}")
        lines.append("")

    lines.extend([
        "## 综合判断",
        _overall_assessment(question, findings, planned_count=len(sub_questions)),
        "",
        "## 证据不足与后续建议",
        _next_steps(findings),
    ])
    return "\n".join(line for line in lines if line is not None).strip()


def _overall_assessment(question: str, findings: List[Dict[str, Any]], planned_count: int) -> str:
    supported = [item for item in findings if item.get("verdict") == "CORRECT"]
    partial = [item for item in findings if item.get("verdict") == "AMBIGUOUS"]
    insufficient = [item for item in findings if item.get("verdict") == "INCORRECT"]
    return (
        f"围绕“{question}”，本次任务共规划 {planned_count} 个子问题，"
        f"其中证据充足 {len(supported)} 项，部分相关 {len(partial)} 项，证据不足 {len(insufficient)} 项。"
        " 当前结论优先依据当前论文，必要时参考了内部文献库补充线索；对证据不足的部分不应当作论文已经证明的事实。"
    )


def _next_steps(findings: List[Dict[str, Any]]) -> str:
    missing_lines = []
    for finding in findings:
        missing = _normalize_missing_aspects(finding.get("missingAspects"))
        if not missing:
            continue
        missing_lines.append(f"- {finding.get('subQuestion')}：优先补查 {', '.join(missing[:3])}")

    if not missing_lines:
        return "- 当前主要子问题都已形成可追溯结论；后续可在模块 8B 中直接展示这些 findings 与报告。"

    missing_lines.append("- 如果后续需要更完整的研究报告，可在模块 8B 增加任务面板并展示逐项 findings。")
    return "\n".join(missing_lines)


def _should_try_library(judge_result: Dict[str, Any]) -> bool:
    return str(judge_result.get("verdict") or "") != "CORRECT" or float(judge_result.get("confidence") or 0) < 0.68


def _should_retry(judge_result: Dict[str, Any]) -> bool:
    return bool(judge_result.get("shouldRetry")) and (
        str(judge_result.get("verdict") or "") != "CORRECT" or float(judge_result.get("confidence") or 0) < 0.68
    )


def _fallback_plan(question: str) -> Tuple[str, List[str]]:
    normalized_question = _clean_text(question) or "当前研究问题"
    return (
        f"围绕“{normalized_question}”，优先核对当前论文中的研究目标、方法证据、实验支撑与结论边界，再用内部文献库补充缺口。",
        [
            f"这篇论文针对“{normalized_question}”想解决的核心研究问题与研究目标是什么？",
            f"当前论文中有哪些方法、机制或流程证据可以直接支撑“{normalized_question}”？",
            f"实验结果、评价指标和已披露局限对“{normalized_question}”提供了哪些支持或边界？",
        ],
    )


def _build_planning_context(question: str, paper_skeleton: Dict[str, Any], documents: List[Dict[str, Any]]) -> str:
    skeleton_text = _stringify_paper_skeleton(paper_skeleton)
    evidence_text = format_evidence_context(documents, title="当前论文证据", max_items=4, max_text_chars=260)
    return (
        f"Main question: {question}\n"
        f"Paper skeleton:\n{skeleton_text[:1200]}\n"
        f"{evidence_text[:1800]}"
    )


def _stringify_paper_skeleton(paper_skeleton: Dict[str, Any]) -> str:
    if not isinstance(paper_skeleton, dict) or not paper_skeleton:
        return ""

    lines = []
    for key, value in paper_skeleton.items():
        text = _clean_text(value)
        if not text:
            continue
        lines.append(f"{key}: {text[:220]}")
        if len(lines) >= 6:
            break
    return "\n".join(lines)


def _normalize_sub_questions(value: Any, fallback: List[str]) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [line.strip("-* 0123456789.、 \t") for line in value.splitlines()]
    else:
        raw_items = []

    questions = []
    seen = set()
    for item in raw_items:
        text = _clean_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(text[:140])
        if len(questions) >= 5:
            break

    if len(questions) < 3:
        for extra in fallback:
            text = _clean_text(extra)
            if not text or text.lower() in seen:
                continue
            questions.append(text[:140])
            seen.add(text.lower())
            if len(questions) >= 3:
                break

    return questions[:5]


def _normalize_missing_aspects(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items = []
    seen = set()
    for raw_item in value:
        text = _clean_text(raw_item)
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


def _evidence_preview(evidence: List[Dict[str, Any]]) -> str:
    snippets = []
    for item in evidence[:2]:
        text = _clean_text(item.get("text"))
        if text:
            snippets.append(text[:100])
    return "；".join(snippets)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.strip("-") or "source"


def _copy_task_snapshot(task_id: str) -> Dict[str, Any]:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise ResearchTaskNotFoundError("Research task not found.")
        return copy.deepcopy(task)


def _copy_task_context(task_id: str) -> Dict[str, Any]:
    with _TASK_LOCK:
        return copy.deepcopy(_TASK_CONTEXTS.get(task_id) or {})


def _update_task_snapshot(task_id: str, **updates: Any) -> Dict[str, Any]:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise ResearchTaskNotFoundError("Research task not found.")
        if str(task.get("status") or "") == "cancelled" and updates.get("status") != "cancelled":
            return copy.deepcopy(task)

        updated = {
            **task,
            **copy.deepcopy(updates),
        }
        _TASKS[task_id] = updated
        return copy.deepcopy(updated)


def _fail_task(task_id: str, error_message: str) -> None:
    _update_task_snapshot(
        task_id,
        status="failed",
        stage=DONE_STAGE,
        error=_clean_text(error_message)[:240] or "Research task failed.",
    )


def _is_cancelled(task_id: str) -> bool:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        return task_id in _TASK_CANCELLATIONS or str((task or {}).get("status") or "") == "cancelled"
