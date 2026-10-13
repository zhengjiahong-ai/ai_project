import copy
import unittest

from services.deep_research.coverage_repair import (
    merge_verified_revisions,
    prepare_coverage_repair,
)


def _claim(cid, obligations, text):
    return {"claimId": cid, "obligationIds": list(obligations), "text": text}


def _camera_claims():
    return [
        _claim("c1", ["o1"], "Checkerboard corner detection localizes camera intrinsics."),
        _claim("c2", ["o2"], "Bundle adjustment refines camera extrinsics."),
        _claim("c3", ["o1", "o3"], "Radial distortion model lowers reprojection error."),
    ]


def test_merge_initial_conflicting_identity_stays_rejected():
    claim = _claim('c', ['o'], 'ambiguous')
    initial = {'accepted': [claim], 'rejected': [{'claimId': 'c', 'reason': 'failed'}]}
    for checked in ({}, {'accepted': [claim]}):
        result = merge_verified_revisions(initial, checked)
        assert result['accepted'] == []
        assert result['rejected'] == initial['rejected']


def test_merge_conflicting_revision_cannot_promote_failed_claim():
    claim = _claim('c', ['o'], 'conflicting revision')
    initial = {'accepted': [], 'rejected': [{'claimId': 'c', 'reason': 'failed'}]}
    result = merge_verified_revisions(initial, {'accepted': [claim],
        'rejected': [{'claimId': 'c', 'reason': 'also failed'}]})
    assert result == initial


def test_merge_conflicting_revision_preserves_unambiguous_previous_acceptance():
    claim = _claim('c', ['o'], 'previously checked')
    initial = {'accepted': [claim], 'rejected': []}
    result = merge_verified_revisions(initial, {'accepted': [{**claim, 'text': 'ambiguous'}],
        'rejected': [{'claimId': 'c', 'reason': 'failed'}]})
    assert result == initial


