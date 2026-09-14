import json
import unittest
from unittest.mock import patch

from schemas.requests import ChatRequest, DeepAnalysisRequest
from services import analysis_service, chat_service, critical_reading


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
            patch.object(critical_reading, "_extract_claims_with_llm", return_value=[]),
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
            patch.object(critical_reading, "_extract_claims_with_llm", return_value=[]),
        ):
            response = analysis_service.deep_analysis(DeepAnalysisRequest(paper_content="paper text"))

        self.assertIn("claims", response)
        self.assertGreaterEqual(len(response["claims"]), 1)
        # 夹具里带了旧键名，但响应不得回吐它（见 test_normalize_report_drops_inferred_alias）。
        self.assertNotIn("inferred_real_contributions", response)
        self.assertEqual(
            response["evidence_based_contributions"], "问答准确率提升有当前证据支撑。"
        )
        response_source_ids = {source["sourceId"] for source in response["rag_sources"]}
        claim_source_ids = {source_id for claim in response["claims"] for source_id in claim["evidenceSourceIds"]}

        self.assertTrue(claim_source_ids)
        self.assertLessEqual(claim_source_ids, response_source_ids)

    def test_normalize_report_drops_inferred_alias(self):
        """inferred_real_contributions 只能进、不能出。

        旧实现把它写成 evidence_based_contributions 的同义别名（逐字节相同），
        而前端 getEvidenceBasedContributions 把它当"旧载荷"回退分支：于是每个新响应
        都同时命中新旧两键，旧载荷探测变成假阳性，回退分支永不可达。
        """
        legacy_only = critical_reading._normalize_report_payload(
            {
                "claimed_contributions": "作者宣称提出了新框架。",
                "inferred_real_contributions": "旧键名里的证据结论。",
            },
            [],
        )
        # 输入侧仍兼容旧键名：内容被吸收进新键。
        self.assertEqual(legacy_only["evidence_based_contributions"], "旧键名里的证据结论。")
        self.assertNotIn("inferred_real_contributions", legacy_only)

        both_keys = critical_reading._normalize_report_payload(
            {
                "claimed_contributions": "作者宣称提出了新框架。",
                "evidence_based_contributions": "新键名优先。",
                "inferred_real_contributions": "旧键名应被忽略。",
            },
            [],
        )
        self.assertEqual(both_keys["evidence_based_contributions"], "新键名优先。")
        self.assertNotIn("inferred_real_contributions", both_keys)

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
            patch.object(critical_reading, "_extract_claims_with_llm", return_value=["作者声称 F1 提升 20%。"]),
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
            patch.object(critical_reading, "_extract_claims_with_llm", return_value=["作者声称准确率提升 20%。"]),
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
            patch.object(critical_reading, "_extract_claims_with_llm", return_value=["作者提出新的检索排序方法。"]),
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

    def test_risk_score_tracks_claim_grounding_not_report_list_length(self):
        """风险分必须随“主张能不能落地”单调上升，而不是随 LLM 写了多少条上升。

        旧公式把列表长度直接乘权重累加，实测同一篇 3DGS 三次生成分别给 4/3、5/4、
        6/5 条，riskScore 随之从 96 爬到 100，而三次的主张支撑情况完全相同；
        更荒谬的是全部主张都有支撑时也能堆到 100（“高风险”）。
        """
        axis_results = [
            {"key": "methods", "judge": {"verdict": "CORRECT"}, "evidence": [{"sourceId": "m1", "text": "方法。"}]},
            {"key": "experiments", "judge": {"verdict": "CORRECT"}, "evidence": [{"sourceId": "e1", "text": "实验。"}]},
        ]

        def assess(support_levels, missing_count, overclaim_count):
            return analysis_service._build_contribution_assessment(
                {
                    "missing_evidence": [f"缺失 {i}" for i in range(missing_count)],
                    "overclaim_risks": [f"夸大 {i}" for i in range(overclaim_count)],
                },
                [{"supportLevel": level, "missingEvidence": []} for level in support_levels],
                axis_results,
            )["riskScore"]

        all_supported = ["SUPPORTED"] * 5
        mixed = ["SUPPORTED", "SUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED"]
        none_supported = ["UNSUPPORTED"] * 5

        # 全部支撑 + 报告级列表堆得很长 → 仍必须是低风险（饱和计权）。
        verbose = assess(all_supported, 12, 12)
        self.assertEqual(verbose["level"], "low")
        # 堆到 12 条与堆到 3 条得分相同：长度买不到分数。
        self.assertEqual(verbose["score"], assess(all_supported, 3, 3)["score"])

        # 没有一条主张能落地 → 必须是高风险，即使报告级列表很短。
        ungrounded = assess(none_supported, 1, 1)
        self.assertEqual(ungrounded["level"], "high")

        # 单调性：支撑越少风险越高。
        self.assertLess(verbose["score"], assess(mixed, 2, 1)["score"])
        self.assertLess(assess(mixed, 2, 1)["score"], ungrounded["score"])

    def test_partial_claims_show_up_in_risk_summary_and_basis(self):
        """部分支撑的主张必须出现在摘要里，否则摘要与分数自相矛盾。

        实测 3DGS 那篇出现过 unsupported=0、partial=1：摘要写“检测到 0 条证据不足
        主张”，可 claimRisk 是 0.083（正是那条 PARTIAL 按半权贡献的）。用户看到
        “0 条”会以为毫无问题，而分数里明明扣了。
        """
        axis_results = [
            {"key": "methods", "judge": {"verdict": "CORRECT"}, "evidence": [{"sourceId": "m1", "text": "方法。"}]},
            {"key": "experiments", "judge": {"verdict": "CORRECT"}, "evidence": [{"sourceId": "e1", "text": "实验。"}]},
        ]
        report = {"missing_evidence": [], "overclaim_risks": []}

        risk = analysis_service._build_contribution_assessment(
            report,
            [
                {"supportLevel": "SUPPORTED", "missingEvidence": []},
                {"supportLevel": "PARTIAL", "missingEvidence": []},
            ],
            axis_results,
        )["riskScore"]

        self.assertIn("1 条部分支撑主张", risk["summary"])
        self.assertEqual(risk["basis"]["partialClaims"], 1)
        self.assertEqual(risk["basis"]["unsupportedClaims"], 0)

        all_supported = analysis_service._build_contribution_assessment(
            report,
            [{"supportLevel": "SUPPORTED", "missingEvidence": []}] * 2,
            axis_results,
        )["riskScore"]
        # 不只是文案变了：分数确实因这条 PARTIAL 而抬高。
        self.assertGreater(risk["score"], all_supported["score"])
        # 全支撑时不得多余地提“部分支撑”。
        self.assertNotIn("部分支撑", all_supported["summary"])
        self.assertEqual(all_supported["basis"]["partialClaims"], 0)


