import unittest

from services.evidence_service import (
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


if __name__ == "__main__":
    unittest.main()
