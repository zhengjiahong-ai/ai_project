import unittest
from unittest.mock import patch

from schemas.requests import ChatRequest, DeepAnalysisRequest
from services import analysis_service, chat_service


class CitationResponseTests(unittest.TestCase):
    def test_chat_response_sentence_source_map_uses_response_sources(self):
        evidence = [
            {
                "sourceId": "chat-source-1",
                "text": "本文提出新的检索排序方法，并提升问答准确率。",
                "sourceType": "current_paper",
            }
        ]

        with (
            patch.object(chat_service, "build_chat_query_plan", return_value={"queries": [], "intent": "自由问答"}),
            patch.object(
                chat_service,
                "_run_chat_agentic_retrieval",
                return_value=(evidence, "current_paper", {"verdict": "CORRECT", "confidence": 0.9}),
            ),
            patch.object(chat_service, "_call_guarded_llm", return_value="论文提出新的检索排序方法，问答准确率提升。"),
        ):
            response = chat_service.chat(ChatRequest(message="总结方法", pdfId="paper.pdf"))

        response_source_ids = {source["sourceId"] for source in response["rag_sources"]}
        emitted_source_ids = {source_id for item in response["sentenceSourceMap"] for source_id in item["sourceIds"]}

        self.assertEqual(response_source_ids, {"chat-source-1"})
        self.assertEqual(emitted_source_ids, {"chat-source-1"})

    def test_deep_analysis_response_sentence_source_map_uses_response_sources(self):
        axis_result = {
            "key": "contributions",
            "label": "贡献与创新",
            "question": "贡献是什么？",
            "queryPlan": {},
            "judge": {"verdict": "CORRECT", "confidence": 0.8},
            "evidence": [
                {
                    "sourceId": "analysis-source-1",
                    "text": "作者提出新的检索排序方法，并报告问答准确率提升。",
                    "sourceType": "current_paper",
                }
            ],
        }
        report = {
            "claimed_contributions": "作者提出新的检索排序方法。",
            "evidence_based_contributions": "问答准确率提升有当前证据支撑。",
            "inferred_real_contributions": "问答准确率提升有当前证据支撑。",
            "weaknesses": [],
            "overclaim_risks": [],
            "missing_evidence": [],
            "critical_analysis": "检索排序方法和问答准确率提升都有证据支撑。",
        }

        with (
            patch.object(
                analysis_service,
                "_load_analysis_source",
                return_value=(
                    [axis_result["evidence"][0]],
                    "paper_content",
                    None,
                    "作者提出新的检索排序方法，并报告问答准确率提升。",
                ),
            ),
            patch.object(analysis_service, "_analyze_axis", return_value=axis_result),
            patch.object(analysis_service, "_generate_structured_critical_report", return_value=report),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        response_source_ids = {source["sourceId"] for source in response["rag_sources"]}
        emitted_source_ids = {source_id for item in response["sentenceSourceMap"] for source_id in item["sourceIds"]}

        self.assertEqual(response_source_ids, {"analysis-source-1"})
        self.assertEqual(emitted_source_ids, {"analysis-source-1"})


if __name__ == "__main__":
    unittest.main()