class NumericClaimDetectionTests(unittest.TestCase):
    r"""数值主张识别：中文紧邻小数时不能被漏掉。

    实测 3DGS(2308.04079v1) 那篇：模型写“PSNR 25.2条件下”时，旧正则结尾的 \b 不成立
    （Python 的 \w 含 CJK，2 与 条 之间没有词边界），数值主张被判 not_applicable；
    而同一篇另一次生成写成“PSNR 25.2 下达到”（带空格）就被识别。同一个事实，
    能不能核验取决于模型有没有多打一个空格。
    """

    def test_decimal_adjacent_to_chinese_is_detected(self):
        values = critical_reading._extract_numeric_values(
            "作者报告在训练51分钟、PSNR 25.2条件下达到相当质量。"
        )
        self.assertIn("25.2", values)

    def test_decimal_followed_by_space_is_still_detected(self):
        values = critical_reading._extract_numeric_values(
            "在 PSNR 25.2 下达到与 Mip-NeRF360 相当的质量。"
        )
        self.assertIn("25.2", values)

    def test_arxiv_style_version_id_is_not_a_decimal(self):
        values = critical_reading._extract_numeric_values("参见 2308.04079v1 的补充材料。")
        self.assertNotIn("2308.04079", values)

    def test_percent_and_spaced_decimal_in_evidence_text(self):
        values = critical_reading._extract_numeric_values(
            "该方法将F1提升8.2%，延迟降低至 12.5 ms。"
        )
        self.assertIn("8.2%", values)
        self.assertIn("12.5", values)


class _FakeLlm:
    """返回固定字符串的 LLM 替身。"""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def _call(self, *_args, **_kwargs):
        self.calls += 1
        return self._payload


