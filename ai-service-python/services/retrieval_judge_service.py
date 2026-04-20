from typing import Any, Dict, List, Optional

from llm.client import get_llm
from services.evidence_service import normalize_evidence_items
from services.utils import parse_json_from_llm


VALID_VERDICTS = {"CORRECT", "AMBIGUOUS", "INCORRECT"}


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
        print(f"LLM retrieval judge fell back to heuristic: {error}")
        return heuristic


def _heuristic_judge(question: str, evidence_items: Any, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    evidence = normalize_evidence_items(evidence_items, limit=8, max_text_chars=900)
    if not evidence:
        return _result(
            verdict="INCORRECT",
            confidence=0.12,
            reason="没有检索到可用证据片段。",
            missing_aspects=_missing_aspects(keywords, [], default="可用证据"),
        )

    evidence_text = "\n".join(item.get("text", "") for item in evidence if item.get("text"))
    total_length = len(evidence_text)
    keyword_terms = _normalize_terms(keywords) or _fallback_terms(question)
    matched_terms = _matched_terms(keyword_terms, evidence_text)
    coverage = len(matched_terms) / len(keyword_terms) if keyword_terms else 0.5
    best_similarity = _best_number(evidence, "similarity")
    best_score = _best_number(evidence, "score")

    if total_length < 80 and coverage < 0.25 and (best_similarity is None or best_similarity < 0.55):
        return _result(
            verdict="INCORRECT",
            confidence=0.28,
            reason="证据片段过短，且未覆盖主要检索关键词。",
            missing_aspects=_missing_aspects(keyword_terms, matched_terms),
        )

    if best_similarity is not None and best_similarity >= 0.85 and total_length >= 30:
        return _result(
            verdict="CORRECT",
            confidence=max(0.72, min(0.95, best_similarity)),
            reason="检索结果与问题高度相似，可支撑回答。",
            missing_aspects=[],
        )

    if coverage >= 0.6 and total_length >= 40:
        return _result(
            verdict="CORRECT",
            confidence=0.72,
            reason="证据覆盖了主要检索关键词，可支撑回答。",
            missing_aspects=[],
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
        )
    if confidence > 0.35:
        return _result(
            verdict="AMBIGUOUS",
            confidence=confidence,
            reason="证据部分相关，但覆盖还不够完整。",
            missing_aspects=_missing_aspects(keyword_terms, matched_terms),
        )
    return _result(
        verdict="INCORRECT",
        confidence=confidence,
        reason="证据相关性和覆盖度不足。",
        missing_aspects=_missing_aspects(keyword_terms, matched_terms),
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
  "shouldRetry": true
}}

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

    return _result(
        verdict=verdict,
        confidence=confidence,
        reason=reason,
        missing_aspects=[str(item).strip()[:80] for item in missing_aspects if str(item).strip()][:6],
        should_retry=should_retry,
    )


def _result(
    verdict: str,
    confidence: float,
    reason: str,
    missing_aspects: Optional[List[str]] = None,
    should_retry: Optional[bool] = None,
) -> Dict[str, Any]:
    normalized_verdict = verdict if verdict in VALID_VERDICTS else "INCORRECT"
    normalized_confidence = round(max(0.0, min(1.0, float(confidence))), 2)
    return {
        "verdict": normalized_verdict,
        "confidence": normalized_confidence,
        "reason": reason[:240],
        "missingAspects": missing_aspects or [],
        "shouldRetry": normalized_verdict != "CORRECT" if should_retry is None else bool(should_retry),
    }


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
