import unittest

from services.evidence_service import (
    _extract_citation_terms,
    build_field_sentence_source_map,
    build_sentence_source_map,
    compact_evidence_for_response,
    normalize_evidence_items,
)


class EvidenceCitationServiceTests(unittest.TestCase):
    def test_sentence_source_map_links_sentence_to_existing_source(self):
        sources = [
            {
                "sourceId": "paper-1",
                "text": "本文提出新的检索排序方法，并在问答实验中提升准确率。",
            },
            {
                "sourceId": "paper-2",
                "text": "局限性包括低资源场景验证不足。",
            },
        ]

        references = build_sentence_source_map(
            "作者提出新的检索排序方法，实验显示问答准确率提升。",
            sources,
        )

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["sourceIds"], ["paper-1"])
        self.assertEqual(references[0]["target"], "message")
        self.assertGreaterEqual(references[0]["confidence"], 0.12)

    def test_sentence_source_map_splits_adjacent_chinese_sentences(self):
        references = build_sentence_source_map(
            "作者提出新的检索排序方法。低资源场景验证不足。",
            [
                {"sourceId": "paper-1", "text": "本文提出新的检索排序方法。"},
                {"sourceId": "paper-2", "text": "局限性包括低资源场景验证不足。"},
            ],
        )

        self.assertEqual([item["sourceIds"][0] for item in references], ["paper-1", "paper-2"])

    def test_sentence_source_map_ignores_low_overlap_and_empty_sources(self):
        self.assertEqual(build_sentence_source_map("完全无关的结论。", []), [])
        self.assertEqual(
            build_sentence_source_map(
                "完全无关的结论。",
                [{"sourceId": "paper-1", "text": "方法章节讨论卷积网络结构。"}],
            ),
            [],
        )

    def test_sentence_source_map_never_emits_unknown_source_ids(self):
        sources = [
            {"sourceId": "source-a", "text": "消融实验覆盖不够完整。"},
            {"id": "legacy-id", "text": "跨领域验证不足。"},
        ]

        references = build_sentence_source_map(
            "消融实验覆盖不够完整，跨领域验证不足。",
            sources,
            max_sources_per_sentence=3,
        )
        emitted_ids = {source_id for item in references for source_id in item["sourceIds"]}

        self.assertEqual(emitted_ids, {"source-a", "legacy-id"})

    def test_field_sentence_source_map_preserves_targets(self):
        references = build_field_sentence_source_map(
            {
                "weaknesses": ["消融实验覆盖不够完整。"],
                "critical_analysis": "跨领域验证不足，因此泛化结论需要谨慎。",
            },
            [
                {"sourceId": "source-1", "text": "消融实验覆盖不够完整。"},
                {"sourceId": "source-2", "text": "论文缺少跨领域验证，因此泛化结论需要谨慎。"},
            ],
        )

        self.assertEqual([item["target"] for item in references], ["weaknesses", "critical_analysis"])
        self.assertTrue(all(item["sourceIds"] for item in references))

    def test_normalize_evidence_promotes_location_metadata(self):
        items = normalize_evidence_items(
            [
                {
                    "text": "Paper: Demo\n\nSection: Method\n\nContent:\nmethod evidence",
                    "metadata": {
                        "id": "paper-1",
                        "chunk_index": "7",
                        "page_index": "2",
                        "section_id": "section-3",
                    },
                }
            ],
            source_type="current_paper",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["sourceId"], "paper-1-chunk-7")
        self.assertEqual(items[0]["pdfId"], "paper-1")
        self.assertEqual(items[0]["chunkIndex"], 7)
        self.assertEqual(items[0]["pageIndex"], 2)
        self.assertEqual(items[0]["sectionId"], "section-3")

    def test_normalize_evidence_top_level_location_overrides_metadata(self):
        items = normalize_evidence_items(
            [
                {
                    "sourceId": "explicit-source",
                    "text": "Evidence with explicit location.",
                    "pageIndex": 5,
                    "sectionId": "section-top",
                    "chunkIndex": 9,
                    "metadata": {
                        "page_index": 1,
                        "section_id": "section-meta",
                        "chunk_index": 2,
                    },
                }
            ],
            source_type="current_paper",
            pdf_id="paper-2",
        )

        self.assertEqual(items[0]["sourceId"], "explicit-source")
        self.assertEqual(items[0]["pdfId"], "paper-2")
        self.assertEqual(items[0]["chunkIndex"], 9)
        self.assertEqual(items[0]["pageIndex"], 5)
        self.assertEqual(items[0]["sectionId"], "section-top")

    def test_normalize_evidence_keeps_legacy_source_without_location(self):
        items = normalize_evidence_items(
            [{"id": "legacy-id", "text": "Legacy source text."}],
            source_type="library",
        )

        self.assertEqual(items[0]["sourceId"], "legacy-id")
        self.assertEqual(items[0]["text"], "Legacy source text.")
        self.assertIsNone(items[0]["pageIndex"])
        self.assertIsNone(items[0]["sectionId"])

    def test_compact_evidence_preserves_location_fields_and_legacy_id_alias(self):
        compacted = compact_evidence_for_response(
            [
                {
                    "text": "Evidence text.",
                    "metadata": {
                        "id": "paper-3",
                        "chunk_index": 4,
                        "pageIndex": 8,
                        "sectionId": "section-9",
                    },
                }
            ]
        )

        self.assertEqual(compacted[0]["id"], "paper-3-chunk-4")
        self.assertEqual(compacted[0]["sourceId"], "paper-3-chunk-4")
        self.assertEqual(compacted[0]["pdfId"], "paper-3")
        self.assertEqual(compacted[0]["chunkIndex"], 4)
        self.assertEqual(compacted[0]["pageIndex"], 8)
        self.assertEqual(compacted[0]["sectionId"], "section-9")


