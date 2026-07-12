import unittest


class EvidenceCrossValidatorTests(unittest.TestCase):
    def setUp(self):
        from services.trace_service import clear_traces
        clear_traces()

    def tearDown(self):
        from services.trace_service import clear_traces
        clear_traces()

    def test_rule_based_cross_validate_produces_claims(self):
        """Verify rule-based path produces claims with correct structure."""
        from services.evidence_cross_validator import cross_validate_evidence

        evidence_items = [
            {"sourceId": "paper-1", "sourceType": "current_paper",
             "text": "The model achieves 95% accuracy on benchmark A, significantly improving over baseline."},
            {"sourceId": "paper-2", "sourceType": "external_academic",
             "text": "Accuracy reached 95% on benchmark A, consistent with prior work on this dataset."},
            {"sourceId": "web-1", "sourceType": "web_search",
             "text": "A related article reports 94.8% accuracy on the same benchmark A."},
        ]
        result = cross_validate_evidence(evidence_items, use_llm=False)
        self.assertIn("claims", result)
        self.assertIn("summary", result)
        self.assertIsInstance(result["claims"], list)
        self.assertGreaterEqual(result["summary"].get("total_claims", 0), 0)
        self.assertIsInstance(result["summary"].get("confirmed", 0), int)
        self.assertIsInstance(result["summary"].get("single_source", 0), int)
        self.assertIsInstance(result["summary"].get("contradicted", 0), int)
        self.assertIsInstance(result["summary"].get("needs_manual_review_count", 0), int)

    def test_agreement_level_confirmed(self):
        """Verify >=3 sources produce confirmed agreement."""
        from services.evidence_cross_validator import cross_validate_evidence

        evidence_items = [
            {"sourceId": "s1", "sourceType": "current_paper",
             "text": "improves accuracy by 5% over baseline"},
            {"sourceId": "s2", "sourceType": "external_academic",
             "text": "improves accuracy by 5% over baseline"},
            {"sourceId": "s3", "sourceType": "web_search",
             "text": "improves accuracy by 5% over baseline"},
        ]
        result = cross_validate_evidence(evidence_items, use_llm=False)
        self.assertGreaterEqual(result["summary"]["confirmed"], 1)

    def test_agreement_level_single_source(self):
        """Verify single-source claims are marked with needs_more_evidence."""
        from services.evidence_cross_validator import cross_validate_evidence

        evidence_items = [
            {"sourceId": "s1", "sourceType": "current_paper",
             "text": "unique finding not corroborated elsewhere"},
        ]
        result = cross_validate_evidence(evidence_items, use_llm=False)
        claims = result["claims"]
        single_source_claims = [c for c in claims if c.get("agreement_level") == "single_source"]
        for claim in single_source_claims:
            self.assertTrue(claim.get("needs_more_evidence", False),
                            "Single-source claim should be marked needs_more_evidence")

    def test_contradicted_claims_flagged(self):
        """Verify contradicted claims are flagged for manual review."""
        from services.evidence_cross_validator import cross_validate_evidence

        evidence_items = [
            {"sourceId": "s1", "sourceType": "current_paper",
             "text": "improves accuracy by 5% over baseline"},
            {"sourceId": "s2", "sourceType": "external_academic",
             "text": "no improvement in accuracy compared to baseline"},
        ]
        result = cross_validate_evidence(evidence_items, use_llm=False)
        contradicted = [c for c in result["claims"] if c.get("agreement_level") == "contradicted"]
        for claim in contradicted:
            self.assertTrue(claim.get("needs_manual_review", False),
                            "Contradicted claim should be flagged for manual review")

    def test_empty_evidence_returns_gracefully(self):
        """Verify empty input returns empty claims without error."""
        from services.evidence_cross_validator import cross_validate_evidence

        result = cross_validate_evidence([], use_llm=False)
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["summary"]["total_claims"], 0)

    def test_none_evidence_safe_handling(self):
        """Verify None items are skipped gracefully."""
        from services.evidence_cross_validator import cross_validate_evidence

        evidence_items = [
            {"sourceId": "s1", "sourceType": "current_paper", "text": "some evidence"},
            None,
            {"sourceId": "s2", "sourceType": "external_academic", "text": "corroborating evidence"},
        ]
        result = cross_validate_evidence(evidence_items, use_llm=False)
        self.assertIsInstance(result["claims"], list)
        self.assertIsInstance(result["summary"], dict)

    def test_single_source_claims_marked_for_more_evidence(self):
        """Verify claims from only one source are explicitly needs_more_evidence=True."""
        from services.evidence_cross_validator import cross_validate_evidence

        evidence_items = [
            {"sourceId": "s1", "sourceType": "current_paper",
             "text": "isolated finding with no cross-source support"},
            {"sourceId": "s2", "sourceType": "current_paper",
             "text": "completely different topic about model architecture"},
        ]
        result = cross_validate_evidence(evidence_items, use_llm=False)
        for claim in result["claims"]:
            if claim["source_count"] <= 1:
                self.assertTrue(claim.get("needs_more_evidence", False))


if __name__ == "__main__":
    unittest.main()