class CrossLingualClaimSupportTests(unittest.TestCase):
    """中文主张 × 英文证据 —— 批判分析在产品里唯一的真实语言组合。

    网关只传 pdf_id，界面与报告全中文，而语料是英文论文。旧实现用中文滑窗 n-gram
    去子串匹配英文证据，交集恒为空，于是“原句就在证据里”也被判 UNSUPPORTED。
    实测 3DGS(2308.04079v1) 那篇 5 条主张里 3 条如此，支持等级实际由“主张里
    有没有英文专名”决定：含 tile-based/PSNR/Mip-NeRF360 的两条判 SUPPORTED，
    纯中文表述的三条判 UNSUPPORTED —— 而 chunk-2 里明明写着
    "starting from sparse points produced during camera calibration"。
    """

    CHUNK_2 = (
        "Paper: 3D Gaussian Splatting for Real-Time Radiance Field Rendering\n\n"
        "Section: Ours (93 fps)\n\n"
        "Content:\n"
        "We introduce three key elements that allow us to achieve state-of-the-art visual quality.\n"
        "First, starting from sparse points produced during camera calibration, we represent the "
        "scene with 3D Gaussians that preserve desirable properties of continuous volumetric "
        "radiance fields for scene optimization while avoiding unnecessary computation in empty space;"
    )
    CHUNK_71 = (
        "Paper: 3D Gaussian Splatting for Real-Time Radiance Field Rendering\n\n"
        "Section: DISCUSSION AND CONCLUSIONS\n\n"
        "Content:\n"
        "Our work demonstrates that -contrary to widely accepted opinion -a continuous representation "
        "is not strictly necessary to allow fast and high-quality radiance field training."
    )

    def _evidence(self):
        return [
            {
                "sourceId": "2308.04079v1.pdf-chunk-2",
                "text": self.CHUNK_2,
                "sourceType": "current_paper",
            },
            {
                "sourceId": "2308.04079v1.pdf-chunk-71",
                "text": self.CHUNK_71,
                "sourceType": "current_paper",
            },
        ]

    def _axis_results(self):
        evidence = self._evidence()
        return [
            {
                "key": "contributions",
                "label": "贡献与创新",
                "judge": {"verdict": "CORRECT", "confidence": 0.8},
                "evidence": evidence,
            },
            {
                "key": "methods",
                "label": "方法与机制",
                "judge": {"verdict": "CORRECT", "confidence": 0.8},
                "evidence": [evidence[0]],
            },
            {
                "key": "experiments",
                "label": "实验与结果",
                "judge": {"verdict": "CORRECT", "confidence": 0.8},
                "evidence": [evidence[1]],
            },
        ]

    def _build(self, payload):
        """用给定的 LLM 返回跑一次主张对齐。"""
        raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        with patch.object(critical_reading, "get_llm", return_value=_FakeLlm(raw)):
            return critical_reading._build_claim_support_items(
                {"claimed_contributions": "作者提出 3D 高斯场景表示与实时可微渲染器。"},
                self._axis_results(),
                use_llm=True,
            )

    def test_chinese_claim_with_verbatim_english_quote_is_supported(self):
        """中文主张 + 英文逐字引用 → 必须判 SUPPORTED，并带上可跳转的证据 id。

        同时钉住 claim 文本本身：旧实现把 LLM 返回的 dict 整个 str() 成主张，
        导致 dict 里的英文 quote 泄漏进主张文本、反过来被词面匹配命中（假阳性）。
        """
        claims = self._build({
            "claims": [
                {
                    "claim": "方法从相机标定产生的稀疏点初始化 3D 高斯表示。",
                    "evidenceIds": ["2308.04079v1.pdf-chunk-2"],
                    "quote": "starting from sparse points produced during camera calibration, "
                             "we represent the scene with 3D Gaussians",
                    "supportLevel": "SUPPORTED",
                }
            ]
        })

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim"], "方法从相机标定产生的稀疏点初始化 3D 高斯表示。")
        self.assertEqual(claims[0]["supportLevel"], "SUPPORTED")
        self.assertIn("2308.04079v1.pdf-chunk-2", claims[0]["evidenceSourceIds"])
        self.assertEqual(claims[0]["missingEvidence"], [])
        self.assertTrue(claims[0]["quote"])

    def test_quote_verification_tolerates_line_breaks(self):
        """真实 chunk 带 Paper/Section/Content 换行，引用校验不能因此失败。"""
        claims = self._build({
            "claims": [
                {
                    "claim": "论文论证连续表示并非快速高质量辐射场训练所必需。",
                    "evidenceIds": ["2308.04079v1.pdf-chunk-71"],
                    "quote": "a continuous representation is not strictly necessary\nto allow fast",
                    "supportLevel": "SUPPORTED",
                }
            ]
        })

        self.assertEqual(claims[0]["claim"], "论文论证连续表示并非快速高质量辐射场训练所必需。")
        self.assertEqual(claims[0]["supportLevel"], "SUPPORTED")
        self.assertIn("2308.04079v1.pdf-chunk-71", claims[0]["evidenceSourceIds"])

    def test_hallucinated_quote_is_downgraded_and_id_dropped(self):
        """模型编造的引用（原文里不存在）必须被拦住，不能变成 SUPPORTED。"""
        claims = self._build({
            "claims": [
                {
                    "claim": "论文证明连续表示是必需的。",
                    "evidenceIds": ["2308.04079v1.pdf-chunk-71"],
                    "quote": "a continuous representation is strictly necessary for radiance field training",
                    "supportLevel": "SUPPORTED",
                }
            ]
        })

        self.assertEqual(claims[0]["claim"], "论文证明连续表示是必需的。")
        self.assertNotEqual(claims[0]["supportLevel"], "SUPPORTED")
        self.assertEqual(claims[0]["evidenceSourceIds"], [])
        self.assertTrue(claims[0]["missingEvidence"])

    def test_unknown_source_id_is_rejected(self):
        """引用了不在证据池里的 sourceId → 该 id 必须被丢弃。"""
        claims = self._build({
            "claims": [
                {
                    "claim": "方法使用 tile-based 光栅化。",
                    "evidenceIds": ["2308.04079v1.pdf-chunk-999"],
                    "quote": "sparse points produced during camera calibration",
                    "supportLevel": "SUPPORTED",
                }
            ]
        })

        self.assertEqual(claims[0]["claim"], "方法使用 tile-based 光栅化。")
        self.assertNotIn("2308.04079v1.pdf-chunk-999", claims[0]["evidenceSourceIds"])
        self.assertNotEqual(claims[0]["supportLevel"], "SUPPORTED")

    def test_claim_without_alignment_reports_missing_evidence(self):
        """模型明确说找不到证据时，如实判 UNSUPPORTED 而不是靠词面碰运气。"""
        claims = self._build({
            "claims": [
                {
                    "claim": "方法在动态场景下依然稳定。",
                    "evidenceIds": [],
                    "quote": "",
                    "supportLevel": "UNSUPPORTED",
                }
            ]
        })

        self.assertEqual(claims[0]["claim"], "方法在动态场景下依然稳定。")
        self.assertEqual(claims[0]["supportLevel"], "UNSUPPORTED")
        self.assertEqual(claims[0]["evidenceSourceIds"], [])
        self.assertTrue(claims[0]["missingEvidence"])

    def test_multiple_claims_keep_independent_alignment(self):
        """多条主张各自对齐，不能共用同一批证据 id。"""
        claims = self._build({
            "claims": [
                {
                    "claim": "方法从相机标定稀疏点初始化 3D 高斯。",
                    "evidenceIds": ["2308.04079v1.pdf-chunk-2"],
                    "quote": "starting from sparse points produced during camera calibration",
                    "supportLevel": "SUPPORTED",
                },
                {
                    "claim": "论文论证连续表示并非必需。",
                    "evidenceIds": ["2308.04079v1.pdf-chunk-71"],
                    "quote": "a continuous representation is not strictly necessary",
                    "supportLevel": "SUPPORTED",
                },
            ]
        })

        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[0]["claim"], "方法从相机标定稀疏点初始化 3D 高斯。")
        self.assertEqual(claims[1]["claim"], "论文论证连续表示并非必需。")
        self.assertEqual(claims[0]["evidenceSourceIds"], ["2308.04079v1.pdf-chunk-2"])
        self.assertEqual(claims[1]["evidenceSourceIds"], ["2308.04079v1.pdf-chunk-71"])
        self.assertEqual([claim["id"] for claim in claims], ["claim-1", "claim-2"])


