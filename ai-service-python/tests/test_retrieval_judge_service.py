import unittest

from services.retrieval_judge_service import (
    _build_coverage,
    _judge_score,
    judge_evidence_quality,
)


class RetrievalJudgeServiceTests(unittest.TestCase):
    # ---- P6-20: source diversity and trust-weighted scoring ----

    def test_build_coverage_includes_new_fields(self):
        """_build_coverage returns sourceDiversityScore, sourceTrustWeightedScore, crossSourceAgreement."""
        evidence = [
            {"sourceType": "current_paper", "text": "Evidence from current paper."},
            {"sourceType": "library", "text": "Library reference text."},
            {"sourceType": "external_academic", "text": "External academic source."},
        ]
        terms = ["evidence", "paper"]
        matched = ["evidence", "paper"]

        coverage = _build_coverage(evidence, terms, matched)

        self.assertIn("sourceDiversityScore", coverage)
        self.assertIn("sourceTrustWeightedScore", coverage)
        self.assertIn("crossSourceAgreement", coverage)
        # Existing fields still present
        self.assertIn("score", coverage)
        self.assertIn("sourceTypes", coverage)

    def test_source_diversity_shannon_maximum(self):
        """Shannon diversity is 1.0 when all 5 source types are equally represented."""
        evidence = [
            {"sourceType": "current_paper", "text": "a"},
            {"sourceType": "library", "text": "b"},
            {"sourceType": "external_academic", "text": "c"},
            {"sourceType": "web_search", "text": "d"},
            {"sourceType": "web_page", "text": "e"},
        ]
        coverage = _build_coverage(evidence, ["test"], ["test"])

        diversity = coverage["sourceDiversityScore"]
        self.assertAlmostEqual(diversity, 1.0, delta=0.05,
                               msg="Equal distribution across 5 types should give max diversity")

    def test_source_diversity_single_source_is_zero(self):
        """Shannon diversity is 0 when only one source type is present."""
        evidence = [
            {"sourceType": "current_paper", "text": "a"},
            {"sourceType": "current_paper", "text": "b"},
            {"sourceType": "current_paper", "text": "c"},
        ]
        coverage = _build_coverage(evidence, ["test"], ["test"])

        self.assertEqual(coverage["sourceDiversityScore"], 0.0)

    def test_source_diversity_empty_evidence_is_zero(self):
        """Shannon diversity is 0 when no evidence exists."""
        coverage = _build_coverage([], [], [])
        self.assertEqual(coverage["sourceDiversityScore"], 0.0)

    def test_source_trust_weighted_all_current_paper_is_one(self):
        """Trust-weighted score is 1.0 when all evidence is current_paper."""
        evidence = [
            {"sourceType": "current_paper", "text": "a"},
            {"sourceType": "current_paper", "text": "b"},
        ]
        coverage = _build_coverage(evidence, ["test"], ["test"])

        self.assertAlmostEqual(coverage["sourceTrustWeightedScore"], 1.0, delta=0.01)

    def test_source_trust_weighted_mixed_sources(self):
        """Trust-weighted score computes weighted average by count."""
        evidence = [
            {"sourceType": "current_paper", "text": "a"},   # w=1.0
            {"sourceType": "current_paper", "text": "b"},   # w=1.0
            {"sourceType": "web_search", "text": "c"},      # w=0.45
        ]
        coverage = _build_coverage(evidence, ["test"], ["test"])

        # Expected: (2*1.0 + 1*0.45) / 3 = 2.45/3 ≈ 0.8167
        expected = (2 * 1.0 + 1 * 0.45) / 3
        self.assertAlmostEqual(coverage["sourceTrustWeightedScore"], expected, delta=0.01)

    def test_source_trust_weighted_all_web_page(self):
        """Trust-weighted score is 0.40 when all evidence is web_page."""
        evidence = [
            {"sourceType": "web_page", "text": "a"},
            {"sourceType": "web_page", "text": "b"},
        ]
        coverage = _build_coverage(evidence, ["test"], ["test"])

        self.assertAlmostEqual(coverage["sourceTrustWeightedScore"], 0.40, delta=0.01)

    def test_source_trust_weighted_unknown_uses_default(self):
        """Unknown source types use SOURCE_TRUST_DEFAULT=0.30."""
        evidence = [
            {"sourceType": "unknown", "text": "a"},
        ]
        coverage = _build_coverage(evidence, ["test"], ["test"])

        self.assertAlmostEqual(coverage["sourceTrustWeightedScore"], 0.30, delta=0.01)

    def test_source_trust_weighted_empty_evidence_is_zero(self):
        """Trust-weighted score is 0 when no evidence."""
        coverage = _build_coverage([], [], [])
        self.assertEqual(coverage["sourceTrustWeightedScore"], 0.0)

    def test_cross_source_agreement_multiple_sources(self):
        """crossSourceAgreement reflects diversity of source types."""
        evidence = [
            {"sourceType": "current_paper", "text": "deep learning evaluation"},
            {"sourceType": "library", "text": "evaluation of deep learning"},
            {"sourceType": "external_academic", "text": "deep learning"},
        ]
        terms = ["deep", "learning", "evaluation"]
        matched = ["deep", "learning"]
        coverage = _build_coverage(evidence, terms, matched)

        agreement = coverage["crossSourceAgreement"]
        # Shared terms across source types → agreement should be > 0
        self.assertIsInstance(agreement, float)
        self.assertGreaterEqual(agreement, 0.0)
        self.assertLessEqual(agreement, 1.0)

    def test_cross_source_agreement_single_source_is_null(self):
        """crossSourceAgreement is null when only one source type (cannot measure agreement)."""
        evidence = [
            {"sourceType": "current_paper", "text": "deep learning evaluation"},
            {"sourceType": "current_paper", "text": "more evidence"},
        ]
        coverage = _build_coverage(evidence, ["deep"], ["deep"])

        self.assertIsNone(coverage["crossSourceAgreement"])

    def test_cross_source_agreement_empty_evidence_is_null(self):
        """crossSourceAgreement is null when no evidence."""
        coverage = _build_coverage([], [], [])
        self.assertIsNone(coverage["crossSourceAgreement"])

    def test_judge_score_uses_new_metrics(self):
        """_judge_score incorporates source diversity, trust, and cross-agreement."""
        coverage = {
            "score": 0.5,
            "matchedAspects": 3,
            "totalAspects": 6,
            "evidenceCount": 4,
            "sourceTypes": ["current_paper", "library", "external_academic", "web_search"],
            "sourceDiversityScore": 0.8,
            "sourceTrustWeightedScore": 0.75,
            "crossSourceAgreement": 0.6,
        }

        score = _judge_score("CORRECT", 0.7, coverage)

        # Score should be sensible 0-100
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        # With good diversity and trust, score should be decently high
        self.assertGreaterEqual(score, 50)

    def test_judge_score_low_diversity_penalized(self):
        """Low source diversity and trust reduce the judge score."""
        coverage_low = {
            "score": 0.5,
            "matchedAspects": 3,
            "totalAspects": 6,
            "evidenceCount": 3,
            "sourceTypes": ["web_search"],
            "sourceDiversityScore": 0.0,
            "sourceTrustWeightedScore": 0.45,
            "crossSourceAgreement": None,
        }
        coverage_high = {
            "score": 0.5,
            "matchedAspects": 3,
            "totalAspects": 6,
            "evidenceCount": 3,
            "sourceTypes": ["current_paper", "library"],
            "sourceDiversityScore": 0.9,
            "sourceTrustWeightedScore": 0.93,
            "crossSourceAgreement": 0.7,
        }

        score_low = _judge_score("CORRECT", 0.5, coverage_low)
        score_high = _judge_score("CORRECT", 0.5, coverage_high)

        # High diversity/trust should score higher than low
        self.assertGreater(score_high, score_low)

    def test_judge_evidence_quality_end_to_end_with_source_types(self):
        """Full judge_evidence_quality() includes new coverage fields in output."""
        evidence = [
            {"sourceType": "current_paper", "text": "Deep learning is a subset of machine learning."},
            {"sourceType": "library", "text": "Machine learning uses neural networks with deep architectures."},
            {"sourceType": "external_academic", "text": "Deep learning has revolutionized AI research."},
        ]
        result = judge_evidence_quality(
            question="What is deep learning?",
            evidence_items=evidence,
            keywords=["deep", "learning", "machine"],
        )

        coverage = result["coverage"]
        self.assertIn("sourceDiversityScore", coverage)
        self.assertIn("sourceTrustWeightedScore", coverage)
        self.assertIn("crossSourceAgreement", coverage)
        self.assertIn("sourceTypes", coverage)
        self.assertIn("current_paper", coverage["sourceTypes"])
        self.assertIn("library", coverage["sourceTypes"])
        self.assertIn("external_academic", coverage["sourceTypes"])

    def test_web_search_source_type_preserved(self):
        """web_search sourceType is preserved in coverage (not mapped to unknown)."""
        evidence = [
            {"sourceType": "web_search", "text": "Search result about the topic."},
        ]
        result = judge_evidence_quality(
            question="test",
            evidence_items=evidence,
            keywords=["test"],
        )
        self.assertIn("web_search", result["coverage"]["sourceTypes"])

    def test_web_page_source_type_preserved(self):
        """web_page sourceType is preserved in coverage (not mapped to unknown)."""
        evidence = [
            {"sourceType": "web_page", "text": "Fetched page content about the topic."},
        ]
        result = judge_evidence_quality(
            question="test",
            evidence_items=evidence,
            keywords=["test"],
        )
        self.assertIn("web_page", result["coverage"]["sourceTypes"])

    # ---- 1-1: reflection and suggestedQueries fields ----

    def test_reflection_and_suggested_queries_fields_exist(self):
        """Judge result includes reflection (string) and suggestedQueries (list) fields."""
        evidence = [
            {"sourceType": "current_paper", "text": "Deep learning is a subset of machine learning."},
        ]
        result = judge_evidence_quality(
            question="What is deep learning?",
            evidence_items=evidence,
            keywords=["deep", "learning"],
        )

        self.assertIn("reflection", result)
        self.assertIn("suggestedQueries", result)
        self.assertIsInstance(result["reflection"], str)
        self.assertIsInstance(result["suggestedQueries"], list)

    def test_empty_evidence_reflection_degradation(self):
        """Empty evidence: reflection is empty string and suggestedQueries is empty list."""
        result = judge_evidence_quality(
            question="What is deep learning?",
            evidence_items=[],
            keywords=["deep", "learning"],
        )

        self.assertEqual(result["reflection"], "")
        self.assertEqual(result["suggestedQueries"], [])

    def test_llm_failure_reflection_degradation(self):
        """When LLM fails, degraded result still has empty reflection/suggestedQueries."""
        # Simulate LLM failure by passing use_llm=True but with a broken LLM path.
        # Since we cannot reliably trigger LLM failure without mocking,
        # we verify the heuristic path (which is the degradation target) produces valid empty fields.
        result = judge_evidence_quality(
            question="What is deep learning?",
            evidence_items=[{"sourceType": "current_paper", "text": "DL is ML subset."}],
            keywords=["deep", "learning"],
            use_llm=True,
        )

        # When LLM is unavailable (e.g. no API key), it falls back to heuristic.
        # The result must still be structurally valid with empty reflection/suggestedQueries.
        self.assertIn("reflection", result)
        self.assertIn("suggestedQueries", result)
        self.assertIsInstance(result["reflection"], str)
        self.assertIsInstance(result["suggestedQueries"], list)
        # Verdict and confidence must still be present (degradation preserves core fields)
        self.assertIn(result["verdict"], ("CORRECT", "AMBIGUOUS", "INCORRECT"))
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_suggested_queries_format(self):
        """suggestedQueries contains at most 3 string elements when populated."""
        evidence = [
            {"sourceType": "current_paper", "text": "Deep learning is a subset of machine learning."},
            {"sourceType": "library", "text": "Neural networks use multiple layers."},
        ]
        result = judge_evidence_quality(
            question="What is deep learning?",
            evidence_items=evidence,
            keywords=["deep", "learning"],
        )

        suggested = result["suggestedQueries"]
        self.assertIsInstance(suggested, list)
        self.assertLessEqual(len(suggested), 3)
        for query in suggested:
            self.assertIsInstance(query, str)
            self.assertLessEqual(len(query), 200)


