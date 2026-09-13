import json
import unittest
from unittest.mock import Mock, patch
from services.agent_grounded_answer import synthesize_grounded_answer


class GroundedAnswerTests(unittest.TestCase):
    def test_no_evidence_or_placeholder_does_not_call_model(self):
        with patch("llm.client.get_llm") as llm:
            result = synthesize_grounded_answer("比较", [{"sourceId": "fake", "text": "placeholder", "metadata": {"fallback": True}}], ["p1"])
        self.assertEqual(result["answerStatus"], "insufficient_evidence")
        self.assertEqual(result["findings"], [])
        llm.assert_not_called()

    def test_valid_answer_keeps_full_ids_and_reports_missing_papers(self):
        source_id = "paper-uuid-with-a-long-source-identifier-page-7"
        response = {"claims": [{"summary": "使用剪枝减少存储。", "sourceIds": [source_id]}], "limitations": []}
        model = Mock()
        model._call.return_value = json.dumps(response)
        with patch("llm.client.get_llm", return_value=model):
            result = synthesize_grounded_answer("存储如何优化", [{"sourceId": source_id, "pdfId": "p1", "text": "Pruning reduces storage."}], ["p1", "p2"])
        self.assertEqual(result["findings"][0]["sourceIds"], [source_id])
        self.assertIn(source_id, model._call.call_args.kwargs["prompt"])
        self.assertIn("p2", result["openQuestions"][0])

    def test_extracts_json_surrounded_by_explanatory_text_and_markdown(self):
        source_id = "paper-a-page-3"
        response = {"claims": [{"summary": "该方法减少训练开销。", "sourceIds": [source_id]}], "limitations": []}
        model = Mock()
        model._call.return_value = "分析完成，结果如下：\n```json\n" + json.dumps(response, ensure_ascii=False) + "\n```\n请查收。"
        with patch("llm.client.get_llm", return_value=model):
            result = synthesize_grounded_answer(
                "训练效率如何", [{"sourceId": source_id, "pdfId": "p1", "text": "Training is efficient."}], ["p1"]
            )
        self.assertEqual(result["answerStatus"], "grounded")
        self.assertEqual(result["findings"][0]["sourceIds"], [source_id])

    def test_unknown_citations_and_missing_citations_are_rejected(self):
        for ids in (["invented"], []):
            model = Mock()
            model._call.return_value = json.dumps({"claims": [{"summary": "Claim", "sourceIds": ids}]})
            with patch("llm.client.get_llm", return_value=model), self.assertRaises(ValueError):
                synthesize_grounded_answer("question", [{"sourceId": "real", "text": "evidence"}], [])

    def test_provider_failure_is_not_replaced_with_a_fake_answer(self):
        with patch("llm.client.get_llm", side_effect=RuntimeError("provider unavailable")), self.assertRaises(RuntimeError):
            synthesize_grounded_answer("question", [{"sourceId": "real", "text": "evidence"}], [])
