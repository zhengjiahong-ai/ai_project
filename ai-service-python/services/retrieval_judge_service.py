import logging
import math
from typing import Any, Dict, List, Optional

from llm.client import get_llm
from services.evidence_service import normalize_evidence_items

_logger = logging.getLogger(__name__)
from services.utils import parse_json_from_llm


VALID_VERDICTS = {"CORRECT", "AMBIGUOUS", "INCORRECT"}

SOURCE_TRUST_WEIGHTS = {
    "current_paper": 1.0,
    "library": 0.85,
    "external_academic": 0.65,
    "web_search": 0.45,
    "web_page": 0.40,
}
SOURCE_TRUST_DEFAULT = 0.30


def judge_evidence_quality(
    question: str,
    evidence_items: Any,
    keywords: Optional[List[str]] = None,
    use_llm: bool = False,
) -> Dict[str, Any]:
    heuristic = _heuristic_judge(question, evidence_items, keywords=keywords)
    if not use_llm:
        return heuristic

    try:
        return _llm_judge(question, evidence_items, keywords=keywords, fallback=heuristic)
    except Exception as error:
        _logger.warning("LLM retrieval judge fell back to heuristic: %s", error)
        return heuristic


def _heuristic_judge(question: str, evidence_items: Any, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    evidence = normalize_evidence_items(evidence_items, limit=8, max_text_chars=900)
    keyword_terms = _normalize_terms(keywords) or _fallback_terms(question)
    if not evidence:
        return _result(
            verdict="INCORRECT",
            confidence=0.12,
            reason="没有检索到可用证据片段。",
            missing_aspects=_missing_aspects(keyword_terms, [], default="可用证据"),
            coverage=_build_coverage([], keyword_terms, []),
        )

    evidence_text = "\n".join(item.get("text", "") for item in evidence if item.get("text"))
    total_length = len(evidence_text)
    matched_terms = _matched_terms(keyword_terms, evidence_text)
    coverage_payload = _build_coverage(evidence, keyword_terms, matched_terms)
    coverage = coverage_payload["score"]
    best_similarity = _best_number(evidence, "similarity")
    best_score = _best_number(evidence, "score")

    if total_length < 80 and coverage < 0.25 and (best_similarity is None or best_similarity < 0.55):
        return _result(
            verdict="INCORRECT",
            confidence=0.28,
            reason="证据片段过短，且未覆盖主要检索关键词。",
            missing_aspects=_missing_aspects(keyword_terms, matched_terms),
            coverage=coverage_payload,
        )

    if best_similarity is not None and best_similarity >= 0.85 and total_length >= 30:
        return _result(
            verdict="CORRECT",
            confidence=max(0.72, min(0.95, best_similarity)),
            reason="检索结果与问题高度相似，可支撑回答。",
            missing_aspects=[],
            coverage=coverage_payload,
        )

    if coverage >= 0.6 and total_length >= 40:
        return _result(
            verdict="CORRECT",
            confidence=0.72,
            reason="证据覆盖了主要检索关键词，可支撑回答。",
            missing_aspects=[],
            coverage=coverage_payload,
        )

    confidence = 0.25
    confidence += min(len(evidence), 4) * 0.06
    confidence += min(total_length / 1600, 1.0) * 0.2
    confidence += coverage * 0.25

    if best_similarity is not None:
        if best_similarity >= 0.75:
            confidence += 0.18
        elif best_similarity >= 0.55:
            confidence += 0.1
        else:
            confidence += 0.04
    elif best_score is not None and best_score > 0:
        confidence += 0.08

    confidence = min(0.95, max(0.0, confidence))
    if confidence >= 0.68:
        return _result(
            verdict="CORRECT",
            confidence=confidence,
            reason="证据数量、文本长度和关键词覆盖整体足够。",
            missing_aspects=[],
            coverage=coverage_payload,
        )
    if confidence > 0.35:
        return _result(
            verdict="AMBIGUOUS",
            confidence=confidence,
            reason="证据部分相关，但覆盖还不够完整。",
            missing_aspects=_missing_aspects(keyword_terms, matched_terms),
            coverage=coverage_payload,
        )
    return _result(
        verdict="INCORRECT",
        confidence=confidence,
        reason="证据相关性和覆盖度不足。",
        missing_aspects=_missing_aspects(keyword_terms, matched_terms),
        coverage=coverage_payload,
    )


def _llm_judge(
    question: str,
    evidence_items: Any,
    keywords: Optional[List[str]],
    fallback: Dict[str, Any],
) -> Dict[str, Any]:
    evidence = normalize_evidence_items(evidence_items, limit=5, max_text_chars=600)
    evidence_text = "\n\n".join(
        f"{item.get('sourceId')}: {item.get('text', '')}"
        for item in evidence
    )
    prompt = f"""
You are judging whether retrieved academic evidence is sufficient to answer a user question.
Return valid JSON only with this shape:
{{
  "verdict": "CORRECT|AMBIGUOUS|INCORRECT",
  "confidence": 0.0,
  "reason": "short reason",
  "missingAspects": ["short missing aspect"],
  "shouldRetry": true,
  "reflection": "已确认 X 和 Y，仍不确定 Z。为验证 Z 需要查找 ____。当前证据矛盾在于 ____。",
  "suggestedQueries": ["precise search keyword combination 1", "precise search keyword combination 2"]
}}

The "reflection" field must follow this format in Chinese:
- Start with what is confirmed (已确认...)
- Then state what remains uncertain (仍不确定...)
- Then state what evidence is needed to resolve the uncertainty (为验证...需要查找...)
- Finally note any contradictions in current evidence (当前证据矛盾在于...)
- If evidence is empty, write "无可用证据，无法进行反思。"

The "suggestedQueries" field must contain 0-3 precise search keyword combinations
(not full sentences) optimized for academic/web search to fill the knowledge gaps.
Each query should be ≤200 characters. Leave empty if no further search is needed.

Question:
{question}

Keywords:
{", ".join(_normalize_terms(keywords))}

Evidence:
{evidence_text}
"""
    payload = parse_json_from_llm(get_llm()._call(prompt))
    verdict = str(payload.get("verdict") or "").strip().upper()
    if verdict not in VALID_VERDICTS:
        return fallback

    confidence = _clamp_confidence(payload.get("confidence"), fallback["confidence"])
    missing_aspects = payload.get("missingAspects") if isinstance(payload.get("missingAspects"), list) else []
    reason = str(payload.get("reason") or fallback["reason"]).strip()[:240]
    should_retry = bool(payload.get("shouldRetry")) if "shouldRetry" in payload else verdict != "CORRECT"
    coverage = _build_coverage(
        evidence,
        _normalize_terms(keywords) or _fallback_terms(question),
        _matched_terms(_normalize_terms(keywords) or _fallback_terms(question), "\n".join(item.get("text", "") for item in evidence)),
    )

    # Extract new reflection fields from LLM response
    reflection = str(payload.get("reflection") or "").strip()[:400]
    suggested_queries_raw = payload.get("suggestedQueries")
    if isinstance(suggested_queries_raw, list):
        suggested_queries = [
            str(q).strip()[:200]
            for q in suggested_queries_raw
            if str(q).strip()
        ][:3]
    else:
        suggested_queries = []

    return _result(
        verdict=verdict,
        confidence=confidence,
        reason=reason,
        missing_aspects=[str(item).strip()[:80] for item in missing_aspects if str(item).strip()][:6],
        should_retry=should_retry,
        coverage=coverage,
        reflection=reflection,
        suggested_queries=suggested_queries,
    )


def _result(
    verdict: str,
    confidence: float,
    reason: str,
    missing_aspects: Optional[List[str]] = None,
    should_retry: Optional[bool] = None,
    coverage: Optional[Dict[str, Any]] = None,
    reflection: str = "",
    suggested_queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    normalized_verdict = verdict if verdict in VALID_VERDICTS else "INCORRECT"
    normalized_confidence = round(max(0.0, min(1.0, float(confidence))), 2)
    normalized_missing = missing_aspects or []
    normalized_should_retry = normalized_verdict != "CORRECT" if should_retry is None else bool(should_retry)
    normalized_coverage = _normalize_coverage(coverage)
    normalized_reflection = str(reflection or "").strip()[:400]
    normalized_suggested_queries = suggested_queries if isinstance(suggested_queries, list) else []
    normalized_suggested_queries = [
        str(q).strip()[:200]
        for q in normalized_suggested_queries
        if str(q).strip()
    ][:3]
    return {
        "verdict": normalized_verdict,
        "confidence": normalized_confidence,
        "reason": reason[:240],
        "missingAspects": normalized_missing,
        "shouldRetry": normalized_should_retry,
        "judgeScore": _judge_score(normalized_verdict, normalized_confidence, normalized_coverage),
        "coverage": normalized_coverage,
        "retryReason": _retry_reason(normalized_should_retry, normalized_missing, reason),
        "reflection": normalized_reflection,
        "suggestedQueries": normalized_suggested_queries,
    }


def _build_coverage(evidence: List[Dict[str, Any]], terms: List[str], matched_terms: List[str]) -> Dict[str, Any]:
    source_types = []
    seen_source_types = set()
    source_type_counts: Dict[str, int] = {}
    for item in evidence:
        source_type = str(item.get("sourceType") or "").strip()
        if not source_type:
            continue
        if source_type not in seen_source_types:
            seen_source_types.add(source_type)
            source_types.append(source_type[:80])
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1

    total_aspects = len(terms)
    matched_aspects = len({term.lower() for term in matched_terms})
    score = matched_aspects / total_aspects if total_aspects else (0.5 if evidence else 0.0)

    # sourceDiversityScore (Shannon diversity index, normalized 0-1)
    total_count = sum(source_type_counts.values())
    source_diversity = _compute_shannon_diversity(source_type_counts, total_count)

    # sourceTrustWeightedScore
    source_trust = _compute_source_trust_weighted(source_type_counts, total_count)

    # crossSourceAgreement
    cross_agreement = _compute_cross_source_agreement(evidence, source_type_counts)

    return {
        "score": round(max(0.0, min(1.0, score)), 2),
        "matchedAspects": matched_aspects,
        "totalAspects": total_aspects,
        "evidenceCount": len(evidence),
        "sourceTypes": source_types,
        "sourceDiversityScore": round(max(0.0, min(1.0, source_diversity)), 4),
        "sourceTrustWeightedScore": round(max(0.0, min(1.0, source_trust)), 4),
        "crossSourceAgreement": cross_agreement,
    }


def _compute_shannon_diversity(source_type_counts: Dict[str, int], total_count: int) -> float:
    if total_count == 0:
        return 0.0
    entropy = 0.0
    for count in source_type_counts.values():
        if count > 0:
            p = count / total_count
            entropy -= p * math.log(p)
    n = len(source_type_counts)
    if n <= 1:
        return 0.0
    max_entropy = math.log(n)
    if max_entropy == 0:
        return 0.0
    return entropy / max_entropy


def _compute_source_trust_weighted(source_type_counts: Dict[str, int], total_count: int) -> float:
    if total_count == 0:
        return 0.0
    weighted_sum = 0.0
    for source_type, count in source_type_counts.items():
        weight = SOURCE_TRUST_WEIGHTS.get(source_type, SOURCE_TRUST_DEFAULT)
        weighted_sum += weight * count
    return weighted_sum / total_count


def _compute_cross_source_agreement(
    evidence: List[Dict[str, Any]], source_type_counts: Dict[str, int]
) -> Optional[float]:
    unique_types = len(source_type_counts)
    if unique_types <= 1:
        return None

    # Extract meaningful text tokens per source type
    source_texts: Dict[str, str] = {}
    for item in evidence:
        source_type = str(item.get("sourceType") or "").strip()
        if not source_type:
            continue
        text = str(item.get("text") or "")
        source_texts[source_type] = source_texts.get(source_type, "") + " " + text

    # Build keyword sets per source type
    source_keyword_sets: Dict[str, set] = {}
    for source_type, text in source_texts.items():
        tokens = set(token.lower() for token in text.split() if len(token) >= 3)
        if tokens:
            source_keyword_sets[source_type] = tokens

    if len(source_keyword_sets) <= 1:
        return None

    # Count how many source types share keywords with at least one other
    agreeing_types = 0
    source_list = list(source_keyword_sets.keys())
    for i, source_a in enumerate(source_list):
        tokens_a = source_keyword_sets[source_a]
        has_overlap = False
        for j, source_b in enumerate(source_list):
            if i == j:
                continue
            tokens_b = source_keyword_sets[source_b]
            overlap = len(tokens_a & tokens_b)
            if overlap >= 2:  # at least 2 shared keywords
                has_overlap = True
                break
        if has_overlap:
            agreeing_types += 1

    return round(agreeing_types / len(source_list), 4)


def _normalize_coverage(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    coverage = value if isinstance(value, dict) else {}
    return {
        "score": round(max(0.0, min(1.0, _coerce_float(coverage.get("score"), 0.0))), 2),
        "matchedAspects": max(0, _coerce_int(coverage.get("matchedAspects"), 0)),
        "totalAspects": max(0, _coerce_int(coverage.get("totalAspects"), 0)),
        "evidenceCount": max(0, _coerce_int(coverage.get("evidenceCount"), 0)),
        "sourceTypes": [
            str(item).strip()[:80]
            for item in (coverage.get("sourceTypes") if isinstance(coverage.get("sourceTypes"), list) else [])
            if str(item).strip()
        ][:6],
        "sourceDiversityScore": _coerce_float_or_none(coverage.get("sourceDiversityScore")),
        "sourceTrustWeightedScore": _coerce_float_or_none(coverage.get("sourceTrustWeightedScore")),
        "crossSourceAgreement": _coerce_float_or_none(coverage.get("crossSourceAgreement")),
    }


def _judge_score(verdict: str, confidence: float, coverage: Dict[str, Any]) -> int:
    verdict_bonus = {"CORRECT": 16, "AMBIGUOUS": 4, "INCORRECT": -8}.get(verdict, -8)
    source_diversity = _coerce_float(coverage.get("sourceDiversityScore"), 0.0)
    source_trust = _coerce_float(coverage.get("sourceTrustWeightedScore"), SOURCE_TRUST_DEFAULT)
    cross_agreement = _coerce_float(coverage.get("crossSourceAgreement"), 0.0)
    raw_score = (
        confidence * 55
        + float(coverage.get("score") or 0) * 15
        + source_diversity * 8
        + source_trust * 8
        + cross_agreement * 6
        + verdict_bonus
    )
    return int(round(max(0, min(100, raw_score))))


def _retry_reason(should_retry: bool, missing_aspects: List[str], reason: str) -> str:
    if not should_retry:
        return ""
    if missing_aspects:
        return f"证据覆盖不足，仍缺少：{', '.join(missing_aspects[:3])}"[:240]
    return str(reason or "证据质量不足，需要补充检索。")[:240]


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_terms(value: Any) -> List[str]:
    if isinstance(value, str):
        raw_terms = [item.strip() for item in value.replace("，", ",").split(",")]
    elif isinstance(value, list):
        raw_terms = [str(item).strip() for item in value]
    else:
        raw_terms = []

    terms = []
    seen = set()
    for term in raw_terms:
        cleaned = " ".join(term.strip(" \t\r\n,.;:，。；：、").split())
        if not cleaned or len(cleaned) < 2:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(cleaned)
        if len(terms) >= 8:
            break
    return terms


def _fallback_terms(question: str) -> List[str]:
    text = str(question or "")
    for separator in ",.;:，。；：、()[]{}<>《》/\\|!?！？\n\t'\"":
        text = text.replace(separator, " ")
    return _normalize_terms([token for token in text.split() if len(token) >= 2])


def _matched_terms(terms: List[str], text: str) -> List[str]:
    lowered = str(text or "").lower()
    return [
        term
        for term in terms
        if term.lower() in lowered
    ]


def _missing_aspects(terms: Optional[List[str]], matched_terms: List[str], default: str = "更多相关证据") -> List[str]:
    normalized_terms = _normalize_terms(terms)
    matched = {term.lower() for term in matched_terms}
    missing = [
        term
        for term in normalized_terms
        if term.lower() not in matched
    ][:5]
    return missing or [default]


def _best_number(evidence: List[Dict[str, Any]], field: str) -> Optional[float]:
    values = [
        item.get(field)
        for item in evidence
        if isinstance(item.get(field), (int, float))
    ]
    return max(values) if values else None


def _clamp_confidence(value: Any, fallback: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return float(fallback)
