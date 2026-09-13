"""向量检索 + BM25 关键词检索的混合召回。

旧实现的三个问题：
1. `d.split()` 按空白分词，中文整句只产出 1 个 token，BM25 对中文完全失效；
2. `__init__` 无条件 `rag.collection.get()` 拉全库建索引，既吃内存又让
   "在当前论文里检索"被其他论文的片段污染；
3. vector 与 bm25 两个列表并列返回、从不做融合，调用方只取 vector 时
   BM25 整路白算（旧的 `retrieve_hybrid_for_vector` 就是这个情况）。

融合策略采用“向量主导 + BM25 补召回”而不是等权 RRF，依据见 fuse_evidence 的实测数据。
"""
import logging
import re

from rank_bm25 import BM25Okapi

from core.query_rewriter import rewrite_query

_logger = logging.getLogger(__name__)

# 全库 BM25 语料上限。按 pdf 分片时几乎不会触及，仅用于兜住无过滤条件的调用。
MAX_BM25_CORPUS = 20000

# ASCII 词整词保留，CJK 连续段切字符 bigram。
# 不引入 jieba：Docker Hub 不可达 → 镜像无法重建 → 任何新依赖都会在下次 rebuild 时消失。
# 字符 bigram 是中文 BM25 的无分词库标准做法，对术语类查询（"反射系数"→反射/射系/系数）足够。
_TOKEN_RE = re.compile(
    r"[a-z0-9]+|[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+"
)

# documents 的固定入库格式，见 LiteratureRAG.add_sections_to_db。
_STORED_DOC_RE = re.compile(
    r"^Paper:\s*(?P<title>.*?)\n\nSection:\s*(?P<section>.*?)\n\nContent:\n(?P<body>.*)$",
    re.DOTALL,
)

_ALL_SCOPE = "__all__"


def bm25_text(document):
    """把入库文本还原成“章节标题 + 正文”，与向量输入保持同一表示。

    直接拿 documents 建 BM25 会让论文标题参与打分：同一篇论文的所有片段都含
    相同的标题词，等于给全库检索叠了一个与查询无关的常量偏置，还让标题里
    的普通词（model / system / analysis）拿到不该有的权重。

    注意这并不能修好等权 RRF 的排序退步（剥前缀后实测仍是 top-1 5/10），
    那是 RRF 头部权重太平坦导致的，见 fuse_evidence。
    """
    text = str(document or "")
    match = _STORED_DOC_RE.match(text)
    if not match:
        return text
    return f"Section: {match.group('section')}\n{match.group('body')}"


def tokenize(text):
    """中英混合分词：ASCII 按词、CJK 按字符 bigram。

    只产 bigram 不产单字，避免"的""是"这类高频单字把 BM25 打分拉平。
    """
    tokens = []
    for match in _TOKEN_RE.finditer(str(text or "").lower()):
        piece = match.group(0)
        if piece[0].isascii() or len(piece) == 1:
            tokens.append(piece)
        else:
            tokens.extend(piece[index:index + 2] for index in range(len(piece) - 1))

    return tokens


def fuse_evidence(vector_results, bm25_results):
    """vector 主导排序，BM25 独有的片段追加在后。

    这里刻意不用等权 RRF。实测（真实论文 28 个 chunk、10 中 + 10 英查询）
    RRF 把 top-1 命中从 7/10 拉到 5/10、top-3 从 8/10 拉到 7/10：
    1/(k+rank) 在头部太平坦（rank0 与 rank2 仅差 3%），只要某片段在向量里排 rank1、
    在 BM25 里排 rank0，它就必然压过向量 rank0 的正确项。要让向量 rank0 不被翻盘，
    BM25 权重必须小于 0.016，等于实质上不用 BM25。
    具体案例：查询 "communication model SINR"，BM25 因为 SINR 在父章节
    II. SYSTEM MODEL 里词频最高而把它顶到第一，挤掉了语义更贴切的子章节
    A. Communication Model。改成向量主导后这两个案例均恢复正确，
    top-1 / top-3 回到 7/10 与 8/10（与纯向量持平，且保留了 BM25 的补召回）。

    BM25 的真正价值是补召回（向量漏掉的精确术语、以及中文语料上的中文查询，
    实测中文 BM25 top-1 命中从 1/4 提到 4/4），不是重排。
    返回列表长度可达 2 × top_k，由下游的 limit 决定用多少。
    """
    fused = []
    seen = set()

    for item in vector_results or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        if not text or text in seen:
            continue
        seen.add(text)
        fused.append({**item, "retriever": "vector"})

    for item in bm25_results or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        if not text or text in seen:
            continue
        seen.add(text)
        fused.append({**item, "retriever": "bm25"})

    return fused


