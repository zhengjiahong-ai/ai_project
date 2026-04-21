import unittest
from unittest.mock import patch

from services.query_service import (
    build_chat_query_plan,
    build_retrieval_queries,
    rewrite_academic_query,
)


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

    def test_build_chat_query_plan_uses_structured_llm_json(self):
        llm_json = """
        {
          "intent": "总结实验",
          "needsRetrieval": true,
          "rewritten": "paper experiment results metrics",
          "keywords": ["实验", "结果", "指标"],
          "queries": [
            {"query": "related benchmark metrics", "scope": "library", "reason": "补充文献"},
            {"query": "paper experiment results metrics", "scope": "current_paper", "reason": "优先当前论文"}
          ],
          "answerStyle": "detailed"
        }
        """

        with patch("services.query_service.get_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.return_value = llm_json

            plan = build_chat_query_plan(
                "这篇论文的实验结果和指标是什么？",
                context="Recent conversation: user asked about experiments.",
                has_pdf=True,
            )

        self.assertEqual(plan["source"], "llm")
        self.assertEqual(plan["taskType"], "chat")
        self.assertEqual(plan["intent"], "总结实验")
        self.assertTrue(plan["needsRetrieval"])
        self.assertEqual(plan["answerStyle"], "detailed")
        self.assertEqual(plan["queries"][0]["scope"], "current_paper")
        self.assertEqual(plan["queries"][1]["scope"], "library")
        self.assertEqual(plan["rewritten"], "paper experiment results metrics")

    def test_build_chat_query_plan_falls_back_to_compatible_plan_on_llm_failure(self):
        with patch("services.query_service.get_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.side_effect = RuntimeError("planner unavailable")

            plan = build_chat_query_plan(
                "这篇论文的方法是什么？",
                context="Paper summary:\n- methods: encoder and decoder",
                has_pdf=True,
            )

        self.assertEqual(plan["source"], "fallback")
        self.assertEqual(plan["taskType"], "chat")
        self.assertEqual(plan["intent"], "解释方法")
        self.assertTrue(plan["needsRetrieval"])
        self.assertEqual(plan["answerStyle"], "concise")
        self.assertEqual(plan["queries"][0]["scope"], "current_paper")
        self.assertEqual(plan["rewritten"], "这篇论文的方法是什么？")

    def test_build_chat_query_plan_normalizes_query_count_and_field_lengths(self):
        long_query = "q" * 260
        long_reason = "r" * 200
        llm_json = f"""
        {{
          "intent": "未知类型",
          "needsRetrieval": "true",
          "rewritten": "{long_query}",
          "keywords": ["graph", "rag", "retrieval"],
          "queries": [
            {{"query": "{long_query}", "scope": "invalid", "reason": "{long_reason}"}},
            {{"query": "library comparison query", "scope": "library", "reason": "{long_reason}"}},
            {{"query": "extra query should be dropped", "scope": "library", "reason": "drop"}}
          ],
          "answerStyle": "verbose"
        }}
        """

        with patch("services.query_service.get_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.return_value = llm_json

            plan = build_chat_query_plan(
                "请详细分析这篇论文和相关工作的对比。",
                context="compare against baselines",
                has_pdf=True,
            )

        self.assertEqual(plan["intent"], "总结实验")
        self.assertEqual(plan["answerStyle"], "detailed")
        self.assertLessEqual(len(plan["queries"]), 2)
        self.assertEqual(plan["queries"][0]["scope"], "current_paper")
        self.assertIn(plan["queries"][1]["scope"], {"current_paper", "library"})
        self.assertLessEqual(len(plan["queries"][0]["query"]), 180)
        self.assertLessEqual(len(plan["queries"][0]["reason"]), 120)


if __name__ == "__main__":
    unittest.main()
