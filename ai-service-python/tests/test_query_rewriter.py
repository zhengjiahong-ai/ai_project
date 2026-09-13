"""core/query_rewriter 的单测。

改写依赖翻译 LLM，这里全部 mock 掉：单测只关心“什么时候改写、什么时候不改写、
失败了怎么办”，译文质量交给 benchmarks/retrieval_quality 在真实语料上量化。
"""

import unittest
from unittest.mock import patch

from core import query_rewriter

ENGLISH_CORPUS = ["We propose an anchor-based gaussian representation for rendering."]
CHINESE_CORPUS = ["我们提出一种基于锚点的高斯表示用于渲染。"]


class QueryRewriterTests(unittest.TestCase):
    def setUp(self):
        query_rewriter.clear_rewrite_cache()
        # 不依赖容器环境：开关必须显式钉为开，否则在 PIXIU_QUERY_REWRITE_ENABLED=0
        # 的环境里跑测试，除了 test_disabled_by_env_switch 以外的用例会全部假失败。
        env = patch.dict("os.environ", {"PIXIU_QUERY_REWRITE_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        query_rewriter.clear_rewrite_cache()

    def test_has_cjk(self):
        self.assertTrue(query_rewriter.has_cjk("锚点高斯如何生长"))
        self.assertTrue(query_rewriter.has_cjk("Scaffold-GS 的锚点"))
        self.assertFalse(query_rewriter.has_cjk("anchor gaussians"))
        self.assertFalse(query_rewriter.has_cjk(""))
        self.assertFalse(query_rewriter.has_cjk(None))

    def test_corpus_prefers_latin(self):
        self.assertTrue(query_rewriter.corpus_prefers_latin(ENGLISH_CORPUS))
        self.assertFalse(query_rewriter.corpus_prefers_latin(CHINESE_CORPUS))
        # 空语料拿不到凭据，判为不改写，保持原查询的既有行为
        self.assertFalse(query_rewriter.corpus_prefers_latin([]))
        self.assertFalse(query_rewriter.corpus_prefers_latin(None))

    def test_english_query_is_not_rewritten(self):
        """英文查询改写成英文没有意义，还白花一次 LLM 调用。"""
        with patch("services.cross_lingual.translate_text") as translate:
            got = query_rewriter.rewrite_query("anchor gaussians", corpus_sample=ENGLISH_CORPUS)

        self.assertEqual(got, "anchor gaussians")
        translate.assert_not_called()

    def test_chinese_query_on_english_corpus_is_rewritten(self):
        with patch("services.cross_lingual.translate_text", return_value="anchor gaussians grow") as translate:
            got = query_rewriter.rewrite_query("锚点高斯如何生长", corpus_sample=ENGLISH_CORPUS)

        self.assertEqual(got, "anchor gaussians grow")
        translate.assert_called_once()

    def test_no_corpus_sample_still_rewrites(self):
        """调用方没提供语料采样时按查询语言判定，否则改写无法单独使用与测试。"""
        with patch("services.cross_lingual.translate_text", return_value="anchor gaussians grow"):
            got = query_rewriter.rewrite_query("锚点高斯如何生长")

        self.assertEqual(got, "anchor gaussians grow")

    def test_chinese_corpus_keeps_original_query(self):
        """语料本身是中文时翻译会把能直接命中的查询推到英文空间，反而变差。"""
        with patch("services.cross_lingual.translate_text") as translate:
            got = query_rewriter.rewrite_query("锚点高斯如何生长", corpus_sample=CHINESE_CORPUS)

        self.assertEqual(got, "锚点高斯如何生长")
        translate.assert_not_called()

    def test_untranslated_result_falls_back_to_original(self):
        """translate_text 失败时返回原文（仍含 CJK），不能拿它当英文查询用。"""
        with patch("services.cross_lingual.translate_text", return_value="锚点高斯如何生长"):
            got = query_rewriter.rewrite_query("锚点高斯如何生长", corpus_sample=ENGLISH_CORPUS)

        self.assertEqual(got, "锚点高斯如何生长")

    def test_translation_exception_falls_back_to_original(self):
        with patch("services.cross_lingual.translate_text", side_effect=RuntimeError("llm down")):
            got = query_rewriter.rewrite_query("锚点高斯如何生长", corpus_sample=ENGLISH_CORPUS)

        self.assertEqual(got, "锚点高斯如何生长")

    def test_empty_translation_falls_back_to_original(self):
        with patch("services.cross_lingual.translate_text", return_value="   "):
            got = query_rewriter.rewrite_query("锚点高斯如何生长", corpus_sample=ENGLISH_CORPUS)

        self.assertEqual(got, "锚点高斯如何生长")

    def test_result_is_cached_across_calls(self):
        """同一问题多轮追问只翻译一次。"""
        with patch("services.cross_lingual.translate_text", return_value="anchor gaussians") as translate:
            for _ in range(3):
                query_rewriter.rewrite_query("锚点高斯", corpus_sample=ENGLISH_CORPUS)

        self.assertEqual(translate.call_count, 1)

    def test_disabled_by_env_switch(self):
        """降级开关：翻译 LLM 出问题时不用改代码就能退回改写前行为。"""
        with (
            patch.dict("os.environ", {"PIXIU_QUERY_REWRITE_ENABLED": "0"}),
            patch("services.cross_lingual.translate_text") as translate,
        ):
            got = query_rewriter.rewrite_query("锚点高斯", corpus_sample=ENGLISH_CORPUS)

        self.assertEqual(got, "锚点高斯")
        translate.assert_not_called()

    def test_enabled_switch_accepts_common_false_values(self):
        for value in ("0", "false", "no", "off", " FALSE "):
            with patch.dict("os.environ", {"PIXIU_QUERY_REWRITE_ENABLED": value}):
                self.assertFalse(query_rewriter.rewrite_enabled(), value)

        for value in ("1", "true", "yes", ""):
            with patch.dict("os.environ", {"PIXIU_QUERY_REWRITE_ENABLED": value}):
                self.assertTrue(query_rewriter.rewrite_enabled(), value)


if __name__ == "__main__":
    unittest.main()
