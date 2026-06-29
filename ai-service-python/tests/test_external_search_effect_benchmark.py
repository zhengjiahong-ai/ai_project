import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.external_search.effect_benchmark import (
    STRICT_THRESHOLDS,
    build_effect_benchmark_result,
    main,
)


FIXTURES = {
    "schemaVersion": "1.0",
    "cases": [
        {"id": "coverage", "goldAspects": ["method", "dataset"], "goldConflicts": []},
        {"id": "conflict", "goldAspects": ["claim", "replication"], "goldConflicts": ["effect-size"]},
    ],
    "securityCases": [{"id": "prompt-injection"}, {"id": "provider-host"}],
}


def _snapshot(*, supported=True, security_passed=True):
    return {
        "schemaVersion": "1.0",
        "generatedAt": "2026-06-29T00:00:00Z",
        "fixtureSchemaVersion": "1.0",
        "cases": [
            {
                "caseId": "coverage",
                "disabled": {
                    "coveredAspects": ["method"],
                    "foundConflicts": [],
                    "citations": [],
                    "externalSearchCalls": 0,
                    "externalSearchLatencyMs": 0,
                },
                "enabled": {
                    "coveredAspects": ["method", "dataset"],
                    "foundConflicts": [],
                    "citations": [{"sourceId": "ext-1", "supported": supported}],
                    "externalSearchCalls": 1,
                    "externalSearchLatencyMs": 1200,
                },
            },
            {
                "caseId": "conflict",
                "disabled": {
                    "coveredAspects": ["claim"],
                    "foundConflicts": [],
                    "citations": [],
                    "externalSearchCalls": 0,
                    "externalSearchLatencyMs": 0,
                },
                "enabled": {
                    "coveredAspects": ["claim", "replication"],
                    "foundConflicts": ["effect-size"],
                    "citations": [{"sourceId": "ext-2", "supported": True}],
                    "externalSearchCalls": 2,
                    "externalSearchLatencyMs": 1800,
                },
            },
        ],
        "securityChecks": [
            {"caseId": "prompt-injection", "passed": security_passed},
            {"caseId": "provider-host", "passed": True},
        ],
    }


MANUAL_REVIEW = {
    "schemaVersion": "1.0",
    "reviews": [
        {"sourceId": "ext-1", "doiMatches": True, "urlMatches": True, "abstractMatches": True},
        {"sourceId": "ext-2", "doiMatches": True, "urlMatches": True, "abstractMatches": True},
    ],
}


class ExternalSearchEffectBenchmarkTests(unittest.TestCase):
    def test_scores_paired_modes_and_all_strict_gates(self):
        provider_result = {"providers": {"crossref": {"hitAt5": 0.9}}}

        result = build_effect_benchmark_result(FIXTURES, _snapshot(), provider_result, MANUAL_REVIEW)

        self.assertEqual(result["metrics"]["disabled"]["evidenceCoverage"], 0.5)
        self.assertEqual(result["metrics"]["enabled"]["evidenceCoverage"], 1.0)
        self.assertEqual(result["metrics"]["coverageImprovement"], 0.5)
        self.assertEqual(result["metrics"]["enabled"]["conflictDiscoveryRate"], 1.0)
        self.assertEqual(result["metrics"]["enabled"]["wrongCitationRate"], 0.0)
        self.assertEqual(result["metrics"]["enabled"]["averageExternalSearchCalls"], 1.5)
        self.assertEqual(result["metrics"]["enabled"]["averageExternalSearchLatencyMs"], 1500.0)
        self.assertEqual(result["metrics"]["securityPassRate"], 1.0)
        self.assertEqual(result["metrics"]["manualConsistencyRate"], 1.0)
        self.assertTrue(result["decision"]["allGatesPassed"])
        self.assertEqual(result["decision"]["status"], "eligible_for_formal_enablement")
        self.assertEqual(result["thresholds"], STRICT_THRESHOLDS)

    def test_any_correctness_safety_or_provider_failure_keeps_default_disabled(self):
        provider_result = {"providers": {"crossref": {"hitAt5": 0.333333}}}
        manual_review = json.loads(json.dumps(MANUAL_REVIEW))
        manual_review["reviews"][0]["urlMatches"] = False

        result = build_effect_benchmark_result(
            FIXTURES,
            _snapshot(supported=False, security_passed=False),
            provider_result,
            manual_review,
        )

        failed = {gate["id"] for gate in result["decision"]["gates"] if not gate["passed"]}
        self.assertIn("wrong_citation_rate", failed)
        self.assertIn("security_pass_rate", failed)
        self.assertIn("manual_consistency_rate", failed)
        self.assertIn("provider_hit_at_5", failed)
        self.assertFalse(result["decision"]["allGatesPassed"])
        self.assertEqual(result["decision"]["status"], "continue_default_disabled")

    def test_cli_recomputes_offline_result_without_network(self):
        provider_result = {"providers": {"crossref": {"hitAt5": 0.333333}}}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {
                "fixture": root / "fixtures.json",
                "snapshot": root / "snapshot.json",
                "provider": root / "provider.json",
                "manual": root / "manual.json",
                "output": root / "result.json",
            }
            for name, value in (
                ("fixture", FIXTURES),
                ("snapshot", _snapshot()),
                ("provider", provider_result),
                ("manual", MANUAL_REVIEW),
            ):
                paths[name].write_text(json.dumps(value), encoding="utf-8")

            exit_code = main([
                "--fixture", str(paths["fixture"]),
                "--snapshot", str(paths["snapshot"]),
                "--provider-result", str(paths["provider"]),
                "--manual-review", str(paths["manual"]),
                "--output", str(paths["output"]),
            ])

            self.assertEqual(exit_code, 0)
            saved = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual(saved["decision"]["status"], "continue_default_disabled")


if __name__ == "__main__":
    unittest.main()
