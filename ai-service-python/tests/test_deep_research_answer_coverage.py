import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.deep_research.answer_coverage import answer_coverage_gaps


def make_plan():
    return [
        {
            "obligations": [
                {
                    "obligationId": "ob-calibration",
                    "question": "How was the camera intrinsic matrix calibrated?",
                    "requiredSources": ["camera-paper"],
                },
                {
                    "obligationId": "ob-distortion",
                    "question": "Which distortion model was fitted?",
                    "requiredSources": ["camera-paper"],
                },
            ]
        }
    ]


def make_claims():
    return [
        {
            "claimId": "claim-calibration",
            "text": "The camera intrinsic matrix was calibrated by Zhang's method with reprojection error 0.42 pixels.",
            "conditions": None,
            "obligationIds": ["ob-calibration"],
        },
        {
            "claimId": "claim-distortion",
            "text": "Radial distortion coefficients k1 and k2 were estimated from eighteen checkerboard views.",
            "conditions": {"dataset": "checkerboard", "views": 18},
            "obligationIds": ["ob-distortion"],
        },
    ]


def covered_verdict(obligation_id, claim_id, excerpt):
    return {
        "obligationId": obligation_id,
        "status": "covered",
        "bindings": [{"claimId": claim_id, "excerpt": excerpt}],
    }


def make_verdicts():
    return [
        covered_verdict(
            "ob-calibration",
            "claim-calibration",
            "calibrated by Zhang's method with reprojection error 0.42 pixels",
        ),
        covered_verdict(
            "ob-distortion",
            "claim-distortion",
            "Radial distortion coefficients k1 and k2",
        ),
    ]


class AnswerCoverageGapsTests(unittest.TestCase):
    def test_cited_final_text_closes_gaps(self):
        gaps = answer_coverage_gaps(make_plan(), make_claims(), make_verdicts())
        self.assertEqual(gaps, [])

    def test_retrieval_metadata_and_obligation_ids_alone_do_not_close(self):
        verdicts = [
            {"obligationId": "ob-calibration", "status": "covered", "bindings": []},
            covered_verdict("ob-distortion", "claim-distortion", "eighteen checkerboard views"),
        ]
        gaps = answer_coverage_gaps(make_plan(), make_claims(), verdicts)
        self.assertEqual([gap["obligationId"] for gap in gaps], ["ob-calibration"])

    def test_removed_claim_not_in_accepted_cannot_close(self):
        claims = [c for c in make_claims() if c["claimId"] != "claim-calibration"]
        gaps = answer_coverage_gaps(make_plan(), claims, make_verdicts())
        self.assertEqual(
            gaps,
            [
                {
                    "obligationId": "ob-calibration",
                    "question": "How was the camera intrinsic matrix calibrated?",
                    "missingEvidence": "最终回答尚未完整回应这一问题",
                    "stage": "answer",
                }
            ],
        )

    def test_duplicated_verdict_fails_even_with_covered(self):
        verdicts = make_verdicts() + [
            {"obligationId": "ob-calibration", "status": "missing", "bindings": []}
        ]
        gaps = answer_coverage_gaps(make_plan(), make_claims(), verdicts)
        self.assertEqual([gap["obligationId"] for gap in gaps], ["ob-calibration"])

    def test_duplicate_claim_identities_fail(self):
        claims = make_claims()
        claims.append(dict(claims[0]))
        gaps = answer_coverage_gaps(make_plan(), claims, make_verdicts())
        self.assertEqual([gap["obligationId"] for gap in gaps], ["ob-calibration"])

    def test_excerpt_from_other_claim_or_invented_words_fails(self):
        verdicts = [
            covered_verdict("ob-calibration", "claim-calibration", "estimated from eighteen checkerboard views"),
            covered_verdict("ob-distortion", "claim-distortion", "laser interferometer bench measurement"),
        ]
        gaps = answer_coverage_gaps(make_plan(), make_claims(), verdicts)
        self.assertEqual(
            [gap["obligationId"] for gap in gaps],
            ["ob-calibration", "ob-distortion"],
        )

    def test_absent_partial_or_missing_status_fails(self):
        base = make_verdicts()
        no_status = {"obligationId": "ob-calibration", "bindings": base[0]["bindings"]}
        partial = dict(base[0], status="partial")
        missing = dict(base[1], status="missing")
        for bad in (no_status, partial):
            gaps = answer_coverage_gaps(make_plan(), make_claims(), [bad, base[1]])
            self.assertEqual([gap["obligationId"] for gap in gaps], ["ob-calibration"])
        gaps = answer_coverage_gaps(make_plan(), make_claims(), [base[0], missing])
        self.assertEqual([gap["obligationId"] for gap in gaps], ["ob-distortion"])

    def test_unknown_obligation_verdict_does_not_close_known(self):
        verdicts = [covered_verdict("ob-unknown", "claim-calibration", "calibrated by Zhang's method")]
        gaps = answer_coverage_gaps(make_plan(), make_claims(), verdicts)
        self.assertEqual(
            [gap["obligationId"] for gap in gaps],
            ["ob-calibration", "ob-distortion"],
        )

    def test_conditions_serialized_excerpt_closes(self):
        serialized = json.dumps(make_claims()[1]["conditions"], ensure_ascii=False, sort_keys=True)
        self.assertIn('"dataset": "checkerboard"', serialized)
        verdicts = [
            covered_verdict("ob-calibration", "claim-calibration", "reprojection error 0.42 pixels"),
            covered_verdict("ob-distortion", "claim-distortion", '"dataset": "checkerboard"'),
        ]
        gaps = answer_coverage_gaps(make_plan(), make_claims(), verdicts)
        self.assertEqual(gaps, [])

    def test_whitespace_only_and_short_excerpts_fail(self):
        verdicts = [
            covered_verdict("ob-calibration", "claim-calibration", "        "),
            covered_verdict("ob-distortion", "claim-distortion", "k1 k2"),
        ]
        gaps = answer_coverage_gaps(make_plan(), make_claims(), verdicts)
        self.assertEqual(
            [gap["obligationId"] for gap in gaps],
            ["ob-calibration", "ob-distortion"],
        )

    def test_malformed_inputs_leave_gaps(self):
        plan = make_plan()
        self.assertEqual(len(answer_coverage_gaps(plan, None, None)), 2)
        self.assertEqual(len(answer_coverage_gaps(plan, make_claims(), [None, "x", 3])), 2)
        bad_binding = [{"obligationId": "ob-calibration", "status": "covered", "bindings": [{"claimId": "claim-calibration"}]}]
        gaps = answer_coverage_gaps(plan, make_claims(), bad_binding)
        self.assertEqual([gap["obligationId"] for gap in gaps], ["ob-calibration", "ob-distortion"])

    def test_inputs_are_not_mutated(self):
        plan, claims, verdicts = make_plan(), make_claims(), make_verdicts()
        plan_copy, claims_copy, verdicts_copy = copy.deepcopy(plan), copy.deepcopy(claims), copy.deepcopy(verdicts)
        answer_coverage_gaps(plan, claims, verdicts)
        self.assertEqual(plan, plan_copy)
        self.assertEqual(claims, claims_copy)
        self.assertEqual(verdicts, verdicts_copy)


if __name__ == "__main__":
    unittest.main()
