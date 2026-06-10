import unittest
from unittest.mock import patch

from schemas.requests import PageTranslationRequest
from services import chat_service, page_translation_service


class PageTranslationServiceTests(unittest.TestCase):
    def test_chat_service_keeps_only_translate_page_delegate(self):
        legacy_helper_names = [
            "_trim_page_text",
            "_trim_translation_reference",
            "_call_translation_with_timeout",
        ]

        for helper_name in legacy_helper_names:
            self.assertFalse(
                hasattr(chat_service, helper_name),
                f"{helper_name} should live only in page_translation_service",
            )

    def test_normalize_translated_blocks_discards_unknown_and_preserves_source_order(self):
        source_blocks = [
            {"id": "block-1", "text": "First paragraph."},
            {"id": "block-2", "text": "Second paragraph."},
            {"id": "block-3", "text": "Third paragraph."},
        ]
        payload = {
            "translatedBlocks": [
                {"id": "block-2", "translatedText": "第二段。"},
                {"id": "unknown", "translatedText": "未知。"},
                {"id": "block-1", "translatedText": "第一段。"},
                {"id": "block-3", "translatedText": ""},
            ]
        }

        translated = page_translation_service._normalize_translated_blocks(payload, source_blocks)

        self.assertEqual(
            translated,
            [
                {"id": "block-1", "translatedText": "第一段。"},
                {"id": "block-2", "translatedText": "第二段。"},
            ],
        )

    def test_chunk_layout_blocks_limits_batch_size_and_character_count(self):
        blocks = [
            {"id": "block-1", "text": "a" * 6},
            {"id": "block-2", "text": "b" * 6},
            {"id": "block-3", "text": "c" * 3},
            {"id": "block-4", "text": "d" * 3},
        ]

        batches = page_translation_service._chunk_layout_blocks(blocks, max_blocks=2, max_chars=10)

        self.assertEqual(
            [[block["id"] for block in batch] for batch in batches],
            [["block-1"], ["block-2", "block-3"], ["block-4"]],
        )

    def test_translate_page_uses_structured_blocks_without_calling_plain_fallback(self):
        request = PageTranslationRequest(
            pageText="First paragraph.\n\nSecond paragraph.",
            pageIndex=1,
            paperSkeleton={"method": "The method section."},
            pageLayout={
                "blocks": [
                    {"id": "block-1", "text": "First paragraph.", "style": {"fontSize": 10}},
                    {"id": "block-2", "text": "Second paragraph.", "style": {"fontSize": 10}},
                ]
            },
        )

        def fake_call(prompt, timeout_seconds=45):
            self.assertIn('"id": "block-1"', prompt)
            self.assertIn('"id": "block-2"', prompt)
            return (
                '{"translatedBlocks": ['
                '{"id": "block-2", "translatedText": "第二段。"},'
                '{"id": "block-1", "translatedText": "第一段。"}'
                ']}'
            )

        with patch.object(page_translation_service, "_call_translation_with_timeout", side_effect=fake_call):
            response = page_translation_service.translate_page(request)

        self.assertEqual(response["renderMode"], "overlay")
        self.assertEqual(
            response["translatedBlocks"],
            [
                {"id": "block-1", "translatedText": "第一段。"},
                {"id": "block-2", "translatedText": "第二段。"},
            ],
        )
        self.assertEqual(response["translatedText"], "第一段。\n\n第二段。")

    def test_translate_page_falls_back_to_plain_when_structured_translation_is_incomplete(self):
        request = PageTranslationRequest(
            pageText="First paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
            pageIndex=0,
            paperSkeleton={},
            pageLayout={
                "blocks": [
                    {"id": "block-1", "text": "First paragraph.", "style": {}},
                    {"id": "block-2", "text": "Second paragraph.", "style": {}},
                    {"id": "block-3", "text": "Third paragraph.", "style": {}},
                ]
            },
        )
        calls = []

        def fake_call(prompt, timeout_seconds=45):
            calls.append(prompt)
            if "待翻译文本块" in prompt:
                return '{"translatedBlocks": [{"id": "unknown", "translatedText": "未知。"}]}'
            return "纯文本兜底译文。"

        with patch.object(page_translation_service, "_call_translation_with_timeout", side_effect=fake_call):
            with patch.object(page_translation_service, "_translate_missing_blocks_individually", return_value=[]):
                response = page_translation_service.translate_page(request)

        self.assertEqual(response["renderMode"], "plain")
        self.assertEqual(response["translatedBlocks"], [])
        self.assertEqual(response["translatedText"], "纯文本兜底译文。")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