class CrossLingualCitationTests(unittest.TestCase):
    """中文报告句 × 英文证据 —— 批判分析在产品里唯一的真实语言组合。

    网关只传 pdf_id，报告字段全中文，而语料是英文论文。旧打分用
    len(overlap) / len(sentence_terms)，而 sentence_terms 把中文段展开成
    全部 2/3/4-gram（实测单句 67–137 项），这些项永远不可能与英文证据相交，
    分母因此被污染：3DGS(2308.04079v1) 那篇 29 个报告句 0 条过阈、
    最高仅 0.0597、中位数 0.0000（MIN_CITATION_SCORE = 0.12）。
    前端「结论引用」卡片是 length > 0 条件渲染，于是它从来不出现。
    """

    # 实测那份响应里的真实报告句形状（单句 143 个词项）。
    # 必须用这个长度：短句（33 词项）在旧公式下也有 0.1212，恰好过阈，
    # 拿它做夹具会把修复误证成“本来就对”。长句旧分 0.0280、新分 1.0000。
    REPORT_SENTENCE = (
        "在约 51min 训练、PSNR 25.2 的条件下达到与 Mip-NeRF360 相当甚至略优的画质，"
        "同时把单张图像的渲染开销压到实时水平，这说明连续表示并非高质量辐射场训练所必需。"
    )
    EVIDENCE_TEXT = (
        "Training takes about 51min and reaches PSNR 25.2 on Mip-NeRF360, "
        "matching or slightly exceeding prior radiance field methods. "
        "This shows a continuous representation is not strictly necessary."
    )

    def test_chinese_sentence_links_to_english_evidence_via_shared_anchors(self):
        """专名与数值是跨语言唯一可靠的锚点，必须能把句子接到证据上。

        断言 0.5 而不是 MIN_CITATION_SCORE：旧分母污染下这句只有 0.0280，
        仅断言“过阈”无法区分修复与巧合。
        """
        references = build_sentence_source_map(
            self.REPORT_SENTENCE,
            [{"sourceId": "2308.04079v1.pdf-chunk-58", "text": self.EVIDENCE_TEXT}],
        )

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["sourceIds"], ["2308.04079v1.pdf-chunk-58"])
        self.assertGreaterEqual(references[0]["confidence"], 0.5)

    def test_chinese_sentence_without_shared_anchor_stays_unlinked(self):
        """精度护栏：没有共享锚点时宁可不连，也不能编造引用。

        改分母最容易犯的就是这个错 —— 把分数抬高到连无关证据也被连上。
        """
        references = build_sentence_source_map(
            "作者声称该方法显著优于既有方案。",
            [{"sourceId": "chunk-1", "text": "We propose a novel method that outperforms baselines."}],
        )

        self.assertEqual(references, [])

    def test_single_shared_conjunction_does_not_link_unrelated_evidence(self):
        """跨书写系统时单个共享 token 不足以定引用。

        这是改分母后新出现的假阳性：句里的 and 属于专名 Tanks and Temples，
        而无关证据里的 and 只是连词，两者相同纯属巧合。旧公式因分母被
        中文 n-gram 撑大而“意外地”挡住了它，不能把修正建立在这种巧合上。
        """
        references = build_sentence_source_map(
            "实验在 Tanks and Temples 上同样保持了实时渲染帧率。",
            [
                {"sourceId": "chunk-58", "text": self.EVIDENCE_TEXT},
                {
                    "sourceId": "chunk-61",
                    "text": "On Tanks and Temples the method keeps real-time rendering frame rates.",
                },
            ],
            max_sources_per_sentence=3,
        )

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["sourceIds"], ["chunk-61"])

    def test_same_language_confidence_is_bit_identical_to_flat_formula(self):
        """同语言配对的分数必须与按书写系统分类之前逐位一致。

        这条守的是爆炸半径：build_sentence_source_map 同时服务 chat 路径
        （target="message"），改打分不能扰动已经能用的同语言场景。
        """
        cases = [
            (
                "作者提出新的检索排序方法，实验显示问答准确率提升。",
                "本文提出新的检索排序方法，并在问答实验中提升准确率。",
            ),
            (
                "The method reaches PSNR 25.2 on the Mip-NeRF360 benchmark.",
                "Training reaches PSNR 25.2 on Mip-NeRF360 in about 51min.",
            ),
            (
                "在 Mip-NeRF360 上该方法达到 PSNR 25.2，训练耗时约 51min。",
                "在 Mip-NeRF360 数据集上，PSNR 达到 25.2，训练约 51min 完成。",
            ),
        ]

        for sentence, source_text in cases:
            with self.subTest(sentence=sentence[:24]):
                references = build_sentence_source_map(
                    sentence, [{"sourceId": "src", "text": source_text}]
                )
                sentence_terms = _extract_citation_terms(sentence)
                source_terms = _extract_citation_terms(source_text)
                expected = len(sentence_terms & source_terms) / len(sentence_terms)

                self.assertEqual(len(references), 1)
                self.assertEqual(references[0]["confidence"], round(expected, 2))

    def test_field_map_yields_references_for_chinese_report_over_english_corpus(self):
        """产品验收口径：中文字段 × 英文语料，字段级映射必须非空。"""
        references = build_field_sentence_source_map(
            {
                "critical_analysis": (
                    f"{self.REPORT_SENTENCE}作者声称该方法显著优于既有方案。"
                ),
                "claimed_contributions": "实验在 Tanks and Temples 上同样保持了实时渲染帧率。",
            },
            [
                {"sourceId": "chunk-58", "text": self.EVIDENCE_TEXT},
                {
                    "sourceId": "chunk-61",
                    "text": "On Tanks and Temples the method keeps real-time rendering frame rates.",
                },
            ],
        )

        self.assertTrue(references)
        self.assertEqual(
            {item["target"] for item in references},
            {"critical_analysis", "claimed_contributions"},
        )
        # 无锚点的那句不得混进来（它没有 ASCII token，连不上英文证据）。
        self.assertTrue(
            all("作者声称该方法显著优于既有方案" not in item["sentence"] for item in references)
        )


if __name__ == "__main__":
    unittest.main()
