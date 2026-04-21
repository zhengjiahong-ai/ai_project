import json
import re
import unittest
from unittest.mock import patch

from schemas.requests import PageTranslationRequest
from services.chat_service import translate_page


class TranslatePageServiceTests(unittest.TestCase):
    def test_translate_page_returns_plain_payload_for_legacy_request(self):
        request = PageTranslationRequest(
            pdfId="paper-1",
            pageIndex=1,
            pageText="This is the first paragraph.\n\nThis is the second paragraph.",
            paperSkeleton={"abstract": "A short abstract."},
        )

        with patch("services.page_translation_service.get_translation_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.return_value = "这是第一页的译文。"
            response = translate_page(request)

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["pageIndex"], 1)
        self.assertEqual(response["sourceText"], request.pageText)
        self.assertEqual(response["translatedText"], "这是第一页的译文。")
        self.assertEqual(response["renderMode"], "plain")
        self.assertEqual(response["translatedBlocks"], [])

    def test_translate_page_returns_overlay_payload_when_page_layout_exists(self):
        request = PageTranslationRequest(
            pdfId="paper-1",
            pageIndex=0,
            pageText="Semantic Alignment-Enhanced Code Translation",
            paperSkeleton={"abstract": "A short abstract."},
            pageLayout={
                "viewport": {"width": 600, "height": 800},
                "blocks": [
                    {
                        "id": "block-1",
                        "text": "Semantic Alignment-Enhanced Code Translation",
                        "bbox": {"left": 0.1, "top": 0.1, "width": 0.4, "height": 0.08},
                        "style": {"fontSize": 16, "fontWeight": "bold", "italic": False},
                    }
                ],
                "excludedZonesVersion": 1,
            },
        )

        with patch("services.page_translation_service.get_translation_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.return_value = """
            {
              "translatedBlocks": [
                {
                  "id": "block-1",
                  "translatedText": "基于语义对齐增强的代码翻译"
                }
              ]
            }
            """
            response = translate_page(request)

        self.assertEqual(response["renderMode"], "overlay")
        self.assertEqual(response["translatedText"], "基于语义对齐增强的代码翻译")
        self.assertEqual(response["translatedBlocks"][0]["id"], "block-1")

    def test_translate_page_falls_back_to_plain_when_structured_json_is_invalid(self):
        request = PageTranslationRequest(
            pdfId="paper-1",
            pageIndex=0,
            pageText="Source text",
            paperSkeleton={},
            pageLayout={
                "viewport": {"width": 600, "height": 800},
                "blocks": [
                    {
                        "id": "block-1",
                        "text": "Source text",
                        "bbox": {"left": 0.1, "top": 0.1, "width": 0.2, "height": 0.1},
                    }
                ],
                "excludedZonesVersion": 1,
            },
        )

        with patch("services.page_translation_service.get_translation_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.side_effect = [
                "not json",
                RuntimeError("single block retry failed"),
                "纯文本兜底译文",
            ]
            response = translate_page(request)

        self.assertEqual(response["renderMode"], "plain")
        self.assertEqual(response["translatedText"], "纯文本兜底译文")
        self.assertEqual(response["translatedBlocks"], [])

    def test_translate_page_retries_single_block_when_structured_json_is_invalid(self):
        request = PageTranslationRequest(
            pdfId="paper-1",
            pageIndex=0,
            pageText="Source text",
            paperSkeleton={},
            pageLayout={
                "viewport": {"width": 600, "height": 800},
                "blocks": [
                    {
                        "id": "block-1",
                        "text": "Source text",
                        "bbox": {"left": 0.1, "top": 0.1, "width": 0.2, "height": 0.1},
                    }
                ],
                "excludedZonesVersion": 1,
            },
        )

        with patch("services.page_translation_service.get_translation_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.side_effect = ["not json", "单块译文"]
            response = translate_page(request)

        self.assertEqual(response["renderMode"], "overlay")
        self.assertEqual(response["translatedText"], "单块译文")
        self.assertEqual(response["translatedBlocks"], [{"id": "block-1", "translatedText": "单块译文"}])

    def test_translate_page_batches_large_structured_layout(self):
        blocks = [
            {
                "id": f"block-{index + 1}",
                "text": f"Source line {index + 1}",
                "bbox": {"left": 0.08 if index < 65 else 0.56, "top": 0.2, "width": 0.36, "height": 0.02},
            }
            for index in range(125)
        ]
        request = PageTranslationRequest(
            pdfId="paper-1",
            pageIndex=0,
            pageText="\n".join(block["text"] for block in blocks),
            paperSkeleton={},
            pageLayout={
                "viewport": {"width": 600, "height": 800},
                "blocks": blocks,
                "excludedZonesVersion": 1,
            },
        )

        def translate_batch(prompt):
            block_ids = re.findall(r'"id":\s*"(block-\d+)"', prompt)
            return json.dumps(
                {
                    "translatedBlocks": [
                        {"id": block_id, "translatedText": f"Translated {block_id}"}
                        for block_id in block_ids
                    ]
                }
            )

        with patch("services.page_translation_service.get_translation_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.side_effect = translate_batch
            response = translate_page(request)

        self.assertEqual(response["renderMode"], "overlay")
        self.assertEqual(len(response["translatedBlocks"]), 125)
        self.assertEqual(response["translatedBlocks"][0]["id"], "block-1")
        self.assertEqual(response["translatedBlocks"][-1]["id"], "block-125")

    def test_translate_page_falls_back_to_plain_without_mass_single_block_retries(self):
        blocks = [
            {
                "id": f"block-{index + 1}",
                "text": f"Source line {index + 1}",
                "bbox": {"left": 0.08, "top": 0.12 + index * 0.04, "width": 0.4, "height": 0.03},
            }
            for index in range(6)
        ]
        request = PageTranslationRequest(
            pdfId="paper-1",
            pageIndex=0,
            pageText="\n".join(block["text"] for block in blocks),
            paperSkeleton={},
            pageLayout={
                "viewport": {"width": 600, "height": 800},
                "blocks": blocks,
                "excludedZonesVersion": 1,
            },
        )

        with patch("services.page_translation_service.get_translation_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.side_effect = [
                "not json",
                "大页回退纯文本译文",
            ]
            response = translate_page(request)

        self.assertEqual(response["renderMode"], "plain")
        self.assertEqual(response["translatedText"], "大页回退纯文本译文")
        self.assertEqual(response["translatedBlocks"], [])
        self.assertEqual(mocked_get_llm.return_value._call.call_count, 2)

    def test_translate_page_rejects_empty_page_text(self):
        request = PageTranslationRequest(pdfId="paper-1", pageIndex=0, pageText="   ", paperSkeleton={})

        with self.assertRaisesRegex(ValueError, "Page text cannot be empty."):
            translate_page(request)


if __name__ == "__main__":
    unittest.main()
