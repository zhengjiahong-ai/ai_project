"""Advanced analysis tools for agent outputs.

Runs adversarial review, hypothesis generation, meta-analysis,
conflict adjudication, and cross-lingual search on agent findings.
"""

from typing import Any


def run_advanced_analysis(
    prompt: str,
    paper_ids: list[str],
    evidence_items: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    open_questions: list[str],
) -> dict[str, Any]:
    """Run optional advanced analysis tools on agent outputs.

    Returns a dict with keys for each analysis domain, or empty dict on failure.
    Each value is the structured result that frontend cards can render directly.
    """
    result: dict[str, Any] = {}

    # 1. Adversarial review of findings
    if findings and evidence_items:
        try:
            from services.adversarial_reviewer import adversarial_review

            adv_result = adversarial_review(
                question=prompt,
                findings=findings[:4],
                evidence_items=evidence_items[:8],
                conflicts=conflicts[:3],
            )
            if adv_result and adv_result.get("status") == "success":
                result["adversarialReview"] = adv_result
        except Exception:
            pass

    # 2. Hypothesis generation and verification
    if findings or conflicts:
        try:
            from services.hypothesis_engine import generate_and_verify_hypotheses

            hypo_result = generate_and_verify_hypotheses(
                question=prompt,
                findings=findings[:4],
                conflicts=conflicts[:3],
                gaps=open_questions[:3],
            )
            if hypo_result and hypo_result.get("status") == "success":
                result["hypotheses"] = hypo_result
        except Exception:
            pass

    # 3. Meta-analysis (only when we have numeric/quantitative evidence)
    study_items = _extract_study_items(evidence_items, findings)
    if len(study_items) >= 2:
        try:
            from services.meta_analysis import meta_analyze

            meta_result = meta_analyze(studies=study_items[:8])
            if meta_result and meta_result.get("status") == "success":
                result["metaAnalysis"] = meta_result
        except Exception:
            pass

    # 4. Conflict adjudication (per conflict)
    if conflicts:
        adjudicated = []
        for c in conflicts[:3]:
            if c.get("conflictType") == "no-major-conflict":
                continue
            try:
                from services.conflict_adjudicator import adjudicate_conflict

                pro_sources = [
                    s for s in evidence_items[:4]
                    if s.get("pdfId") in (c.get("papers") or [])[:2]
                ]
                con_sources = [
                    s for s in evidence_items[:4]
                    if s.get("pdfId") in (c.get("papers") or [])[2:]
                ]
                adj_result = adjudicate_conflict(
                    claim=c.get("claim", c.get("summary", ""))[:300],
                    proSources=pro_sources if pro_sources else evidence_items[:2],
                    conSources=con_sources if con_sources else evidence_items[2:4],
                )
                if adj_result and adj_result.get("status") == "success":
                    adjudicated.append(adj_result)
            except Exception:
                pass
        if adjudicated:
            result["conflictAdjudications"] = adjudicated

    # 5. Cross-lingual search when evidence is sparse
    if len(evidence_items) <= 4 and prompt:
        try:
            from services.cross_lingual import cross_lingual_search

            cl_result = cross_lingual_search(
                query=prompt[:200],
                languages=["zh", "en"],
                limitPerLang=3,
            )
            if cl_result and cl_result.get("status") == "success":
                result["crossLingualResults"] = cl_result
        except Exception:
            pass

    return result


def _extract_study_items(
    evidence_items: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract study-like items from evidence for meta-analysis."""
    studies = []
    for item in evidence_items:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        effect = metadata.get("effectSize") or item.get("effectSize")
        se = metadata.get("standardError") or item.get("standardError")
        n_val = metadata.get("sampleSize") or item.get("sampleSize")
        if effect is not None:
            studies.append({
                "studyId": str(item.get("sourceId") or item.get("id") or ""),
                "label": str(item.get("title") or item.get("text", ""))[:120],
                "effectSize": float(effect) if effect is not None else None,
                "standardError": float(se) if se is not None else None,
                "sampleSize": int(n_val) if n_val is not None else None,
                "year": item.get("year"),
            })
    for f in findings:
        meta_data = f.get("meta") if isinstance(f.get("meta"), dict) else {}
        effect = meta_data.get("effectSize") or f.get("effectSize")
        if effect is not None:
            studies.append({
                "studyId": str(f.get("id", "")),
                "label": str(f.get("summary", ""))[:120],
                "effectSize": float(effect),
                "standardError": meta_data.get("standardError"),
                "sampleSize": meta_data.get("sampleSize"),
                "year": None,
            })
    return studies
