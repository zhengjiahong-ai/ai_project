"""Tests for shared evidence credibility model (14-2)."""
import unittest


class EvidenceCredibilityCoreTests(unittest.TestCase):
    """Tests for compute_credibility and enrich_evidence_with_credibility."""

    def test_compute_credibility_current_paper_full_trust(self):
        """Current paper with page anchor and high judge score → highest credibility."""
        from services.evidence_credibility import compute_credibility

        item = {
            "sourceId": "cp-1",
            "text": "The proposed method achieves state-of-the-art performance on benchmark X with 95% accuracy.",
            "sourceType": "current_paper",
            "pageIndex": 3,
            "judgeScore": 92,
        }
        cred = compute_credibility(item, [item])
        # Single item → cross_source_agreement=0; composite ≈0.78.
        self.assertGreater(cred["score"], 0.7)
        self.assertEqual(cred["calibration_note"], "high")
        self.assertEqual(cred["factors"]["source_type_weight"], 1.0)
        self.assertEqual(cred["factors"]["page_anchor_coverage"], 1.0)

    def test_compute_credibility_web_page_low_trust(self):
        """Web page with no page anchor and low judge score → low credibility."""
        from services.evidence_credibility import compute_credibility

        item = {
            "sourceId": "wp-1",
            "text": "blog post comment",
            "sourceType": "web_page",
            "pageIndex": None,
            "judgeScore": 20,
        }
        cred = compute_credibility(item, [item])
        self.assertLess(cred["score"], 0.45)
        self.assertIn(cred["calibration_note"], ("low", "insufficient"))
        self.assertEqual(cred["factors"]["source_type_weight"], 0.40)
        self.assertEqual(cred["factors"]["page_anchor_coverage"], 0.65)

    def test_compute_credibility_cross_source_agreement_boosts_score(self):
        """Evidence sharing keywords with other evidence gets higher cross-source agreement."""
        from services.evidence_credibility import compute_credibility

        items = [
            {"sourceId": "a", "text": "transformer model achieves 95% accuracy on benchmark X with attention mechanism", "sourceType": "current_paper", "pageIndex": 3, "judgeScore": 85},
            {"sourceId": "b", "text": "transformer based approach achieves 94% accuracy benchmark X using attention", "sourceType": "library", "pageIndex": 5, "judgeScore": 80},
            {"sourceId": "c", "text": "completely unrelated topic about climate change and carbon emissions", "sourceType": "web_search", "pageIndex": None, "judgeScore": 30},
        ]
        cred_a = compute_credibility(items[0], items)
        cred_c = compute_credibility(items[2], items)
        self.assertGreater(cred_a["factors"]["cross_source_agreement"], cred_c["factors"]["cross_source_agreement"])
        self.assertGreater(cred_a["score"], cred_c["score"])

    def test_compute_credibility_unknown_source_type(self):
        """Unknown source type falls back to default weight."""
        from services.evidence_credibility import compute_credibility, get_source_trust_default

        item = {"sourceId": "u", "text": "some text", "sourceType": "made_up_type", "pageIndex": None, "judgeScore": 50}
        cred = compute_credibility(item, [item])
        default = get_source_trust_default()
        self.assertEqual(cred["factors"]["source_type_weight"], default)

    def test_enrich_evidence_with_credibility_preserves_all_fields(self):
        """Enriched evidence items retain original fields and add credibility."""
        from services.evidence_credibility import enrich_evidence_with_credibility

        items = [
            {"sourceId": "s1", "text": "evidence text one", "sourceType": "current_paper", "pageIndex": 1},
            {"sourceId": "s2", "text": "evidence text two different content", "sourceType": "external_academic", "pageIndex": None},
        ]
        enriched = enrich_evidence_with_credibility(items)
        self.assertEqual(len(enriched), 2)
        for i, item in enumerate(enriched):
            self.assertEqual(item["sourceId"], items[i]["sourceId"])
            self.assertEqual(item["text"], items[i]["text"])
            self.assertIn("credibility", item)
            self.assertIn("score", item["credibility"])
            self.assertIn("factors", item["credibility"])
            self.assertIn("calibration_note", item["credibility"])

    def test_enrich_empty_list(self):
        """Empty evidence list returns empty list."""
        from services.evidence_credibility import enrich_evidence_with_credibility

        self.assertEqual(len(enrich_evidence_with_credibility([])), 0)

    def test_get_source_trust_weights_returns_expected_keys(self):
        """get_source_trust_weights returns all five source types."""
        from services.evidence_credibility import get_source_trust_weights

        weights = get_source_trust_weights()
        for key in ("current_paper", "library", "external_academic", "web_search", "web_page"):
            self.assertIn(key, weights)
        self.assertGreater(weights["current_paper"], weights["web_page"])


class EvidenceCredibilityIntegrationTests(unittest.TestCase):
    """Tests that credibility is wired through agent_evidence_collector."""

    def test_collect_project_evidence_returns_credibility(self):
        """Evidence items from collect_project_evidence carry credibility field (14-2)."""
        from unittest.mock import patch

        with patch("services.agent_evidence_collector.invoke_agent_tool") as mock_invoke:
            mock_invoke.return_value = (
                {"items": [{"sourceId": "s1", "text": "method achieves 95% accuracy on benchmark X", "sourceType": "current_paper", "pageIndex": 3, "judgeScore": 85}]},
                {"name": "test", "status": "succeeded", "meta": {}, "version": "1.0", "safetyScope": {}},
            )
            from services.agent_evidence_collector import collect_project_evidence

            _, _, evidence, _ = collect_project_evidence("test prompt", ["paper-1"], allow_external_search=False, allow_web_search=False)

        self.assertGreater(len(evidence), 0)
        for item in evidence:
            self.assertIn("credibility", item, f"Evidence item {item.get('sourceId')} missing credibility field")
            cred = item["credibility"]
            self.assertIn("score", cred)
            self.assertIn("factors", cred)
            self.assertIn("calibration_note", cred)
            self.assertGreaterEqual(cred["score"], 0.0)
            self.assertLessEqual(cred["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
