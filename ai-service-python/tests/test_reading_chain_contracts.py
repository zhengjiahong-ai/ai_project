"""阅读链路（背景补课 / 引导式学习 / 深度研究）的契约回归。

这三个功能此前几乎没有单测，而它们恰恰是用户直接点的按钮。实测跑出来的两个
真问题都长在“没人看的接口边界”上：

1. 背景补课的知识图谱根节点标签是一段 240 字的英文检索原文（_resolve_topic 的
   兜底把九千字 paper_context 压成一行截 240 返回），而前端只在做过篇章解构时
   才传得上 paper_topic，所以“没先解构就点背景补课”这条最常见路径必然踩中。
2. 引导式学习老入口把给 LLM 的整条 prompt 指令当检索式，既稀释向量，又因为
   指令里夹了中文 reading_progress 而白付一次跨语言改写的 LLM 调用。

另外，深度研究的规划/聚合与图谱生成本轮改成了温度 0 的 structured LLM（同一篇
论文两次跑必须得同一张图），这里同时钉住 get_structured_llm 契约与三个模块
可在全新解释器里独立导入 —— 路由层的同类护栏见 test_route_service_contracts。
"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from schemas.requests import BackgroundKnowledgeRequest, SocraticQuestionRequest
from services import background_knowledge_service as background_service
from services import socratic_service

SERVICE_ROOT = Path(__file__).resolve().parents[1]

# 索引片段的真实格式：Paper / Section / Content 三段。
INDEXED_CONTEXT = (
    "Current indexed paper excerpts:\n"
    "Paper: 3D Gaussian Splatting for Real-Time Radiance Field Rendering\n\n"
    "Section: Ours (93 fps)\n\n"
    "Content: Train: 51min, PSNR: 25.2 Fig.1. Our method achieves real-time rendering.\n\n"
    + "filler text " * 400
)


class BackgroundTopicTests(unittest.TestCase):
    """主题会直接当知识图谱根节点的标签展示，必须是标题级短文本。"""

    def test_topic_falls_back_to_indexed_paper_title(self):
        request = BackgroundKnowledgeRequest(pdfId="2308.04079v1.pdf")
        self.assertEqual(
            background_service._resolve_topic(request, INDEXED_CONTEXT),
            "3D Gaussian Splatting for Real-Time Radiance Field Rendering",
        )

    def test_topic_never_returns_raw_excerpts(self):
        """没有 Paper: 行时也不能把九千字检索原文当主题。"""
        request = BackgroundKnowledgeRequest(pdfId="2308.04079v1.pdf")
        context = "Current indexed paper excerpts:\n" + "Train: 51min, PSNR: 25.2 " * 300
        topic = background_service._resolve_topic(request, context)
        self.assertNotIn("Current indexed paper excerpts", topic)
        self.assertLessEqual(len(topic), 120)

    def test_structure_title_wins_over_file_name(self):
        request = BackgroundKnowledgeRequest(
            pdfId="a.pdf", paperStructure={"title": "Attention Is All You Need"}
        )
        self.assertEqual(background_service._resolve_topic(request, ""), "Attention Is All You Need")

    def test_file_name_is_the_last_resort_before_long_text(self):
        request = BackgroundKnowledgeRequest(pdfId="3dgv_holographic_video-streaming.pdf")
        self.assertEqual(
            background_service._resolve_topic(request, ""),
            "3dgv holographic video streaming",
        )

    def test_research_problem_still_used_when_no_title_anywhere(self):
        request = BackgroundKnowledgeRequest(
            pdfId=None, paperStructure={"research_problem": "如何实时渲染辐射场"}
        )
        self.assertEqual(background_service._resolve_topic(request, ""), "如何实时渲染辐射场")

    def test_explicit_topic_wins_and_is_clamped(self):
        request = BackgroundKnowledgeRequest(paper_topic="T" * 300)
        self.assertEqual(len(background_service._resolve_topic(request, "")), 120)

    def test_empty_everything_falls_back_to_placeholder(self):
        self.assertEqual(background_service._resolve_topic(BackgroundKnowledgeRequest(), ""), "当前论文")


class SocraticRetrievalQueryTests(unittest.TestCase):
    """老入口的检索式必须是论文内容，不能是给 LLM 的 prompt 指令。"""

    def _run(self, paper_content, reading_progress):
        captured = {}

        def fake_retrieve(query, top_k=3, filter_metadata=None):
            captured["query"] = query
            captured["top_k"] = top_k
            return []

        fake_llm = mock.MagicMock()
        fake_llm.return_value._call.return_value = "1. 第一问\n2. 第二问"
        with mock.patch.object(socratic_service, "retrieve_fused_evidence", fake_retrieve), \
                mock.patch.object(socratic_service, "get_llm", fake_llm):
            payload = socratic_service.generate_socratic_questions(
                SocraticQuestionRequest(
                    paper_content=paper_content, reading_progress=reading_progress
                )
            )
        return captured, payload

    def test_query_is_paper_content_without_instruction_prefix(self):
        captured, _ = self._run(
            "3D Gaussian Splatting for Real-Time Radiance Field Rendering.", "摘要"
        )
        self.assertNotIn("Generate Socratic questions", captured["query"])
        self.assertIn("3D Gaussian Splatting", captured["query"])

    def test_query_is_pure_ascii_when_content_is_english(self):
        """纯英文检索式不该触发 query_rewriter 的跨语言改写（那要白付一次 LLM 调用）。"""
        captured, _ = self._run("Real-time radiance field rendering with gaussians.", "摘要")
        self.assertNotIn("摘要", captured["query"])

    def test_query_falls_back_to_reading_progress_without_content(self):
        captured, payload = self._run("", "读到方法部分")
        self.assertEqual(captured["query"], "读到方法部分")
        self.assertEqual(payload["status"], "success")

    def test_long_content_is_clamped_to_prompt_budget(self):
        captured, _ = self._run("word " * 400, "摘要")
        self.assertLessEqual(len(captured["query"]), 300)


class ReadingChainImportTests(unittest.TestCase):
    """三个功能的模块必须能在全新解释器里独立导入。"""

    MODULES = (
        "services.background_knowledge_service",
        "services.socratic_service",
        "services.knowledge_graph_service",
        "services.research_planner",
        "services.research_task_results",
        "services.research_task_service",
    )

    def test_every_module_imports_in_a_fresh_interpreter(self):
        code = "import " + ", ".join(self.MODULES)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(SERVICE_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])

    def test_structured_llm_contract_exists(self):
        """规划/聚合/图谱现在都靠它拿温度 0 的模型，这个函数消失就是全线 ImportError。"""
        from llm.client import get_structured_llm

        self.assertTrue(callable(get_structured_llm))


if __name__ == "__main__":
    unittest.main()