class HybridRetriever:

    def __init__(self, rag):
        self.rag = rag
        # 按检索范围分片缓存 BM25 索引：入库时 invalidate_hybrid_cache() 会重建整个对象，
        # 缓存随之失效，因此不需要额外的版本号。
        self._index_cache: dict[str, tuple[list, list, BM25Okapi | None]] = {}

    @staticmethod
    def _scope_key(filter_metadata):
        if not isinstance(filter_metadata, dict):
            return _ALL_SCOPE
        scope = filter_metadata.get("id") or filter_metadata.get("pdfId") or filter_metadata.get("pdf_id")
        return str(scope) if scope else _ALL_SCOPE

    def _build_index(self, scope):
        where = None if scope == _ALL_SCOPE else {"id": scope}
        try:
            data = self.rag.collection.get(
                where=where,
                limit=MAX_BM25_CORPUS,
                include=["documents", "metadatas"],
            )
        except Exception as error:
            _logger.warning("BM25 语料加载失败(scope=%s): %s", scope, error)
            return [], [], None

        docs = [str(doc or "") for doc in (data.get("documents") or [])]
        metas = list(data.get("metadatas") or [])
        if len(metas) < len(docs):
            metas.extend({} for _ in range(len(docs) - len(metas)))

        tokenized = [tokenize(bm25_text(doc)) for doc in docs]
        # rank_bm25 对空语料会除零，必须先判空
        bm25 = BM25Okapi(tokenized) if tokenized else None
        _logger.info("BM25 索引就绪：scope=%s，语料 %d 条", scope, len(docs))

        return docs, metas, bm25

    def _index_for(self, filter_metadata):
        scope = self._scope_key(filter_metadata)
        cached = self._index_cache.get(scope)
        if cached is None:
            cached = self._build_index(scope)
            self._index_cache[scope] = cached
        return cached

    def _bm25_search(self, query, top_k, filter_metadata):
        docs, metas, bm25 = self._index_for(filter_metadata)
        if bm25 is None or not docs:
            return []

        tokens = tokenize(query)
        if not tokens:
            return []

        scores = bm25.get_scores(tokens)
        ranked = sorted(range(len(docs)), key=lambda index: scores[index], reverse=True)

        results = []
        for index in ranked[:max(1, top_k)]:
            score = float(scores[index])
            # 零分意味着查询词与该片段完全无词汇重叠，返回它只会给下游添噪音
            if score <= 0:
                break
            results.append({
                "text": docs[index],
                "score": score,
                "metadata": metas[index] if isinstance(metas[index], dict) else {},
            })

        return results

    def retrieve(self, query, top_k=5, filter_metadata=None):
        """返回 vector / bm25 / fused 三路结果。

        fused 是向量主导、BM25 补召回的合并列表，下游应优先使用它；
        vector 与 bm25 保留是为了兼容既有调用方与前端引文展示。
        searchQuery / queryRewritten 暴露实际用于检索的查询，便于排查
        “我问的是中文，为什么返回这些片段”。
        """
        # 旧实现这里丢掉了 filter_metadata，导致"在当前论文里检索"实际搜的是全库
        original_query = str(query or "").strip()

        # 中文查询在英文语料上会坍缩到固定吸引子（实测数据见 core/query_rewriter），
        # 按语料语言决定是否改写成英文。两路都用改写后的查询：BM25 在中文查询下
        # 恒为 0 命中，改写后一并恢复成有效补召回。
        # 索引已按 scope 缓存，这里取语料采样不会产生额外 IO。
        try:
            corpus_docs = self._index_for(filter_metadata)[0]
        except Exception as error:
            _logger.warning("BM25 语料采样失败，改写将仅根据查询语言判定: %s", error)
            corpus_docs = None
        search_query = rewrite_query(original_query, corpus_sample=corpus_docs)

        vector_results = self.rag.retrieve(search_query, top_k, filter_metadata=filter_metadata)
        bm25_results = self._bm25_search(search_query, top_k, filter_metadata)
        fused = fuse_evidence(vector_results, bm25_results)

        return {
            "vector": vector_results,
            "bm25": bm25_results,
            "fused": fused,
            "searchQuery": search_query,
            "queryRewritten": search_query != original_query,
        }