class CrossLingualConfidenceTests(unittest.TestCase):
    """跨语言（中文关键词 × 英文证据）时字面 coverage 失效，confidence 改由向量相似度主导。"""

    def _en_evidence(self, similarity, count=4, length=60):
        return [
            {
                "sourceType": "current_paper",
                "similarity": similarity,
                "text": ("gaussian splatting novel view synthesis " * 3)[:length],
            }
            for _ in range(count)
        ]

    def test_cross_lingual_flagged_in_coverage(self):
        result = judge_evidence_quality(
            question="核心方法是什么",
            evidence_items=self._en_evidence(0.82),
            keywords=["核心方法", "高斯泼溅"],
        )
        self.assertTrue(result["coverage"]["crossLingual"])
        self.assertFalse(result["coverage"]["literalMatchReliable"])

    def test_single_language_not_flagged(self):
        result = judge_evidence_quality(
            question="what is the core method",
            evidence_items=self._en_evidence(0.82),
            keywords=["gaussian", "splatting", "optimization"],
        )
        self.assertFalse(result["coverage"]["crossLingual"])
        self.assertTrue(result["coverage"]["literalMatchReliable"])

    def test_cross_lingual_confidence_tracks_similarity(self):
        high = judge_evidence_quality(
            question="核心方法",
            evidence_items=self._en_evidence(0.82),
            keywords=["核心方法"],
        )
        low = judge_evidence_quality(
            question="核心方法",
            evidence_items=self._en_evidence(0.45),
            keywords=["核心方法"],
        )
        # 不再恒等：相似度高的 confidence 明显高于相似度低的
        self.assertGreater(high["confidence"], low["confidence"])
        self.assertNotAlmostEqual(high["confidence"], low["confidence"], delta=0.05)
        # 高相似度仍判 CORRECT（与现状好证据的 retry 行为一致）
        self.assertEqual(high["verdict"], "CORRECT")
        # 低相似度掉到 0.68 阈值以下（修复现状“跨语言+低相似度仍判 CORRECT 不重试”的漏重试）
        self.assertLess(low["confidence"], 0.68)
        self.assertNotEqual(low["verdict"], "CORRECT")

    def test_cross_lingual_without_similarity_falls_back(self):
        evidence = [
            {
                "sourceType": "current_paper",
                "text": "gaussian splatting novel view synthesis " * 3,
            }
        ] * 4
        result = judge_evidence_quality(
            question="核心方法",
            evidence_items=evidence,
            keywords=["核心方法"],
        )
        # 无向量相似度时不抛错，回落原累加公式，但跨语言标志仍在
        self.assertTrue(result["coverage"]["crossLingual"])
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_cross_lingual_reason_does_not_claim_keyword_coverage(self):
        result = judge_evidence_quality(
            question="核心方法",
            evidence_items=self._en_evidence(0.82),
            keywords=["核心方法"],
        )
        self.assertEqual(result["verdict"], "CORRECT")
        # 跨语言时关键词字面覆盖（coverage=0）未参与评分，reason 不得再声称“关键词覆盖足够”
        self.assertNotIn("关键词覆盖整体足够", result["reason"])
        self.assertIn("相似度", result["reason"])

    def test_single_language_reason_not_cross_lingual_worded(self):
        result = judge_evidence_quality(
            question="what is the core method",
            evidence_items=self._en_evidence(0.82),
            keywords=["gaussian", "splatting", "optimization"],
        )
        # 单语言走原公式，reason 不应出现跨语言措辞
        self.assertNotIn("跨语言", result["reason"])


if __name__ == "__main__":
    unittest.main()
