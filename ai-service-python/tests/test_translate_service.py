import unittest
from unittest.mock import patch

from schemas.requests import PageTranslationRequest
from services.chat_service import translate_page


class TranslatePageServiceTests(unittest.TestCase):
    def test_translate_page_returns_translated_payload(self):
        request = PageTranslationRequest(
            pdfId="paper-1",
            pageIndex=1,
            pageText="This is the first paragraph.\n\nThis is the second paragraph.",
            paperSkeleton={"abstract": "A short abstract."},
        )

        with patch("services.chat_service.get_translation_llm") as mocked_get_llm:
            mocked_get_llm.return_value._call.return_value = "这是第一页的译文。"
            response = translate_page(request)

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["pageIndex"], 1)
        self.assertEqual(response["sourceText"], request.pageText)
        self.assertEqual(response["translatedText"], "这是第一页的译文。")

    def test_translate_page_rejects_empty_page_text(self):
        request = PageTranslationRequest(pdfId="paper-1", pageIndex=0, pageText="   ", paperSkeleton={})

        with self.assertRaisesRegex(ValueError, "Page text cannot be empty."):
            translate_page(request)


if __name__ == "__main__":
    unittest.main()
