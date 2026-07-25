"""Mini meta-analysis engine for aggregating effect sizes across studies.

Supports random-effects and fixed-effects models, heterogeneity statistics
(Q, I²), and publication bias assessment (Egger's test, funnel plot data).
"""

from __future__ import annotations

import math
from typing import Any

# ── Public API ───────────────────────────────────────────────────────────────

def meta_analyze(studies: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate effect sizes across *studies*.

    Each study dict should have:
      - ``label`` (str): study identifier
      - ``effectSize`` (float): point estimate (e.g. Hedges' g, log OR, SMD)
      - ``stdError`` (float) or ``ciLower`` + ``ciUpper`` (float): precision

    Returns ``{status, model, summary, heterogeneity, forestPlot, funnelPlot, error}``.
    """
    if not studies or not isinstance(studies, list):
        return _error("At least one study is required.")

    parsed = _parse_studies(studies)
    if len(parsed) < 2:
        return _error("Need at least 2 studies with valid effect sizes for meta-analysis.")

    # Fixed-effects: weight = 1/variance
    fixed_weights = [1.0 / max(s["variance"], 1e-10) for s in parsed]
    fixed_sum_w = sum(fixed_weights)
    fixed_es = sum(s["effectSize"] * w for s, w in zip(parsed, fixed_weights)) / fixed_sum_w
    fixed_se = math.sqrt(1.0 / fixed_sum_w)
    fixed_ci_low = fixed_es - 1.96 * fixed_se
    fixed_ci_high = fixed_es + 1.96 * fixed_se

    # Q statistic + I² heterogeneity
    q_stat = sum(w * (s["effectSize"] - fixed_es) ** 2 for s, w in zip(parsed, fixed_weights))
    df = len(parsed) - 1
    i_squared = max(0.0, (q_stat - df) / q_stat * 100) if q_stat > 0 else 0.0
    p_hetero = 1.0 - _chi2_cdf(q_stat, df) if df > 0 else 1.0

    # Random-effects (DerSimonian-Laird)
    c = fixed_sum_w - sum(w**2 for w in fixed_weights) / fixed_sum_w
    tau_squared = max(0.0, (q_stat - df) / c) if c > 0 and q_stat > df else 0.0
    re_weights = [1.0 / (s["variance"] + tau_squared) for s in parsed]
    re_sum_w = sum(re_weights)
    re_es = sum(s["effectSize"] * w for s, w in zip(parsed, re_weights)) / re_sum_w
    re_se = math.sqrt(1.0 / re_sum_w)
    re_ci_low = re_es - 1.96 * re_se
    re_ci_high = re_es + 1.96 * re_se

    # Forest plot data
    forest = []
    for s in parsed:
        se_local = math.sqrt(s["variance"])
        forest.append({
            "label": s["label"][:60],
            "effectSize": round(s["effectSize"], 4),
            "ciLower": round(s["effectSize"] - 1.96 * se_local, 4),
            "ciUpper": round(s["effectSize"] + 1.96 * se_local, 4),
            "weight": round(re_weights[parsed.index(s)] / re_sum_w * 100, 1),
        })
    forest.append({
        "label": "RE Model (Summary)",
        "effectSize": round(re_es, 4),
        "ciLower": round(re_ci_low, 4),
        "ciUpper": round(re_ci_high, 4),
        "weight": 100.0,
    })

    # Funnel plot data
    funnel = [{"effectSize": s["effectSize"], "stdError": math.sqrt(s["variance"])} for s in parsed]

    # Egger's test (simplified)
    egger = _eggers_test(parsed)

    # GRADE assessment
    grade = _grade_assessment(parsed, i_squared, len(parsed))

    return {
        "status": "success",
        "model": "random-effects",
        "summary": {
            "effectSize": round(re_es, 4),
            "ciLower": round(re_ci_low, 4),
            "ciUpper": round(re_ci_high, 4),
            "pValue": "<0.001" if abs(re_es / re_se) > 3.3 else f"{2 * (1 - _norm_cdf(abs(re_es / re_se))):.4f}",
        },
        "heterogeneity": {
            "qStatistic": round(q_stat, 2),
            "df": df,
            "iSquared": round(i_squared, 1),
            "tauSquared": round(tau_squared, 4),
            "pValue": f"{p_hetero:.4f}",
            "interpretation": "低异质性" if i_squared < 25 else ("中异质性" if i_squared < 75 else "高异质性"),
        },
        "fixedEffectModel": {
            "effectSize": round(fixed_es, 4),
            "ciLower": round(fixed_ci_low, 4),
            "ciUpper": round(fixed_ci_high, 4),
        },
        "forestPlot": forest,
        "funnelPlot": funnel,
        "eggersTest": egger,
        "gradeAssessment": grade,
        "studyCount": len(parsed),
        "error": "",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_studies(studies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = []
    for i, s in enumerate(studies):
        if not isinstance(s, dict):
            continue
        es = _safe_float(s.get("effectSize") or s.get("effect_size"))
        if es is None:
            continue
        se = _safe_float(s.get("stdError") or s.get("std_error") or s.get("se"))
        ci_low = _safe_float(s.get("ciLower") or s.get("ci_lower"))
        ci_high = _safe_float(s.get("ciUpper") or s.get("ci_upper"))
        if se is None and ci_low is not None and ci_high is not None:
            se = (ci_high - ci_low) / (2 * 1.96)
        if se is None or se <= 0:
            se = 0.1  # fallback
        parsed.append({
            "label": s.get("label", f"Study {i+1}"),
            "effectSize": es,
            "variance": se ** 2,
        })
    return parsed


def _eggers_test(studies: list[dict[str, Any]]) -> dict[str, Any]:
    """Simplified Egger's regression test for funnel plot asymmetry."""
    n = len(studies)
    if n < 3:
        return {"intercept": 0, "pValue": "N/A", "asymmetric": False, "interpretation": "样本量不足，无法评估发表偏倚"}

    # Precision = 1/SE, SND = ES/SE
    precisions = [1.0 / math.sqrt(s["variance"]) for s in studies]
    snds = [s["effectSize"] * p for s, p in zip(studies, precisions)]

    # Simple linear regression: SND = a + b * precision
    mean_p = sum(precisions) / n
    mean_s = sum(snds) / n
    num = sum((p - mean_p) * (s - mean_s) for p, s in zip(precisions, snds))
    den = sum((p - mean_p) ** 2 for p in precisions)
    if den == 0:
        return {"intercept": 0, "pValue": "N/A", "asymmetric": False, "interpretation": "无法计算"}
    slope = num / den
    intercept = mean_s - slope * mean_p

    # SE of intercept
    residuals = [s - (intercept + slope * p) for s, p in zip(snds, precisions)]
    residual_se = math.sqrt(sum(r**2 for r in residuals) / (n - 2)) if n > 2 else 1.0
    intercept_se = residual_se * math.sqrt(1/n + mean_p**2 / den)
    t_stat = intercept / intercept_se if intercept_se > 0 else 0
    p_val = 2 * (1 - _norm_cdf(abs(t_stat)))

    asymmetric = p_val < 0.10
    return {
        "intercept": round(intercept, 3),
        "se": round(intercept_se, 3),
        "tStatistic": round(t_stat, 3),
        "pValue": f"{p_val:.4f}",
        "asymmetric": asymmetric,
        "interpretation": "可能存在发表偏倚" if asymmetric else "未检测到显著发表偏倚",
    }


def _grade_assessment(studies: list[dict[str, Any]], i_squared: float, n: int) -> dict[str, Any]:
    """Simplified GRADE evidence quality assessment."""
    score = 4  # start high (RCT/default)
    if i_squared > 50:
        score -= 1  # inconsistency
    if n < 3:
        score -= 1  # imprecision (small sample)
    if n < 5:
        score -= 1  # publication bias risk
    grades = {4: "高", 3: "中", 2: "低", 1: "极低"}
    return {
        "grade": grades.get(max(score, 1), "极低"),
        "score": score,
        "factors": {
            "studyCount": n,
            "heterogeneity": "高" if i_squared > 50 else "低",
            "publicationBiasRisk": "存在" if n < 5 else "较低",
        },
    }


# ── Statistical helpers ──────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Standard normal CDF (Abramowitz & Stegun approximation)."""
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2.0)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)


def _chi2_cdf(x: float, df: int) -> float:
    """Chi-square CDF approximation for df > 0."""
    if df <= 0 or x <= 0:
        return 0.0
    # Wilson-Hilferty approximation
    z = ((x / df) ** (1/3) - 1 + 2/(9*df)) / math.sqrt(2/(9*df))
    return _norm_cdf(z)


def _safe_float(value: Any) -> float | None:
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "model": "", "summary": {}, "heterogeneity": {},
            "forestPlot": [], "studyCount": 0, "error": message}