class EvidenceGraphTests(unittest.TestCase):
    """证据关系图必须由真实对齐关系构造，不得凭空补边。

    旧实现把 citationGraph 硬编码为 None，前端“证据关系图”卡片因而永远是空态，
    ForceGraph 成为死代码。而真实引用网络需 Semantic Scholar，本项目未配 key
    （匿名请求实测 429），所以图改用已经逐字核验过的主张—证据对齐关系。
    """

    def _sources(self):
        return [
            {"sourceId": "p.pdf-chunk-2", "pageIndex": 2, "chunkIndex": 2, "text": "sparse points ..."},
            {"sourceId": "p.pdf-chunk-71", "sectionTitle": "Conclusion", "chunkIndex": 71, "text": "continuous ..."},
        ]

    def test_graph_links_claims_to_their_evidence(self):
        graph = critical_reading._build_evidence_graph(
            [
                {
                    "id": "claim-1",
                    "claim": "方法从相机标定产生的稀疏点初始化。",
                    "supportLevel": "SUPPORTED",
                    "evidenceSourceIds": ["p.pdf-chunk-2"],
                },
                {
                    "id": "claim-2",
                    "claim": "论文论证连续表示并非必需。",
                    "supportLevel": "PARTIAL",
                    "evidenceSourceIds": ["p.pdf-chunk-71"],
                },
            ],
            self._sources(),
        )

        self.assertEqual(graph["graphType"], "claim_evidence")
        self.assertEqual(graph["nodeCount"], 4)
        self.assertEqual(graph["linkCount"], 2)
        self.assertEqual(
            [(link["source"], link["target"]) for link in graph["links"]],
            [("claim-1", "p.pdf-chunk-2"), ("claim-2", "p.pdf-chunk-71")],
        )
        self.assertTrue(all(link["relation"] == "supported_by" for link in graph["links"]))

        claim_node = next(node for node in graph["nodes"] if node["id"] == "claim-1")
        self.assertEqual(claim_node["group"], "claim")
        self.assertEqual(claim_node["supportLevel"], "SUPPORTED")
        # 证据节点用章节标题优先，没章节时退回页码。
        evidence_nodes = {node["id"]: node["name"] for node in graph["nodes"] if node["group"] == "evidence"}
        self.assertEqual(evidence_nodes["p.pdf-chunk-71"], "Conclusion")
        self.assertEqual(evidence_nodes["p.pdf-chunk-2"], "第 2 页")

    def test_unsupported_claim_stays_isolated_instead_of_being_dropped(self):
        """无证据的主张保留为孤立节点 —— 那正是“找不到落点”的视觉信号。"""
        graph = critical_reading._build_evidence_graph(
            [
                {
                    "id": "claim-1",
                    "claim": "有证据的主张。",
                    "supportLevel": "SUPPORTED",
                    "evidenceSourceIds": ["p.pdf-chunk-2"],
                },
                {
                    "id": "claim-2",
                    "claim": "没有任何证据的主张。",
                    "supportLevel": "UNSUPPORTED",
                    "evidenceSourceIds": [],
                },
            ],
            self._sources(),
        )

        self.assertIsNotNone(graph)
        node_ids = {node["id"] for node in graph["nodes"]}
        self.assertIn("claim-2", node_ids)
        self.assertNotIn("claim-2", {link["source"] for link in graph["links"]})

    def test_dangling_evidence_reference_draws_no_link(self):
        """模型编出的 sourceId 不在响应证据里时，不得画出悬空边（ForceGraph 会报错）。"""
        graph = critical_reading._build_evidence_graph(
            [
                {
                    "id": "claim-1",
                    "claim": "带悬空引用的主张。",
                    "supportLevel": "SUPPORTED",
                    "evidenceSourceIds": ["p.pdf-chunk-999", "p.pdf-chunk-2"],
                },
            ],
            self._sources(),
        )

        self.assertEqual([link["target"] for link in graph["links"]], ["p.pdf-chunk-2"])
        self.assertNotIn("p.pdf-chunk-999", {node["id"] for node in graph["nodes"]})

    def test_no_grounded_claim_yields_no_graph(self):
        """全部主张都无证据时返回 None，让前端走空态而不是画一堆孤点。"""
        self.assertIsNone(
            critical_reading._build_evidence_graph(
                [{"id": "claim-1", "claim": "无证据。", "supportLevel": "UNSUPPORTED", "evidenceSourceIds": []}],
                self._sources(),
            )
        )
        self.assertIsNone(critical_reading._build_evidence_graph([], self._sources()))
        # 引用全悬空 → 无可画边 → 同样空态。
        self.assertIsNone(
            critical_reading._build_evidence_graph(
                [{"id": "claim-1", "claim": "悬空。", "supportLevel": "SUPPORTED", "evidenceSourceIds": ["nope"]}],
                self._sources(),
            )
        )


