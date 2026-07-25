"""Automated research quality evaluation framework.

Evaluates a completed research session against ground-truth answers,
scoring factual accuracy, evidence completeness, reasoning quality,
and source diversity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_BENCHMARK_DIR = Path(__file__).resolve().parent
_QUESTIONS_FILE = _BENCHMARK_DIR / "questions.json"


# ── Public API ───────────────────────────────────────────────────────────────

def load_benchmark_questions() -> list[dict[str, Any]]:
    """Load benchmark questions from the JSON fixture."""
    if _QUESTIONS_FILE.exists():
        return json.loads(_QUESTIONS_FILE.read_text(encoding="utf-8"))
    return _default_questions()


def evaluate_session(
    session_id: str = "",
    question: str = "",
    findings: list[dict[str, Any]] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate research quality against benchmark questions.

    Returns ``{status, scores, error}``.
    """
    benchmarks = load_benchmark_questions()
    matched = None
    for bq in benchmarks:
        if _overlap_score(question, bq["question"]) > 0.4:
            matched = bq
            break

    if not matched:
        return {
            "status": "success",
            "scores": {"factualAccuracy": None, "evidenceCompleteness": None,
                       "reasoningQuality": None, "sourceDiversity": None,
                       "overall": None},
            "note": "No matching benchmark question found. Scores unavailable.",
            "error": "",
        }

    findings = findings or []
    evidence = evidence_items or []
    conflicts = conflicts or []
    gt = matched

    # 1. Factual accuracy: does the conclusion align with ground truth?
    factual = _score_factual(findings, gt.get("expectedAnswer", ""))

    # 2. Evidence completeness: did we find the key citations?
    key_refs = gt.get("keyReferences", [])
    found_refs = _count_matching_refs(evidence, key_refs)
    completeness = found_refs / len(key_refs) if key_refs else 1.0

    # 3. Reasoning quality: did we identify the expected conflicts?
    reasoning = _score_reasoning(conflicts, gt.get("expectedConflicts", []))

    # 4. Source diversity: how many distinct sources?
    source_types = set(e.get("sourceType", "") for e in evidence)
    diversity = min(len(source_types) / 4.0, 1.0)

    overall = round((factual * 0.35 + completeness * 0.30 + reasoning * 0.20 + diversity * 0.15), 2)

    return {
        "status": "success",
        "sessionId": session_id,
        "matchedQuestion": matched["question"][:200],
        "scores": {
            "factualAccuracy": round(factual, 2),
            "evidenceCompleteness": round(completeness, 2),
            "reasoningQuality": round(reasoning, 2),
            "sourceDiversity": round(diversity, 2),
            "overall": overall,
        },
        "details": {
            "keyReferencesFound": f"{found_refs}/{len(key_refs)}" if key_refs else "N/A",
            "sourceTypes": list(source_types),
            "evidenceCount": len(evidence),
            "conflictCount": len(conflicts),
        },
        "error": "",
    }


# ── Scoring helpers ──────────────────────────────────────────────────────────

def _score_factual(findings: list[dict[str, Any]], expected: str) -> float:
    if not expected:
        return 0.5  # neutral
    all_text = " ".join(f.get("summary", "") for f in findings)
    return _overlap_score(all_text, expected)


def _count_matching_refs(evidence: list[dict[str, Any]], key_refs: list[str]) -> int:
    found = 0
    for ref in key_refs:
        ref_lower = ref.lower()
        for e in evidence:
            title = (e.get("title") or "").lower()
            src_id = (e.get("sourceId") or "").lower()
            if ref_lower in title or ref_lower in src_id:
                found += 1
                break
    return found


def _score_reasoning(conflicts: list[dict[str, Any]], expected_conflicts: list[str]) -> float:
    if not expected_conflicts:
        return 0.5
    conflict_text = " ".join(c.get("claim", c.get("topic", "")) for c in conflicts)
    matches = sum(1 for ec in expected_conflicts if ec.lower() in conflict_text.lower())
    return min(matches / len(expected_conflicts), 1.0)


def _overlap_score(a: str, b: str) -> float:
    words_a = set(w.lower() for w in a.split() if len(w) > 2)
    words_b = set(w.lower() for w in b.split() if len(w) > 2)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a | words_b), 1)


# ── Default questions ────────────────────────────────────────────────────────

def _default_questions() -> list[dict[str, Any]]:
    return [
        {
            "question": "Transformer 模型相比 RNN 在长序列任务上的优势是什么？",
            "expectedAnswer": "Self-attention 机制允许并行计算和直接的长距离依赖建模，避免了 RNN 的梯度消失问题。",
            "keyReferences": ["Attention Is All You Need", "Vaswani"],
            "expectedConflicts": ["Transformer vs LSTM 性能比较", "计算复杂度争议"],
            "domain": "computer_science",
        },
        {
            "question": "mRNA 疫苗相比传统疫苗的优势和风险是什么？",
            "expectedAnswer": "mRNA 疫苗开发速度快、安全性好、不整合基因组，但需要冷链运输且长期效应仍在研究。",
            "keyReferences": ["mRNA vaccine", "COVID-19", "lipid nanoparticle"],
            "expectedConflicts": ["罕见心肌炎风险", "加强针必要性"],
            "domain": "medicine",
        },
        {
            "question": "深度学习在医学影像诊断中的准确率是否超过人类医生？",
            "expectedAnswer": "在特定任务上（如胸部X光、眼底照片）DL 模型达到或超过专家水平，但泛化到新数据集时表现下降。",
            "keyReferences": ["deep learning", "medical imaging", "radiologist", "CheXNet"],
            "expectedConflicts": ["泛化能力争议", "人机协作 vs 替代"],
            "domain": "medicine",
        },
    ]
