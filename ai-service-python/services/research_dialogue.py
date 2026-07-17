"""Interactive research dialogue — agent can ask clarifying questions mid-research.

When evidence is ambiguous or conflicting, the agent generates targeted
clarification questions and incorporates user feedback.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

LLM_TIMEOUT = 20
MAX_QUESTIONS = 3
MAX_ROUNDS = 3


# ── Public API ───────────────────────────────────────────────────────────────

def generate_clarification_question(
    question: str,
    findings: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    gaps: list[str] | None = None,
    round_number: int = 1,
) -> dict[str, Any]:
    """Generate 1-2 high-value clarification questions based on current state.

    Returns ``{status, questions, error}``.
    """
    if round_number > MAX_ROUNDS:
        return {"status": "success", "questions": [], "roundNumber": round_number, "error": ""}

    findings_str = _format_findings(findings or [])
    conflicts_str = _format_conflicts(conflicts or [])
    gaps_str = ", ".join(gaps or []) or "无特定缺口"

    try:
        from llm.client import get_llm

        prompt = (
            f"研究问题：{question}\n\n"
            f"当前发现：\n{findings_str}\n\n"
            f"争议：\n{conflicts_str}\n\n"
            f"证据缺口：{gaps_str}\n\n"
            "基于当前研究状态，请生成 1-2 个最有价值的追问来帮助聚焦研究方向。"
            "追问应针对：1) 歧义澄清 2) 方向选择 3) 范围界定。\n"
            "用 JSON 数组回复：[{\"question\": \"...\", \"context\": \"为什么需要问这个\"}]"
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            raw = future.result(timeout=LLM_TIMEOUT)
    except Exception:
        return _fallback_questions(findings, gaps)

    try:
        text = raw.strip().split("```json")[-1].split("```")[0].strip()
        qs = json.loads(text)
        questions = [
            {"question": str(q.get("question", ""))[:300],
             "context": str(q.get("context", ""))[:200]}
            for q in qs[:MAX_QUESTIONS] if q.get("question")
        ]
        return {"status": "success", "questions": questions, "roundNumber": round_number, "error": ""}
    except (json.JSONDecodeError, TypeError, ValueError):
        return _fallback_questions(findings, gaps)


def incorporate_user_feedback(
    question: str,
    user_answer: str,
    current_direction: str = "",
) -> dict[str, Any]:
    """Incorporate user feedback into a refined research direction.

    Returns ``{status, refinedDirection, refinedQueries, error}``.
    """
    if not user_answer or not user_answer.strip():
        return _error("User answer cannot be empty.")

    try:
        from llm.client import get_llm

        prompt = (
            f"原始研究问题：{question}\n"
            f"当前方向：{current_direction or '未指定'}\n"
            f"用户反馈：{user_answer}\n\n"
            "基于用户反馈，请输出：\n"
            "1) refinedDirection: 调整后的研究方向（一句话）\n"
            "2) refinedQueries: 2-3 个调整后的搜索关键词\n"
            "用 JSON 回复：{\"refinedDirection\": \"...\", \"refinedQueries\": [\"...\"]}"
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            raw = future.result(timeout=LLM_TIMEOUT)
        data = json.loads(raw.strip().split("```json")[-1].split("```")[0].strip())
        return {
            "status": "success",
            "refinedDirection": str(data.get("refinedDirection", ""))[:300],
            "refinedQueries": [str(q)[:200] for q in data.get("refinedQueries", [])[:3]],
            "error": "",
        }
    except Exception:
        return {
            "status": "success",
            "refinedDirection": f"根据反馈调整：{user_answer[:200]}",
            "refinedQueries": [user_answer[:150]],
            "error": "",
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "尚无明确发现"
    lines = []
    for f in findings[:6]:
        summary = f.get("summary") or f.get("subQuestion") or ""
        verdict = f.get("verdict", "?")
        lines.append(f"- [{verdict}] {summary[:200]}")
    return "\n".join(lines)


def _format_conflicts(conflicts: list[dict[str, Any]]) -> str:
    if not conflicts:
        return "无争议"
    return "\n".join(
        f"- {c.get('claim', c.get('topic', ''))[:200]}" for c in conflicts[:4]
    )


def _fallback_questions(
    findings: list[dict[str, Any]] | None, gaps: list[str] | None,
) -> dict[str, Any]:
    qs = []
    if gaps:
        qs.append({"question": f"关于「{gaps[0][:100]}」方面，是否有特定的子方向需要优先探索？", "context": "证据缺口"})
    if findings and len(findings) < 3:
        qs.append({"question": "当前证据较少，是否需要扩大搜索范围或包含相邻领域？", "context": "证据稀疏"})
    return {"status": "success", "questions": qs, "roundNumber": 1, "error": ""}


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "refinedDirection": "", "refinedQueries": [], "error": message}
