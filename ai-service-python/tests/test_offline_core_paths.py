import os
import unittest
from pathlib import Path
from unittest.mock import patch

from llm import client as llm_client
from schemas.requests import PageTranslationRequest
from services import chat_service, page_translation_service, research_planner
from services.knowledge_graph_service import generate_current_paper_graph

import core.config as _config_module


def _patch_settings(**kwargs):
    patchers = [patch.object(_config_module.settings, k, v) for k, v in kwargs.items()]
    for p in patchers:
        p.start()
    return patchers


def _stop_patches(patchers):
    for p in patchers:
        p.stop()


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "llm_responses.json"


class OfflineCorePathsTests(unittest.TestCase):
    def setUp(self):
        self._settings_patches = _patch_settings(
            pixiu_llm_mode="fixture",
            pixiu_llm_fixture_path=str(FIXTURE_PATH),
            deepseek_api_key="",
        )
        llm_client._llm = None
        llm_client._translation_llm = None

    def tearDown(self):
        llm_client._llm = None
        llm_client._translation_llm = None
        _stop_patches(self._settings_patches)

    def test_text_chat_uses_offline_fixture(self):
        with patch("llm.client.requests.post") as post:
            response = chat_service._call_guarded_llm("OFFLINE_CHAT_MARKER")

        self.assertEqual(response, "固定离线问答响应。")
        post.assert_not_called()

    def test_research_plan_uses_structured_offline_fixture(self):
        with patch("llm.client.requests.post") as post:
            brief, questions = research_planner.build_research_plan(
                "OFFLINE_RESEARCH_MARKER",
                {"method": "固定方法摘要"},
                [{"sourceId": "source-1", "text": "固定论文证据"}],
            )

        self.assertEqual(brief, "固定离线研究计划")
        self.assertEqual(len(questions), 3)
        self.assertIsInstance(questions[0], dict)
        self.assertEqual(questions[0]["question"], "离线子问题一是什么？")
        self.assertEqual(questions[0]["searchKeywords"], ["offline", "sub question one"])
        self.assertEqual(questions[0]["expectedSourceTypes"], ["current_paper"])
        post.assert_not_called()

    def test_two_stage_background_graph_uses_offline_fixtures(self):
        with patch("llm.client.requests.post") as post:
            result = generate_current_paper_graph(
                paper_topic="OFFLINE_GRAPH_MARKER",
                paper_context="固定论文上下文",
                paper_structure={"method": "固定结构"},
                rag_sources=[{"sourceId": "source-1", "text": "固定论文证据"}],
                reader_profile={},
                pdf_id="offline-paper",
            )

        self.assertEqual(result["background_knowledge"], ["离线概念"])
        self.assertEqual(result["graph"]["edges"][0]["target"], "current-paper")
        post.assert_not_called()

    def test_page_translation_uses_translation_fixture(self):
        request = PageTranslationRequest(
            pageIndex=0,
            pageText="OFFLINE_TRANSLATION_MARKER",
            paperSkeleton={},
            pageLayout={
                "blocks": [
                    {
                        "id": "block-1",
                        "text": "OFFLINE_TRANSLATION_MARKER",
                        "style": {},
                    }
                ]
            },
        )

        with patch("llm.client.requests.post") as post:
            response = page_translation_service.translate_page(request)

        self.assertEqual(response["renderMode"], "overlay")
        self.assertEqual(response["translatedText"], "固定离线译文。")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
