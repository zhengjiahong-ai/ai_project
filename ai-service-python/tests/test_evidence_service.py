import unittest

from services.evidence_service import (
    build_field_sentence_source_map,
    build_sentence_source_map,
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


if __name__ == "__main__":
    unittest.main()
