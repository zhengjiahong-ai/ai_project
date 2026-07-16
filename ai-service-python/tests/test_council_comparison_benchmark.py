import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.council.comparison_benchmark import (
    STRICT_THRESHOLDS,
    build_comparison_result,
    main,
    run_live_comparison,
    validate_comparison_snapshot,
)
from llm.provider import LLMResult, LLMUsage


ROOT = Path(__file__).parents[1]
COUNCIL_DIR = ROOT / "benchmarks" / "council"


def _opinion(role, verdict, source_ids, *, abstain=False, reason=""):
    return {
        "reviewerId": role,
        "role": role,
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "verdict": "abstain" if abstain else verdict,
        "conclusion": "" if abstain else "bounded conclusion",
        "reason": "" if abstain else "evidence-bound reason",
        "sourceIds": source_ids,
        "confidence": 0.0 if abstain else 0.8,
        "abstain": abstain,
        "abstainReason": reason,
        "usage": {"inputTokens": 100, "outputTokens": 40, "totalTokens": 140, "estimated": False},
    }


def _snapshot(fixtures, *, latency_ms=4000, failure=False):
    cases = []
    for case in fixtures["cases"]:
        category = case["category"]
        required = case["gold"]["requiredSourceIds"]
        if category in {"numeric_conflict", "conclusion_conflict"}:
            opinions = [
                _opinion("evidence_reviewer", "supported", required[:1]),
                _opinion("contradiction_reviewer", "conflict", required),
            ]
            action = "manual_review_required"
        elif category in {"insufficient", "prompt_injection"}:
            opinions = [
                _opinion("evidence_reviewer", "abstain", [], abstain=True, reason="evidence_insufficient"),
                _opinion("contradiction_reviewer", "abstain", [], abstain=True, reason="evidence_insufficient"),
            ]
            action = "collect_more_evidence"
        else:
            opinions = [
                _opinion("evidence_reviewer", "supported", required),
                _opinion("contradiction_reviewer", "supported", required),
            ]
            action = "accept_with_caution"
        if failure and case is fixtures["cases"][0]:
            opinions[0] = _opinion(
                "evidence_reviewer", "abstain", [], abstain=True, reason="provider_unavailable"
            )
            action = "collect_more_evidence"
        cases.append({
            "caseId": case["id"],
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "latencyMs": latency_ms,
            "output": {
                "opinions": opinions,
                "agreements": [],
                "disagreements": [],
                "abstentions": [],
                "evidenceCoverage": {},
                "recommendedAction": action,
            },
        })
    return {
        "schemaVersion": "1.0",
        "fixtureSchemaVersion": fixtures["schemaVersion"],
        "generatedAt": "2026-06-30T00:00:00Z",
        "cases": cases,
    }


class CouncilComparisonBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = json.loads((COUNCIL_DIR / "fixtures.json").read_text(encoding="utf-8"))
        self.baseline = json.loads((COUNCIL_DIR / "baseline-results.json").read_text(encoding="utf-8"))

    def test_all_quality_utility_failure_and_cost_gates_pass(self):
        result = build_comparison_result(self.fixtures, self.baseline, _snapshot(self.fixtures))

        self.assertEqual(result["thresholds"], STRICT_THRESHOLDS)
        self.assertEqual(result["metrics"]["accuracy"], 1.0)
        self.assertEqual(result["metrics"]["citationCorrectness"], 1.0)
        self.assertEqual(result["metrics"]["conflictRecall"], 1.0)
        self.assertEqual(result["metrics"]["promptInjectionPassRate"], 1.0)
        self.assertEqual(result["metrics"]["conflictManualReviewRate"], 1.0)
        self.assertEqual(result["metrics"]["insufficientEscalationRate"], 1.0)
        self.assertEqual(result["metrics"]["reviewerFailureRate"], 0.0)
        self.assertTrue(result["decision"]["allGatesPassed"])
        self.assertEqual(result["decision"]["status"], "retain_explicit_opt_in")

    def test_repository_snapshot_recomputes_committed_comparison_result(self):
        snapshot = json.loads((COUNCIL_DIR / "comparison-snapshot.json").read_text(encoding="utf-8"))
        committed = json.loads((COUNCIL_DIR / "comparison-results.json").read_text(encoding="utf-8"))

        validate_comparison_snapshot(self.fixtures, snapshot)

        self.assertEqual(build_comparison_result(self.fixtures, self.baseline, snapshot), committed)
        self.assertEqual(committed["decision"]["status"], "remove_production_integration")

    def test_any_reviewer_failure_removes_production_integration(self):
        result = build_comparison_result(
            self.fixtures, self.baseline, _snapshot(self.fixtures, failure=True)
        )

        failed = {gate["id"] for gate in result["decision"]["gates"] if not gate["passed"]}
        self.assertIn("reviewer_failure_rate", failed)
        self.assertIn("accuracy_non_regression", failed)
        self.assertEqual(result["decision"]["status"], "remove_production_integration")

    def test_latency_over_baseline_multiplier_fails_cost_gate(self):
        snapshot = _snapshot(self.fixtures, latency_ms=10000)
        result = build_comparison_result(self.fixtures, self.baseline, snapshot)

        failed = {gate["id"] for gate in result["decision"]["gates"] if not gate["passed"]}
        self.assertIn("average_latency_multiplier", failed)

    def test_snapshot_rejects_sensitive_fields(self):
        snapshot = _snapshot(self.fixtures)
        snapshot["cases"][0]["prompt"] = "secret"

        with self.assertRaisesRegex(ValueError, "sensitive field"):
            validate_comparison_snapshot(self.fixtures, snapshot)

    def test_live_runner_uses_two_independent_calls_per_case_and_sanitizes_snapshot(self):
        class Provider:
            def __init__(self):
                self.requests = []

            def invoke(self, request):
                self.requests.append(request)
                role = "conflict" if "CONTRADICTION_REVIEWER" in request.prompt else "supported"
                return LLMResult(
                    "fixture",
                    "fixture-council",
                    json.dumps({
                        "verdict": role,
                        "conclusion": "bounded",
                        "reason": "bounded",
                        "sourceIds": ["paper-result-1"],
                        "confidence": 0.8,
                    }),
                    LLMUsage(10, 5, 15, estimated=False),
                )

        provider = Provider()
        snapshot = run_live_comparison(
            self.fixtures, provider=provider, generated_at="2026-06-30T00:00:00Z"
        )

        self.assertEqual(len(provider.requests), 10)
        self.assertTrue(all("prompt" not in case for case in snapshot["cases"]))
        self.assertEqual(snapshot["cases"][0]["output"]["opinions"][0]["provider"], "fixture")

    def test_cli_recomputes_result_without_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture_path = root / "fixtures.json"
            baseline_path = root / "baseline.json"
            snapshot_path = root / "snapshot.json"
            output_path = root / "result.json"
            fixture_path.write_text(json.dumps(self.fixtures), encoding="utf-8")
            baseline_path.write_text(json.dumps(self.baseline), encoding="utf-8")
            snapshot_path.write_text(json.dumps(_snapshot(self.fixtures)), encoding="utf-8")

            with patch("requests.post") as post:
                exit_code = main([
                    "--fixture", str(fixture_path),
                    "--baseline-result", str(baseline_path),
                    "--snapshot", str(snapshot_path),
                    "--output", str(output_path),
                ])

            self.assertEqual(exit_code, 0)
            post.assert_not_called()
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8"))["decision"]["status"],
                "retain_explicit_opt_in",
            )


if __name__ == "__main__":
    unittest.main()