class PrepareCoverageRepairTests(unittest.TestCase):
    def test_existing_failed_target_prevents_rewriting_all_shared_obligation_claims(self):
        claims = [_claim('good', ['shared'], 'Known supported result'),
                  _claim('bad', ['shared'], 'Incomplete proposed method')]
        audit = {'gaps': [{'obligationId': 'shared', 'question': 'Complete the method'}],
                 'verdicts': [{'obligationId': 'shared', 'status': 'partial',
                               'bindings': [{'claimId': 'good', 'excerpt': 'Known supported result'}]}]}
        before = copy.deepcopy(audit)
        result = prepare_coverage_repair({'claims': claims}, {'accepted': [claims[0]],
            'rejected': [{'claimId': 'bad', 'reason': 'semantic_unresolved'}]}, audit)
        self.assertEqual([c['claimId'] for c in result['accepted']], ['good'])
        self.assertEqual([c['claimId'] for c in result['rejected']], ['bad'])
        self.assertEqual(result['rejected'][0]['missingQuestions'], ['Complete the method'])
        self.assertEqual(audit, before)  # Scheduling does not erase or resolve the gap.

    def test_targets_accepted_claim_via_verdict_bindings(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {"accepted": [claims[0], claims[1]], "rejected": []}
        audit = {
            "gaps": [
                {"obligationId": "o2", "question": "How is scale ambiguity resolved?", "wholeQuestion": False}
            ],
            "verdicts": [
                {
                    "obligationId": "o2",
                    "status": "partial",
                    "bindings": [{"claimId": "c2", "excerpt": "extrinsics"}],
                }
            ],
        }

        result = prepare_coverage_repair(report, verification, audit)

        self.assertEqual([c["claimId"] for c in result["accepted"]], ["c1"])
        self.assertEqual(len(result["rejected"]), 1)
        row = result["rejected"][0]
        self.assertEqual(row["claimId"], "c2")
        self.assertEqual(row["reason"], "answer_incomplete")
        self.assertEqual(row["missingQuestions"], ["How is scale ambiguity resolved?"])

    def test_targets_via_obligation_ids_without_bindings(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {"accepted": [claims[0], claims[2]], "rejected": []}
        audit = {
            "gaps": [
                {"obligationId": "o3", "question": "How is distortion validated?", "wholeQuestion": False}
            ],
            "verdicts": [],
        }

        result = prepare_coverage_repair(report, verification, audit)

        self.assertEqual([c["claimId"] for c in result["accepted"]], ["c1"])
        self.assertEqual([r["claimId"] for r in result["rejected"]], ["c3"])
        self.assertEqual(result["rejected"][0]["missingQuestions"], ["How is distortion validated?"])

    def test_unmapped_specific_gap_targets_all_accepted_report_claims(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {"accepted": [claims[0], claims[1]], "rejected": []}
        audit = {
            "gaps": [
                {"obligationId": "o9", "question": "How is temporal sync handled?", "wholeQuestion": False}
            ],
            "verdicts": [],
        }

        result = prepare_coverage_repair(report, verification, audit)

        self.assertEqual(result["accepted"], [])
        self.assertEqual(sorted(r["claimId"] for r in result["rejected"]), ["c1", "c2"])
        for row in result["rejected"]:
            self.assertEqual(row["reason"], "answer_incomplete")
            self.assertEqual(row["missingQuestions"], ["How is temporal sync handled?"])

    def test_whole_question_gap_ignored_when_specific_gap_present(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {"accepted": [claims[0], claims[1], claims[2]], "rejected": []}
        audit = {
            "gaps": [
                {"obligationId": "o2", "question": "How is scale ambiguity resolved?", "wholeQuestion": False},
                {"obligationId": "oX", "question": "Is everything covered?", "wholeQuestion": True},
            ],
            "verdicts": [
                {
                    "obligationId": "o2",
                    "status": "partial",
                    "bindings": [{"claimId": "c2", "excerpt": "extrinsics"}],
                }
            ],
        }

        result = prepare_coverage_repair(report, verification, audit)

        self.assertEqual([c["claimId"] for c in result["accepted"]], ["c1", "c3"])
        self.assertEqual([r["claimId"] for r in result["rejected"]], ["c2"])

    def test_original_rejection_preserved_alongside_coverage_targets(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {
            "accepted": [claims[0], claims[1]],
            "rejected": [{"claimId": "c0", "reason": "fabricated_source"}],
        }
        audit = {
            "gaps": [
                {"obligationId": "o1", "question": "How are intrinsics validated?", "wholeQuestion": False}
            ],
            "verdicts": [
                {
                    "obligationId": "o1",
                    "status": "partial",
                    "bindings": [{"claimId": "c1", "excerpt": "intrinsics"}],
                }
            ],
        }

        result = prepare_coverage_repair(report, verification, audit)

        ids = [r["claimId"] for r in result["rejected"]]
        self.assertIn("c0", ids)
        self.assertIn("c1", ids)
        original = next(r for r in result["rejected"] if r["claimId"] == "c0")
        self.assertEqual(original["reason"], "fabricated_source")
        coverage = next(r for r in result["rejected"] if r["claimId"] == "c1")
        self.assertEqual(coverage["reason"], "answer_incomplete")

    def test_no_gaps_returns_equivalent_copy(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {"accepted": [claims[0]], "rejected": [{"claimId": "cx", "reason": "off_topic"}]}
        audit = {"gaps": [], "verdicts": []}

        result = prepare_coverage_repair(report, verification, audit)

        self.assertEqual(result["accepted"], verification["accepted"])
        self.assertEqual(result["rejected"], verification["rejected"])
        self.assertIsNot(result["accepted"], verification["accepted"])
        self.assertIsNot(result["rejected"], verification["rejected"])

    def test_no_accepted_claims_invents_no_targets(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {"accepted": [], "rejected": [{"claimId": "c1", "reason": "low_confidence"}]}
        audit = {
            "gaps": [
                {"obligationId": "o1", "question": "How are intrinsics validated?", "wholeQuestion": False}
            ],
            "verdicts": [],
        }

        result = prepare_coverage_repair(report, verification, audit)

        self.assertEqual(result["accepted"], [])
        self.assertEqual([r["claimId"] for r in result["rejected"]], ["c1"])
        self.assertEqual(result["rejected"][0]["reason"], "low_confidence")

    def test_unknown_binding_ids_are_not_invented(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {"accepted": [claims[0]], "rejected": []}
        audit = {
            "gaps": [
                {"obligationId": "o2", "question": "How is scale ambiguity resolved?", "wholeQuestion": False}
            ],
            "verdicts": [
                {
                    "obligationId": "o2",
                    "status": "partial",
                    "bindings": [{"claimId": "c999", "excerpt": "ghost"}],
                }
            ],
        }

        result = prepare_coverage_repair(report, verification, audit)

        self.assertNotIn("c999", [r["claimId"] for r in result["rejected"]])
        self.assertNotIn("c999", [c["claimId"] for c in result["accepted"]])

    def test_inputs_are_not_mutated(self):
        claims = _camera_claims()
        report = {"claims": claims}
        verification = {
            "accepted": [claims[0], claims[1]],
            "rejected": [{"claimId": "c0", "reason": "fabricated_source"}],
        }
        audit = {
            "gaps": [
                {"obligationId": "o2", "question": "How is scale ambiguity resolved?", "wholeQuestion": False}
            ],
            "verdicts": [
                {
                    "obligationId": "o2",
                    "status": "partial",
                    "bindings": [{"claimId": "c2", "excerpt": "extrinsics"}],
                }
            ],
        }

        report_snap = copy.deepcopy(report)
        verification_snap = copy.deepcopy(verification)
        audit_snap = copy.deepcopy(audit)

        prepare_coverage_repair(report, verification, audit)

        self.assertEqual(report, report_snap)
        self.assertEqual(verification, verification_snap)
        self.assertEqual(audit, audit_snap)


class MergeVerifiedRevisionsTests(unittest.TestCase):
    def test_successful_replacement_appears_once(self):
        initial = {"accepted": [_claim("c1", ["o1"], "draft intrinsics")], "rejected": []}
        checked = {"accepted": [_claim("c1", ["o1"], "corrected intrinsics")], "rejected": []}

        result = merge_verified_revisions(initial, checked)

        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["text"], "corrected intrinsics")
        self.assertEqual(result["rejected"], [])

    def test_failed_repair_retains_original_accepted(self):
        initial = {"accepted": [_claim("c1", ["o1"], "draft intrinsics")], "rejected": []}
        checked = {"accepted": [], "rejected": [{"claimId": "c1", "reason": "still_incomplete"}]}

        result = merge_verified_revisions(initial, checked)

        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["text"], "draft intrinsics")

    def test_repaired_original_rejection_promoted(self):
        initial = {
            "accepted": [_claim("c1", ["o1"], "intrinsics")],
            "rejected": [
                {"claimId": "c2", "reason": "answer_incomplete", "missingQuestions": ["How is scale ambiguity resolved?"]}
            ],
        }
        checked = {"accepted": [_claim("c2", ["o2"], "extrinsics repaired")], "rejected": []}

        result = merge_verified_revisions(initial, checked)

        self.assertEqual([c["claimId"] for c in result["accepted"]], ["c1", "c2"])
        self.assertEqual(result["rejected"], [])

    def test_unknown_checked_accepted_ignored(self):
        initial = {"accepted": [_claim("c1", ["o1"], "intrinsics")], "rejected": []}
        checked = {"accepted": [_claim("c999", ["o9"], "ghost claim")], "rejected": []}

        result = merge_verified_revisions(initial, checked)

        self.assertEqual([c["claimId"] for c in result["accepted"]], ["c1"])

    def test_duplicate_checked_accepted_ignored(self):
        initial = {"accepted": [_claim("c1", ["o1"], "draft intrinsics")], "rejected": []}
        checked = {
            "accepted": [_claim("c1", ["o1"], "rev a"), _claim("c1", ["o1"], "rev b")],
            "rejected": [],
        }

        result = merge_verified_revisions(initial, checked)

        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["text"], "draft intrinsics")

    def test_initial_rejection_retained_on_failed_repair(self):
        initial = {
            "accepted": [],
            "rejected": [{"claimId": "c2", "reason": "answer_incomplete", "missingQuestions": ["q"]}],
        }
        checked = {"accepted": [], "rejected": [{"claimId": "c2", "reason": "still_incomplete"}]}

        result = merge_verified_revisions(initial, checked)

        self.assertEqual(result["accepted"], [])
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(result["rejected"][0]["reason"], "answer_incomplete")

    def test_merge_does_not_mutate_inputs(self):
        initial = {
            "accepted": [_claim("c1", ["o1"], "intrinsics")],
            "rejected": [{"claimId": "c2", "reason": "answer_incomplete", "missingQuestions": ["q"]}],
        }
        checked = {"accepted": [_claim("c2", ["o2"], "extrinsics repaired")], "rejected": []}

        initial_snap = copy.deepcopy(initial)
        checked_snap = copy.deepcopy(checked)

        merge_verified_revisions(initial, checked)

        self.assertEqual(initial, initial_snap)
        self.assertEqual(checked, checked_snap)


if __name__ == "__main__":
    unittest.main()
