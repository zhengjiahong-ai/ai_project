import unittest
from unittest.mock import patch

from services.retrieval_judge_service import judge_evidence_quality


class RetrievalJudgeServiceTests(unittest.TestCase):
    def test_correct_when_similarity_is_high(self):
        result = judge_evidence_quality(
            "What is the proposed method?",
            [{"text": "The proposed method uses contrastive representation learning.", "similarity": 0.91}],
            keywords=["method", "contrastive"],
        )

        self.assertEqual(result["verdict"], "CORRECT")
        self.assertGreaterEqual(result["confidence"], 0.68)
        self.assertFalse(result["shouldRetry"])
        self.assertEqual(result["missingAspects"], [])

    def test_correct_when_keywords_are_covered(self):
        result = judge_evidence_quality(
            "Explain contrastive loss.",
            [{"text": "Contrastive loss pulls positive samples together and pushes negative samples apart."}],
            keywords=["contrastive loss", "positive samples", "negative samples"],
        )

        self.assertEqual(result["verdict"], "CORRECT")
        self.assertFalse(result["shouldRetry"])

    def test_ambiguous_for_partial_evidence(self):
        result = judge_evidence_quality(
            "How are experiments and ablations evaluated?",
            [{"text": "The method is evaluated on a benchmark dataset with limited detail.", "similarity": 0.61}],
            keywords=["experiments", "ablation", "metrics"],
        )

        self.assertEqual(result["verdict"], "AMBIGUOUS")
        self.assertTrue(result["shouldRetry"])
        self.assertIn("ablation", result["missingAspects"])

    def test_incorrect_for_empty_evidence(self):
        result = judge_evidence_quality(
            "What are the reported results?",
            [],
            keywords=["results"],
        )

        self.assertEqual(result["verdict"], "INCORRECT")
        self.assertLessEqual(result["confidence"], 0.35)
        self.assertTrue(result["shouldRetry"])

    def test_incorrect_for_short_unrelated_evidence(self):
        result = judge_evidence_quality(
            "What are the ablation metrics?",
            [{"text": "Short note.", "similarity": 0.2}],
            keywords=["ablation", "metrics"],
        )

        self.assertEqual(result["verdict"], "INCORRECT")
        self.assertTrue(result["shouldRetry"])

    def test_llm_judge_invalid_json_falls_back_to_heuristic(self):
        with patch("services.retrieval_judge_service.get_llm") as mocked_llm:
            mocked_llm.return_value._call.return_value = "not json"

            result = judge_evidence_quality(
                "Explain contrastive loss.",
                [{"text": "Contrastive loss aligns positive samples.", "similarity": 0.9}],
                keywords=["contrastive loss"],
                use_llm=True,
            )

        self.assertEqual(result["verdict"], "CORRECT")

    def test_llm_judge_error_falls_back_to_heuristic(self):
        with patch("services.retrieval_judge_service.get_llm") as mocked_llm:
            mocked_llm.return_value._call.side_effect = RuntimeError("judge unavailable")

            result = judge_evidence_quality(
                "What is missing?",
                [],
                keywords=["missing"],
                use_llm=True,
            )

        self.assertEqual(result["verdict"], "INCORRECT")
        self.assertTrue(result["shouldRetry"])


if __name__ == "__main__":
    unittest.main()
