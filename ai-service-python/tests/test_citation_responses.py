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
            patch.object(analysis_service, "_extract_claims_with_llm", return_value=[]),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        response_source_ids = {source["sourceId"] for source in response["rag_sources"]}
        emitted_source_ids = {source_id for item in response["sentenceSourceMap"] for source_id in item["sourceIds"]}

        self.assertEqual(response_source_ids, {"analysis-source-1"})
        self.assertEqual(emitted_source_ids, {"analysis-source-1"})
        self.assertIn("citationGraph", response)
        self.assertIsNone(response["citationGraph"])

    def test_deep_analysis_claims_only_reference_response_sources(self):
        axis_result = {
            "key": "contributions",
            "label": "贡献与创新",
            "question": "贡献是什么？",
            "queryPlan": {},
            "judge": {"verdict": "CORRECT", "confidence": 0.8},
            "evidence": [
                {
                    "sourceId": "analysis-source-1",
                    "text": "作者提出新的检索排序方法，并在问答实验中报告准确率提升。",
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
                    "作者提出新的检索排序方法，并在问答实验中报告准确率提升。",
                ),
            ),
            patch.object(analysis_service, "_analyze_axis", return_value=axis_result),
            patch.object(analysis_service, "_generate_structured_critical_report", return_value=report),
            patch.object(analysis_service, "_extract_claims_with_llm", return_value=[]),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        self.assertIn("claims", response)
        self.assertGreaterEqual(len(response["claims"]), 1)
        response_source_ids = {source["sourceId"] for source in response["rag_sources"]}
        claim_source_ids = {source_id for claim in response["claims"] for source_id in claim["evidenceSourceIds"]}

        self.assertTrue(claim_source_ids)
        self.assertLessEqual(claim_source_ids, response_source_ids)

    def test_deep_analysis_claim_without_evidence_is_unsupported(self):
        axis_result = {
            "key": "contributions",
            "label": "贡献与创新",
            "question": "贡献是什么？",
            "queryPlan": {},
            "judge": {"verdict": "INCORRECT", "confidence": 0.2, "missingAspects": ["实验指标"]},
            "evidence": [],
        }
        report = {
            "claimed_contributions": "作者声称提出通用框架。",
            "evidence_based_contributions": "当前证据不足。",
            "inferred_real_contributions": "当前证据不足。",
            "weaknesses": [],
            "overclaim_risks": ["缺少实验验证"],
            "missing_evidence": ["缺少实验指标"],
            "critical_analysis": "证据不足。",
        }

        with (
            patch.object(
                analysis_service,
                "_load_analysis_source",
                return_value=([], "paper_content", None, "作者声称提出通用框架。"),
            ),
            patch.object(analysis_service, "_analyze_axis", return_value=axis_result),
            patch.object(analysis_service, "_generate_structured_critical_report", return_value=report),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        self.assertEqual(response["claims"][0]["supportLevel"], "UNSUPPORTED")
        self.assertEqual(response["claims"][0]["evidenceSourceIds"], [])
        self.assertTrue(response["claims"][0]["missingEvidence"])
        self.assertIn("contributionScore", response)
        self.assertIn("riskScore", response)
        self.assertIn("noveltyDimensions", response)
        self.assertGreater(response["riskScore"]["score"], response["contributionScore"]["score"])

    def test_deep_analysis_numeric_claim_gets_table_candidate(self):
        axis_result = {
            "key": "experiments",
            "label": "实验与结果",
            "question": "实验结果是什么？",
            "queryPlan": {},
            "judge": {"verdict": "CORRECT", "confidence": 0.84},
            "evidence": [
                {
                    "sourceId": "table-source-1",
                    "text": "Table 2: Main results. The proposed method improves F1 by 20% over the baseline.",
                    "sourceType": "current_paper",
                    "pageIndex": 4,
                    "sectionId": "section-results",
                    "chunkIndex": 8,
                }
            ],
        }
        report = {
            "claimed_contributions": "作者声称 F1 提升 20%。",
            "evidence_based_contributions": "表格结果显示 F1 有提升候选证据。",
            "inferred_real_contributions": "表格结果显示 F1 有提升候选证据。",
            "weaknesses": [],
            "overclaim_risks": [],
            "missing_evidence": [],
            "critical_analysis": "找到数值候选证据，但仍需人工核对表格。",
        }

        with (
            patch.object(
                analysis_service,
                "_load_analysis_source",
                return_value=(axis_result["evidence"], "paper_content", None, axis_result["evidence"][0]["text"]),
            ),
            patch.object(analysis_service, "_analyze_axis", return_value=axis_result),
            patch.object(analysis_service, "_generate_structured_critical_report", return_value=report),
            patch.object(analysis_service, "_extract_claims_with_llm", return_value=["作者声称 F1 提升 20%。"]),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        claim = response["claims"][0]
        response_source_ids = {source["sourceId"] for source in response["rag_sources"]}
        candidate_source_ids = {item["sourceId"] for item in claim["numericEvidenceCandidates"]}

        self.assertEqual(claim["numericVerificationStatus"], "insufficient_for_auto_verification")
        self.assertEqual(candidate_source_ids, {"table-source-1"})
        self.assertLessEqual(candidate_source_ids, response_source_ids)
        self.assertEqual(claim["numericEvidenceCandidates"][0]["pageIndex"], 4)
        self.assertIn("f1", claim["numericEvidenceCandidates"][0]["metrics"])
        self.assertIn("20%", claim["numericEvidenceCandidates"][0]["numbers"])
        self.assertEqual(response["numericEvidenceSummary"]["numericClaimCount"], 1)
        self.assertEqual(response["numericEvidenceSummary"]["candidateCount"], 1)

    def test_deep_analysis_numeric_claim_without_candidate_is_not_found(self):
        axis_result = {
            "key": "experiments",
            "label": "实验与结果",
            "question": "实验结果是什么？",
            "queryPlan": {},
            "judge": {"verdict": "CORRECT", "confidence": 0.7},
            "evidence": [
                {
                    "sourceId": "experiment-source-1",
                    "text": "The paper describes the experimental setup and baseline configuration.",
                    "sourceType": "current_paper",
                }
            ],
        }
        report = {
            "claimed_contributions": "作者声称准确率提升 20%。",
            "evidence_based_contributions": "当前证据不足。",
            "inferred_real_contributions": "当前证据不足。",
            "weaknesses": [],
            "overclaim_risks": [],
            "missing_evidence": ["缺少对应表格或数值结果"],
            "critical_analysis": "没有找到对应数值片段。",
        }

        with (
            patch.object(
                analysis_service,
                "_load_analysis_source",
                return_value=(axis_result["evidence"], "paper_content", None, axis_result["evidence"][0]["text"]),
            ),
            patch.object(analysis_service, "_analyze_axis", return_value=axis_result),
            patch.object(analysis_service, "_generate_structured_critical_report", return_value=report),
            patch.object(analysis_service, "_extract_claims_with_llm", return_value=["作者声称准确率提升 20%。"]),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        self.assertEqual(response["claims"][0]["numericVerificationStatus"], "not_found")
        self.assertEqual(response["claims"][0]["numericEvidenceCandidates"], [])
        self.assertEqual(response["numericEvidenceSummary"]["numericClaimCount"], 1)
        self.assertEqual(response["numericEvidenceSummary"]["candidateCount"], 0)

    def test_deep_analysis_non_numeric_claim_is_not_applicable(self):
        axis_result = {
            "key": "contributions",
            "label": "贡献与创新",
            "question": "贡献是什么？",
            "queryPlan": {},
            "judge": {"verdict": "CORRECT", "confidence": 0.8},
            "evidence": [
                {
                    "sourceId": "claim-source-1",
                    "text": "作者提出新的检索排序方法。",
                    "sourceType": "current_paper",
                }
            ],
        }
        report = {
            "claimed_contributions": "作者提出新的检索排序方法。",
            "evidence_based_contributions": "方法描述有当前证据支撑。",
            "inferred_real_contributions": "方法描述有当前证据支撑。",
            "weaknesses": [],
            "overclaim_risks": [],
            "missing_evidence": [],
            "critical_analysis": "方法主张有证据支撑。",
        }

        with (
            patch.object(
                analysis_service,
                "_load_analysis_source",
                return_value=(axis_result["evidence"], "paper_content", None, axis_result["evidence"][0]["text"]),
            ),
            patch.object(analysis_service, "_analyze_axis", return_value=axis_result),
            patch.object(analysis_service, "_generate_structured_critical_report", return_value=report),
            patch.object(analysis_service, "_extract_claims_with_llm", return_value=["作者提出新的检索排序方法。"]),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        self.assertEqual(response["claims"][0]["numericVerificationStatus"], "not_applicable")
        self.assertEqual(response["claims"][0]["numericEvidenceCandidates"], [])
        self.assertEqual(response["numericEvidenceSummary"]["numericClaimCount"], 0)


class AnalysisClaimSupportTests(unittest.TestCase):
    def test_supported_claim_requires_experiment_or_metric_evidence(self):
        axis_results = [
            {
                "key": "contributions",
                "judge": {"verdict": "CORRECT", "confidence": 0.8},
                "evidence": [
                    {
                        "sourceId": "c1",
                        "text": "作者提出新的检索排序方法。",
                        "sourceType": "current_paper",
                    }
                ],
            },
            {
                "key": "experiments",
                "judge": {"verdict": "CORRECT", "confidence": 0.82},
                "evidence": [
                    {
                        "sourceId": "e1",
                        "text": "实验结果显示，该方法在问答准确率上提升 8.2%，并优于 baseline。",
                        "sourceType": "current_paper",
                    }
                ],
            },
        ]

        claims = analysis_service._build_claim_support_items(
            {"claimed_contributions": "作者提出新的检索排序方法。"},
            axis_results,
        )

        self.assertEqual(claims[0]["supportLevel"], "SUPPORTED")
        self.assertIn("e1", claims[0]["evidenceSourceIds"])

    def test_author_claim_only_is_partial(self):
        axis_results = [
            {
                "key": "contributions",
                "judge": {"verdict": "CORRECT", "confidence": 0.72},
                "evidence": [
                    {
                        "sourceId": "c1",
                        "text": "本文贡献是提出新的检索排序方法。",
                        "sourceType": "current_paper",
                    }
                ],
            }
        ]

        claims = analysis_service._build_claim_support_items(
            {"claimed_contributions": "作者提出新的检索排序方法。"},
            axis_results,
        )

        self.assertEqual(claims[0]["supportLevel"], "PARTIAL")
        self.assertIn("缺少", claims[0]["missingEvidence"][0])

    def test_missing_evidence_is_unsupported(self):
        claims = analysis_service._build_claim_support_items(
            {"claimed_contributions": "作者提出通用框架。"},
            [{"key": "contributions", "judge": {"verdict": "INCORRECT"}, "evidence": []}],
        )

        self.assertEqual(claims[0]["supportLevel"], "UNSUPPORTED")
        self.assertEqual(claims[0]["evidenceSourceIds"], [])
        self.assertTrue(claims[0]["missingEvidence"])

    def test_llm_parse_failure_falls_back_to_valid_claims(self):
        axis_results = [
            {
                "key": "contributions",
                "judge": {"verdict": "CORRECT", "confidence": 0.72},
                "evidence": [
                    {
                        "sourceId": "c1",
                        "text": "本文贡献是提出新的检索排序方法。",
                        "sourceType": "current_paper",
                    }
                ],
            }
        ]

        class FakeLlm:
            def _call(self, *_args, **_kwargs):
                return "not json"

        with (
            patch.object(analysis_service, "get_llm", return_value=FakeLlm()),
            patch.object(analysis_service, "parse_json_from_llm", side_effect=ValueError("bad json")),
        ):
            claims = analysis_service._build_claim_support_items(
                {"claimed_contributions": "作者提出新的检索排序方法。"},
                axis_results,
                use_llm=True,
            )

        self.assertGreaterEqual(len(claims), 1)
        self.assertLessEqual(len(claims), 6)
        self.assertTrue(all(claim["id"].startswith("claim-") for claim in claims))

    def test_contribution_assessment_rewards_supported_claims_and_axis_coverage(self):
        report = {
            "missing_evidence": [],
            "overclaim_risks": [],
        }
        claims = [
            {
                "supportLevel": "SUPPORTED",
                "missingEvidence": [],
            },
            {
                "supportLevel": "SUPPORTED",
                "missingEvidence": [],
            },
        ]
        axis_results = [
            {
                "key": "methods",
                "judge": {"verdict": "CORRECT"},
                "evidence": [{"sourceId": "m1", "text": "方法部分给出模型结构。"}],
            },
            {
                "key": "experiments",
                "judge": {"verdict": "CORRECT"},
                "evidence": [{"sourceId": "e1", "text": "实验显示准确率提升。"}],
            },
        ]

        assessment = analysis_service._build_contribution_assessment(report, claims, axis_results)

        self.assertGreaterEqual(assessment["contributionScore"]["score"], 80)
        self.assertLessEqual(assessment["riskScore"]["score"], 30)
        self.assertEqual(
            [dimension["id"] for dimension in assessment["noveltyDimensions"]],
            ["claim_support", "method_grounding", "experiment_validation", "scope_boundary"],
        )
        self.assertEqual(assessment["noveltyDimensions"][2]["status"], "strong")

    def test_contribution_assessment_penalizes_missing_evidence_and_overclaims(self):
        report = {
            "missing_evidence": ["缺少跨领域测试", "缺少消融实验"],
            "overclaim_risks": ["泛化能力表述过强"],
        }
        claims = [
            {
                "supportLevel": "UNSUPPORTED",
                "missingEvidence": ["缺少直接支撑证据"],
            },
            {
                "supportLevel": "PARTIAL",
                "missingEvidence": ["缺少实验指标或对比结果"],
            },
        ]
        axis_results = [
            {
                "key": "methods",
                "judge": {"verdict": "CORRECT"},
                "evidence": [{"sourceId": "m1", "text": "方法部分给出模型结构。"}],
            },
            {
                "key": "experiments",
                "judge": {"verdict": "INCORRECT"},
                "evidence": [],
            },
        ]

        assessment = analysis_service._build_contribution_assessment(report, claims, axis_results)

        self.assertLessEqual(assessment["contributionScore"]["score"], 55)
        self.assertGreaterEqual(assessment["riskScore"]["score"], 60)
        experiment_dimension = next(
            dimension for dimension in assessment["noveltyDimensions"] if dimension["id"] == "experiment_validation"
        )
        self.assertEqual(experiment_dimension["status"], "weak")
        self.assertTrue(any("实验" in factor for factor in assessment["riskScore"]["factors"]))


if __name__ == "__main__":
    unittest.main()
