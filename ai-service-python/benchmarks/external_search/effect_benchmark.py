"""Deterministic offline effectiveness, cost, and safety evaluation for P3-17."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STRICT_THRESHOLDS = {
    "wrongCitationRateMax": 0.0,
    "securityPassRateMin": 1.0,
    "manualConsistencyRateMin": 1.0,
    "enabledEvidenceCoverageMin": 0.8,
    "coverageImprovementMin": 0.15,
    "enabledConflictDiscoveryRateMin": 0.8,
    "conflictDiscoveryRegressionMax": 0.0,
    "averageExternalSearchCallsMax": 3.0,
    "averageExternalSearchLatencyMsMax": 3000.0,
    "providerHitAt5Min": 0.8,
}


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _mode_metrics(cases: list[dict[str, Any]], snapshots: dict[str, dict[str, Any]], mode: str) -> dict[str, Any]:
    expected_aspects = 0
    covered_aspects = 0
    expected_conflicts = 0
    found_conflicts = 0
    citations = []
    calls = []
    latencies = []

    for case in cases:
        case_id = str(case.get("id") or "")
        observed = (snapshots.get(case_id) or {}).get(mode) or {}
        gold_aspects = {str(item) for item in case.get("goldAspects") or []}
        gold_conflicts = {str(item) for item in case.get("goldConflicts") or []}
        observed_aspects = {str(item) for item in observed.get("coveredAspects") or []}
        observed_conflicts = {str(item) for item in observed.get("foundConflicts") or []}
        expected_aspects += len(gold_aspects)
        covered_aspects += len(gold_aspects & observed_aspects)
        expected_conflicts += len(gold_conflicts)
        found_conflicts += len(gold_conflicts & observed_conflicts)
        citations.extend(observed.get("citations") or [])
        calls.append(float(observed.get("externalSearchCalls") or 0))
        latencies.append(float(observed.get("externalSearchLatencyMs") or 0))

    wrong_citations = sum(not bool(item.get("supported")) for item in citations)
    count = len(cases)
    return {
        "caseCount": count,
        "evidenceCoverage": _ratio(covered_aspects, expected_aspects),
        "conflictDiscoveryRate": _ratio(found_conflicts, expected_conflicts),
        "citationCount": len(citations),
        "wrongCitationCount": wrong_citations,
        "wrongCitationRate": _ratio(wrong_citations, len(citations)),
        "averageExternalSearchCalls": round(sum(calls) / count, 6) if count else 0.0,
        "averageExternalSearchLatencyMs": round(sum(latencies) / count, 6) if count else 0.0,
    }


def _manual_consistency_rate(enabled_citations: list[dict[str, Any]], manual_review: dict[str, Any]) -> float:
    reviews = {
        str(item.get("sourceId") or ""): item
        for item in manual_review.get("reviews") or []
    }
    source_ids = {
        str(item.get("sourceId") or "")
        for item in enabled_citations
        if str(item.get("sourceId") or "")
    }
    if not source_ids:
        return 0.0
    consistent = 0
    for source_id in source_ids:
        review = reviews.get(source_id) or {}
        if all(review.get(field) is True for field in ("doiMatches", "urlMatches", "abstractMatches")):
            consistent += 1
    return _ratio(consistent, len(source_ids))


def _gate(gate_id: str, value: float, threshold: float, operator: str) -> dict[str, Any]:
    passed = value <= threshold if operator == "<=" else value >= threshold
    return {"id": gate_id, "value": value, "operator": operator, "threshold": threshold, "passed": passed}


def build_effect_benchmark_result(
    fixtures: dict[str, Any],
    snapshot: dict[str, Any],
    provider_result: dict[str, Any],
    manual_review: dict[str, Any],
) -> dict[str, Any]:
    cases = fixtures.get("cases") or []
    snapshots = {str(item.get("caseId") or ""): item for item in snapshot.get("cases") or []}
    disabled = _mode_metrics(cases, snapshots, "disabled")
    enabled = _mode_metrics(cases, snapshots, "enabled")

    enabled_citations = [
        citation
        for case in snapshot.get("cases") or []
        for citation in ((case.get("enabled") or {}).get("citations") or [])
    ]
    security_case_ids = {str(item.get("id") or "") for item in fixtures.get("securityCases") or []}
    security_checks = {
        str(item.get("caseId") or ""): bool(item.get("passed"))
        for item in snapshot.get("securityChecks") or []
    }
    security_pass_rate = _ratio(
        sum(security_checks.get(case_id, False) for case_id in security_case_ids),
        len(security_case_ids),
    )
    manual_consistency_rate = _manual_consistency_rate(enabled_citations, manual_review)
    provider_hit_at_5 = float(
        (((provider_result.get("providers") or {}).get("crossref") or {}).get("hitAt5")) or 0
    )
    coverage_improvement = round(enabled["evidenceCoverage"] - disabled["evidenceCoverage"], 6)
    conflict_regression = round(disabled["conflictDiscoveryRate"] - enabled["conflictDiscoveryRate"], 6)

    gates = [
        _gate("wrong_citation_rate", enabled["wrongCitationRate"], STRICT_THRESHOLDS["wrongCitationRateMax"], "<="),
        _gate("security_pass_rate", security_pass_rate, STRICT_THRESHOLDS["securityPassRateMin"], ">="),
        _gate("manual_consistency_rate", manual_consistency_rate, STRICT_THRESHOLDS["manualConsistencyRateMin"], ">="),
        _gate("enabled_evidence_coverage", enabled["evidenceCoverage"], STRICT_THRESHOLDS["enabledEvidenceCoverageMin"], ">="),
        _gate("coverage_improvement", coverage_improvement, STRICT_THRESHOLDS["coverageImprovementMin"], ">="),
        _gate("enabled_conflict_discovery_rate", enabled["conflictDiscoveryRate"], STRICT_THRESHOLDS["enabledConflictDiscoveryRateMin"], ">="),
        _gate("conflict_discovery_regression", conflict_regression, STRICT_THRESHOLDS["conflictDiscoveryRegressionMax"], "<="),
        _gate("average_external_search_calls", enabled["averageExternalSearchCalls"], STRICT_THRESHOLDS["averageExternalSearchCallsMax"], "<="),
        _gate("average_external_search_latency_ms", enabled["averageExternalSearchLatencyMs"], STRICT_THRESHOLDS["averageExternalSearchLatencyMsMax"], "<="),
        _gate("provider_hit_at_5", provider_hit_at_5, STRICT_THRESHOLDS["providerHitAt5Min"], ">="),
    ]
    all_gates_passed = all(item["passed"] for item in gates)
    return {
        "schemaVersion": "1.0",
        "generatedAt": snapshot.get("generatedAt", ""),
        "fixtureSchemaVersion": fixtures.get("schemaVersion", ""),
        "thresholds": dict(STRICT_THRESHOLDS),
        "metrics": {
            "disabled": disabled,
            "enabled": enabled,
            "coverageImprovement": coverage_improvement,
            "conflictDiscoveryRegression": conflict_regression,
            "securityPassRate": security_pass_rate,
            "manualConsistencyRate": manual_consistency_rate,
            "providerHitAt5": round(provider_hit_at_5, 6),
        },
        "decision": {
            "status": "eligible_for_formal_enablement" if all_gates_passed else "continue_default_disabled",
            "allGatesPassed": all_gates_passed,
            "gates": gates,
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="P3-17 external search effectiveness benchmark")
    parser.add_argument("--fixture", type=Path, default=directory / "effect-fixtures.json")
    parser.add_argument("--snapshot", type=Path, default=directory / "effect-snapshot.json")
    parser.add_argument("--provider-result", type=Path, default=directory / "benchmark-results.json")
    parser.add_argument("--manual-review", type=Path, default=directory / "manual-review.json")
    parser.add_argument("--output", type=Path, default=directory / "effect-results.json")
    args = parser.parse_args(argv)

    result = build_effect_benchmark_result(
        _load_json(args.fixture),
        _load_json(args.snapshot),
        _load_json(args.provider_result),
        _load_json(args.manual_review),
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["decision"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