class EvidenceNodeLabelTests(unittest.TestCase):
    """证据节点标签必须用生产真实形状验证，否则测不出线上长什么样。

    上面 EvidenceGraphTests._sources 的夹具是顶层 sectionTitle + pageIndex=2，
    那是按代码假设手写的理想形状。实测从检索层拿到的完全是另一回事：标题在
    metadata.section_title，pageIndex 是 0 基，顶层只有内部标识 sectionId。
    于是那组测试一路绿着，而线上 4 个证据节点全叫 "section-2"。本类夹具逐字段
    照抄实测 dump（2308.04079v1.pdf）。
    """

    @staticmethod
    def _source(chunk: int, section_title: str, page: int, section_id: str) -> dict:
        return {
            "sourceId": f"2308.04079v1.pdf-chunk-{chunk}",
            "id": f"2308.04079v1.pdf-chunk-{chunk}",
            "pdfId": "2308.04079v1.pdf",
            "sourceType": "chunk",
            "sectionId": section_id,
            "pageIndex": page - 1,
            "chunkIndex": chunk,
            "score": None,
            "similarity": 0.9,
            "text": "Paper: 3D Gaussian Splatting for Real-Time Radiance Field Rendering\n\nSection ...",
            "metadata": {
                "section_title": section_title,
                "file_name": "target_paper.pdf",
                "page": page,
                "id": "2308.04079v1.pdf",
                "chunk_index": chunk,
                "section_id": section_id,
                "page_index": page - 1,
                "title": "3D Gaussian Splatting for Real-Time Radiance Field Rendering",
            },
        }

    @staticmethod
    def _graph(sources: list[dict]) -> dict:
        claims = [
            {
                "id": f"claim-{index}",
                "claim": f"论文主张第 {index} 项。",
                "supportLevel": "SUPPORTED",
                "evidenceSourceIds": [source["sourceId"]],
            }
            for index, source in enumerate(sources, start=1)
        ]
        return critical_reading._build_evidence_graph(claims, sources)

    def _evidence_names(self, sources: list[dict]) -> list[str]:
        graph = self._graph(sources)
        return [node["name"] for node in graph["nodes"] if node["group"] == "evidence"]

    def test_label_comes_from_metadata_not_internal_section_id(self):
        """实测形状下必须拿到真实章节名，而不是内部标识。"""
        names = self._evidence_names([self._source(9, "INTRODUCTION", 1, "section-2")])
        self.assertEqual(names, ["INTRODUCTION"])
        self.assertNotIn("section-2", names[0])

    def test_same_section_chunks_stay_distinguishable(self):
        """实测 6 条主张的证据全落在 INTRODUCTION 的 4 个片段上。

        只显示章节名时图上是 4 个同名节点，hover 也分不出谁是谁，而且看不出
        “证据其实只来自引言”这个关键事实。这里要求彼此可区分。
        """
        sources = [self._source(chunk, "INTRODUCTION", 1, "section-2") for chunk in (9, 8, 4, 5)]
        names = self._evidence_names(sources)
        self.assertEqual(len(set(names)), 4)
        self.assertTrue(all(name.startswith("INTRODUCTION") for name in names))
        self.assertTrue(all(len(name) <= 26 for name in names))

    def test_distinct_sections_keep_clean_labels(self):
        """章节各不相同时不得多加后缀，保持标签简洁。"""
        sources = [
            self._source(9, "INTRODUCTION", 1, "section-2"),
            self._source(58, "Results and Evaluation", 8, "section-18"),
            self._source(66, "Ablations", 9, "section-19"),
        ]
        self.assertEqual(
            self._evidence_names(sources),
            ["INTRODUCTION", "Results and Evaluation", "Ablations"],
        )

    def test_first_page_evidence_reports_one_based_page(self):
        """pageIndex 是 0 基的，首页证据不得因为 page > 0 而丢掉页码。"""
        source = self._source(3, "", 1, "section-1")
        source["metadata"].pop("section_title")
        self.assertEqual(critical_reading._evidence_node_label(source), "第 1 页")

    def test_metadata_only_source_still_gets_readable_label(self):
        """顶层身份字段全缺时，从 metadata 兜底，不能退化成裸 sourceId。"""
        source = {
            "sourceId": "2308.04079v1.pdf-chunk-12",
            "metadata": {"section_title": "Method", "chunk_index": 12, "page": 3},
        }
        self.assertEqual(critical_reading._evidence_node_label(source), "Method")

        bare = {"sourceId": "p.pdf-chunk-7", "metadata": {"chunk_index": 7}}
        self.assertEqual(critical_reading._evidence_node_label(bare), "片段 7")


if __name__ == "__main__":
    unittest.main()
