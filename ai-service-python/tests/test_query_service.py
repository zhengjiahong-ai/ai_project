import unittest
from unittest.mock import patch

from services.query_service import build_retrieval_queries, rewrite_academic_query


class QueryServiceTests(unittest.TestCase):
    def test_rewrite_academic_query_uses_llm_json(self):
        llm_json = """
        {
          "rewritten": "contrastive learning loss ablation study",
          "keywords": ["contrastive learning", "loss", "ablation"]
        }
        """

        with patch("services.query_service.get_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.return_value = llm_json

            plan = rewrite_academic_query(
                "这篇论文的 contrastive loss 有什么作用？",
                context="methods section",
                task_type="chat",
            )

        self.assertEqual(plan["original"], "这篇论文的 contrastive loss 有什么作用？")
        self.assertEqual(plan["rewritten"], "contrastive learning loss ablation study")
        self.assertEqual(plan["keywords"], ["contrastive learning", "loss", "ablation"])
        self.assertEqual(plan["taskType"], "chat")
        self.assertEqual(plan["source"], "llm")

    def test_rewrite_academic_query_falls_back_when_llm_fails(self):
        with patch("services.query_service.get_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.side_effect = RuntimeError("llm unavailable")

            plan = rewrite_academic_query("attention 机制是什么？", task_type="explain")

        self.assertEqual(plan["original"], "attention 机制是什么？")
        self.assertEqual(plan["rewritten"], "attention 机制是什么？")
        self.assertIn("attention", plan["keywords"])
        self.assertEqual(plan["taskType"], "explain")
        self.assertEqual(plan["source"], "fallback")

    def test_build_retrieval_queries_falls_back_on_invalid_json_and_limits_keywords(self):
        with patch("services.query_service.get_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.return_value = "not json"

            plan = build_retrieval_queries(
                "retrieval augmented generation graph neural network benchmark evaluation metric baseline dataset ablation",
                task_type="background",
            )

        self.assertEqual(plan["source"], "fallback")
        self.assertEqual(plan["taskType"], "background")
        self.assertLessEqual(len(plan["keywords"]), 8)


if __name__ == "__main__":
    unittest.main()
