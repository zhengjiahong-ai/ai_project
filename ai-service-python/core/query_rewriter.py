"""检索查询的跨语言改写。

问题：多语言小模型（intfloat/multilingual-e5-small，384 维）在纯英文语料上处理中文
查询时，top-1 结果不是随机错，而是**系统性坍缩到同一篇论文**。实测（7 篇 3DGS 论文、
352 chunk）10 个中文查询有 7 个 top-1 落在同一篇仅占库 15% chunk 的论文上，而语义
等价的英文查询 6/6 命中 6 篇不同论文。把 4 个失败的中文查询译成英文后 4/4 修正为
正确 top-1。

坍缩还会让名义命中率被高估：当坍缩目标恰好是某些查询的期望答案时产生假阳性，
所以评估跨语言检索质量要先看 top-1 的目标分布是否集中于单一文档。

BM25 路在同一场景下恒为 0 命中（中文 token 与英文语料无词汇重叠），改写后一并恢复，
因此混合检索的两路都应使用改写后的查询。

只在“查询含 CJK 且语料以拉丁文为主”时改写：语料本身是中文时，翻译会把本来能直接
命中的查询推到英文语义空间，反而变差。
"""

from __future__ import annotations

import logging
import os
import re

_logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# 语料里 CJK 字符占（CJK + 拉丁）比例低于此值即视为英文语料。
# 英文论文正文该比例接近 0，中文论文通常在 0.3 以上，中间留了很宽的安全带。
_CJK_CORPUS_RATIO = 0.1

# 采样多少条片段来判断语料语言。片段本身较长，20 条足以稳定判定，
# 且这些文本来自 BM25 已缓存的索引，不产生额外 IO。
_CORPUS_SAMPLE_SIZE = 20

_TRANSLATE_CACHE: dict[str, str] = {}
_TRANSLATE_CACHE_LIMIT = 256

# 运维降级开关：改写依赖翻译 LLM，一旦它不可用或译文质量出问题，
# 可以不用改代码就把检索行为退回改写前。benchmarks/retrieval_quality 也靠它做 A/B。
_ENABLED_ENV = "PIXIU_QUERY_REWRITE_ENABLED"
_DISABLED_VALUES = {"0", "false", "no", "off"}


def rewrite_enabled() -> bool:
    """跨语言改写是否开启（默认开）。每次调用读环境，便于测试里 monkeypatch。"""
    return os.environ.get(_ENABLED_ENV, "1").strip().lower() not in _DISABLED_VALUES


def has_cjk(text: str) -> bool:
    """是否含中日韩统一表意文字。"""
    return bool(_CJK_RE.search(str(text or "")))


def corpus_prefers_latin(sample_texts) -> bool:
    """采样语料是否以拉丁文为主。

    空语料返回 False —— 无凭据时不改写，保持原查询的既有行为。
    """
    if isinstance(sample_texts, (list, tuple)):
        sample = "\n".join(str(text or "") for text in sample_texts[:_CORPUS_SAMPLE_SIZE])
    else:
        sample = str(sample_texts or "")

    cjk = len(_CJK_RE.findall(sample))
    latin = len(_LATIN_RE.findall(sample))
    if cjk + latin == 0:
        return False
    return cjk / (cjk + latin) < _CJK_CORPUS_RATIO


def _translate_to_english(text: str) -> str:
    """调用既有翻译 LLM 把查询译成英文，任何异常都回退原文。

    复用 services.cross_lingual.translate_text：它走项目已有的翻译模型、带 20 秒
    超时、失败时返回原文，不需要新增依赖。延迟导入以避免 core -> services 的
    模块级循环依赖（项目既有惯例，如 llm/client.py 延迟导入 services.llm_cache）。
    """
    try:
        from services.cross_lingual import translate_text

        translated = (translate_text(text, source_lang="zh", target_lang="en") or "").strip()
    except Exception as error:
        _logger.warning("查询改写失败，回退原查询: %s", error)
        return text

    # translate_text 失败时返回原文；仍含 CJK 说明没译出来，不要拿它当英文查询用
    if not translated or has_cjk(translated):
        return text
    return translated


def rewrite_query(query: str, corpus_sample=None) -> str:
    """把中文检索查询改写成英文，返回实际用于检索的查询。

    不改写的四种情况，均直接返回原查询：
    1. 降级开关 PIXIU_QUERY_REWRITE_ENABLED 置为 0/false/no/off；
    2. 查询本身不含 CJK（英文查询改写成英文没有意义，还白花一次 LLM 调用）；
    3. 语料以中文为主（中文查询能直接命中，翻译反而变差）；
    4. 翻译失败或译文中仍含 CJK。

    结果按原查询缓存，同一问题多轮追问时只翻译一次。
    """
    text = str(query or "").strip()
    if not text or not rewrite_enabled() or not has_cjk(text):
        return text

    if corpus_sample is not None and not corpus_prefers_latin(corpus_sample):
        return text

    cached = _TRANSLATE_CACHE.get(text)
    if cached is not None:
        return cached

    rewritten = _translate_to_english(text)

    if len(_TRANSLATE_CACHE) >= _TRANSLATE_CACHE_LIMIT:
        _TRANSLATE_CACHE.clear()
    _TRANSLATE_CACHE[text] = rewritten

    if rewritten != text:
        _logger.info("检索查询已跨语言改写: %r -> %r", text[:60], rewritten[:120])
    return rewritten


def clear_rewrite_cache() -> None:
    """清空改写缓存，供测试与语料切换后使用。"""
    _TRANSLATE_CACHE.clear()
