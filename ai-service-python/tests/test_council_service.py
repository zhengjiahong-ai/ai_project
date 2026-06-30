import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from llm import client as llm_client
from llm.provider import LLMRequest, LLMResult, LLMUsage
from services.council_service import run_council
from services.research_aggregator import select_council_targets


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def invoke(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def llm_result(payload, *, model="fixture-council"):
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return LLMResult(
        provider="fixture",
        model=model,
        content=content,
        usage=LLMUsage(input_tokens=20, output_tokens=10, total_tokens=30, estimated=False),
    )


def opinion_payload(
    verdict="supported",
    *,
    conclusion="证据支持结论",
    reason="给定证据直接支持该判断",
    source_ids=None,
    confidence=0.8,
):
    return {
        "verdict": verdict,
        "conclusion": conclusion,
        "reason": reason,
        "sourceIds": ["s1"] if source_ids is None else source_ids,
        "confidence": confidence,
    }


def evidence_items():
    return [
        {"sourceId": "s1", "text": "Controlled results support the method."},
        {"sourceId": "s2", "text": "The appendix reports the same conclusion."},
        {"sourceId": "s3", "text": "Ablation details are available."},
    ]


class CouncilServiceTests(unittest.TestCase):
    def tearDown(self):
        llm_client._llm = None

    def test_reviewers_use_independent_role_prompts_with_the_same_provider(self):
        provider = FakeProvider(
            [
                llm_result(opinion_payload(conclusion="EVIDENCE_ONLY_RESULT")),
                llm_result(opinion_payload(conclusion="CONTRADICTION_ONLY_RESULT")),
            ]
        )

        result = run_council("Is the method supported?", evidence_items(), provider=provider)

        self.assertEqual(len(provider.requests), 2)
        self.assertIn("COUNCIL_ROLE_EVIDENCE_REVIEWER", provider.requests[0].prompt)
        self.assertIn("COUNCIL_ROLE_CONTRADICTION_REVIEWER", provider.requests[1].prompt)
        self.assertNotIn("CONTRADICTION_ONLY_RESULT", provider.requests[0].prompt)
        self.assertNotIn("EVIDENCE_ONLY_RESULT", provider.requests[1].prompt)
        self.assertEqual([item["role"] for item in result["opinions"]], ["evidence_reviewer", "contradiction_reviewer"])

    def test_empty_evidence_returns_two_abstentions_without_calling_provider(self):
        provider = FakeProvider([])

        result = run_council("Is the method supported?", [], provider=provider)

        self.assertEqual(provider.requests, [])
        self.assertEqual(len(result["opinions"]), 2)
        self.assertTrue(all(item["abstain"] for item in result["opinions"]))
        self.assertEqual(len(result["abstentions"]), 2)
        self.assertEqual(result["recommendedAction"], "collect_more_evidence")

    def test_unknown_source_id_turns_only_that_reviewer_into_abstention(self):
        provider = FakeProvider(
            [
                llm_result(opinion_payload(source_ids=["invented-source"])),
                llm_result(opinion_payload(source_ids=["s1"])),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        self.assertTrue(result["opinions"][0]["abstain"])
        self.assertEqual(result["opinions"][0]["sourceIds"], [])
        self.assertFalse(result["opinions"][1]["abstain"])
        self.assertNotIn("invented-source", json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["recommendedAction"], "collect_more_evidence")

    def test_parse_failure_preserves_other_valid_opinion_and_hides_raw_output(self):
        provider = FakeProvider(
            [
                llm_result("not-json-secret-output"),
                llm_result(opinion_payload(source_ids=["s2"])),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        self.assertTrue(result["opinions"][0]["abstain"])
        self.assertFalse(result["opinions"][1]["abstain"])
        self.assertNotIn("not-json-secret-output", json.dumps(result, ensure_ascii=False))

    def test_provider_failure_is_a_sanitized_abstention(self):
        provider = FakeProvider(
            [
                RuntimeError("secret-token"),
                llm_result(opinion_payload(source_ids=["s2"])),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        self.assertTrue(result["opinions"][0]["abstain"])
        self.assertEqual(result["opinions"][0]["provider"], "unknown")
        self.assertNotIn("secret-token", json.dumps(result, ensure_ascii=False))
        self.assertFalse(result["opinions"][1]["abstain"])

    def test_explicit_insufficient_verdict_becomes_abstention(self):
        provider = FakeProvider(
            [
                llm_result(opinion_payload(verdict="insufficient", source_ids=[])),
                llm_result(opinion_payload(source_ids=["s1"])),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        self.assertEqual(result["opinions"][0]["verdict"], "abstain")
        self.assertTrue(result["opinions"][0]["abstain"])
        self.assertIn("insufficient", result["opinions"][0]["abstainReason"])

    def test_shared_evidence_agreement_accepts_with_caution_and_reports_coverage(self):
        provider = FakeProvider(
            [
                llm_result(opinion_payload(source_ids=["s1", "s2"])),
                llm_result(opinion_payload(source_ids=["s2"])),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        self.assertEqual(len(result["agreements"]), 1)
        self.assertEqual(result["agreements"][0]["sourceIds"], ["s2"])
        self.assertEqual(result["disagreements"], [])
        self.assertEqual(
            result["evidenceCoverage"],
            {
                "allowedSourceCount": 3,
                "citedSourceCount": 2,
                "sharedSourceIds": ["s2"],
                "uncitedSourceIds": ["s3"],
                "ratio": 0.666667,
            },
        )
        self.assertEqual(result["recommendedAction"], "accept_with_caution")

    def test_same_verdict_without_shared_evidence_is_not_strong_consensus(self):
        provider = FakeProvider(
            [
                llm_result(opinion_payload(source_ids=["s1"])),
                llm_result(opinion_payload(source_ids=["s2"])),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        self.assertEqual(result["agreements"], [])
        self.assertEqual(result["disagreements"][0]["type"], "evidence_basis_disagreement")
        self.assertFalse(result["disagreements"][0]["highRisk"])
        self.assertEqual(result["recommendedAction"], "collect_more_evidence")

    def test_conflicting_verdicts_create_sourced_high_risk_disagreement(self):
        provider = FakeProvider(
            [
                llm_result(opinion_payload(verdict="supported", source_ids=["s1"])),
                llm_result(
                    opinion_payload(
                        verdict="conflict",
                        conclusion="结果存在冲突",
                        reason="主实验和消融实验结论相反",
                        source_ids=["s2", "s3"],
                    )
                ),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        disagreement = result["disagreements"][0]
        self.assertEqual(disagreement["type"], "verdict_disagreement")
        self.assertTrue(disagreement["highRisk"])
        self.assertEqual(disagreement["sourceIds"], ["s1", "s2", "s3"])
        self.assertEqual(len(disagreement["positions"]), 2)
        self.assertTrue(all(item["reason"] for item in disagreement["positions"]))
        self.assertEqual(result["recommendedAction"], "manual_review_required")

    def test_matching_conflict_opinions_still_require_manual_review(self):
        provider = FakeProvider(
            [
                llm_result(opinion_payload(verdict="conflict", source_ids=["s1", "s2"])),
                llm_result(opinion_payload(verdict="conflict", source_ids=["s2", "s3"])),
            ]
        )

        result = run_council("Question", evidence_items(), provider=provider)

        self.assertEqual(len(result["agreements"]), 1)
        self.assertEqual(result["recommendedAction"], "manual_review_required")

    def test_repository_fixture_runs_both_council_reviewers_offline(self):
        fixture_path = Path(__file__).parent / "fixtures" / "llm_responses.json"
        with patch.dict(
            os.environ,
            {
                "PIXIU_LLM_MODE": "fixture",
                "PIXIU_LLM_FIXTURE_PATH": str(fixture_path),
            },
            clear=False,
        ):
            llm_client._llm = None
            result = run_council(
                "OFFLINE_COUNCIL_MARKER",
                [{"sourceId": "source-1", "text": "固定证据支持结论。"}],
            )

        self.assertEqual(len(result["opinions"]), 2)
        self.assertTrue(all(not item["abstain"] for item in result["opinions"]))
        self.assertEqual(result["agreements"][0]["sourceIds"], ["source-1"])


class CouncilPilotTargetSelectionTests(unittest.TestCase):
    def test_conflicts_are_prioritized_by_severity_and_capped(self):
        conflicts = [
            {"id": "low", "conflictType": "numeric_mismatch", "severity": "low", "claim": "low", "sourceIds": ["s-low"], "sources": [{"sourceId": "s-low", "text": "low"}]},
            {"id": "ignored", "conflictType": "other", "severity": "high", "claim": "ignored", "sourceIds": ["s-x"], "sources": [{"sourceId": "s-x", "text": "ignored"}]},
            {"id": "high", "conflictType": "opposing_conclusion", "severity": "high", "claim": "high", "sourceIds": ["s-high"], "sources": [{"sourceId": "s-high", "text": "high"}]},
            {"id": "medium", "conflictType": "numeric_mismatch", "severity": "medium", "claim": "medium", "sourceIds": ["s-medium"], "sources": [{"sourceId": "s-medium", "text": "medium"}]},
        ]

        targets = select_council_targets([], conflicts, max_reviews=3)

        self.assertEqual([item["targetId"] for item in targets], ["high", "medium", "low"])
        self.assertTrue(all(item["targetType"] == "conflict" for item in targets))

    def test_low_coverage_score_and_verdict_select_findings_in_original_order(self):
        findings = [
            {"id": "strong", "subQuestion": "strong", "verdict": "CORRECT", "judgeScore": 90, "coverage": {"score": 0.9}, "sourceIds": ["s0"], "sources": [{"sourceId": "s0", "text": "strong"}]},
            {"id": "coverage", "subQuestion": "coverage", "verdict": "CORRECT", "judgeScore": 80, "coverage": {"score": 0.5}, "sourceIds": ["s1"], "sources": [{"sourceId": "s1", "text": "coverage"}]},
            {"id": "score", "subQuestion": "score", "verdict": "CORRECT", "judgeScore": 59, "coverage": {"score": 0.8}, "sourceIds": ["s2"], "sources": [{"sourceId": "s2", "text": "score"}]},
            {"id": "ambiguous", "subQuestion": "ambiguous", "verdict": "AMBIGUOUS", "judgeScore": 75, "coverage": {"score": 0.8}, "sourceIds": ["s3"], "sources": [{"sourceId": "s3", "text": "ambiguous"}]},
            {"id": "fourth", "subQuestion": "fourth", "verdict": "INCORRECT", "judgeScore": 20, "coverage": {"score": 0.1}, "sourceIds": ["s4"], "sources": [{"sourceId": "s4", "text": "fourth"}]},
        ]

        targets = select_council_targets(findings, [], max_reviews=3)

        self.assertEqual([item["targetId"] for item in targets], ["coverage", "score", "ambiguous"])
        self.assertTrue(all(item["targetType"] == "finding" for item in targets))
        self.assertEqual(targets[0]["sourceIds"], ["s1"])


if __name__ == "__main__":
    unittest.main()
