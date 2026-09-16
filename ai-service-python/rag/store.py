import logging
from typing import Any, Dict, List, Optional

try:
    from core.hybrid_retriever import HybridRetriever
except ModuleNotFoundError:
    HybridRetriever = None

_logger = logging.getLogger(__name__)


class DummyRAG:
    is_available = False

    def __init__(self, initialization_error: Exception | None = None):
        self.initialization_error = initialization_error
        if initialization_error is not None:
            _logger.warning(
                "RAG initialization failed, using DummyRAG fallback: %s",
                initialization_error,
            )

    @staticmethod
    def normalize_id(id_str: Any) -> str:
        return normalize_id(id_str)

    def retrieve(self, query: str, top_k: int = 3, filter_metadata: Optional[dict] = None) -> list:
        return []

    def add_literature_to_db(self, file_path: str, metadata: Optional[dict] = None) -> int:
        return 0

    def add_sections_to_db(self, sections: list, file_path: str, metadata: Optional[dict] = None) -> int:
        return 0

    def get_db_stats(self) -> int:
        return 0

    def get_documents_by_metadata(self, filter_metadata: Optional[dict] = None, limit: int = 200) -> list:
        return []


_rag = None
_hybrid = None
_rag_initialization_error = None


def normalize_id(id_str: Any) -> str:
    import re

    if not id_str:
        return "unknown"

    return re.sub(r"[^a-zA-Z0-9.\-_]", "_", str(id_str)).lower()


def is_rag_available(rag: Any | None = None) -> bool:
    target = rag if rag is not None else _rag
    return target is not None and not isinstance(target, DummyRAG)


def get_rag_initialization_error() -> Exception | None:
    return _rag_initialization_error


def invalidate_hybrid_cache() -> None:
    global _hybrid

    _hybrid = None


def get_rag():
    global _rag, _hybrid, _rag_initialization_error

    if _rag is None:
        try:
            from core.rag_vector_db import LiteratureRAG

            _rag = LiteratureRAG()
            _hybrid = None
            _rag_initialization_error = None
        except Exception as error:
            _logger.error("RAG initialization failed: %s", error)
            _rag_initialization_error = error
            return DummyRAG(error)

    return _rag


def get_hybrid():
    global _hybrid

    if _hybrid is None:
        if HybridRetriever is None:
            raise RuntimeError("HybridRetriever is unavailable because rank-bm25 is not installed.")

        rag = get_rag()
        if isinstance(rag, DummyRAG):
            raise RuntimeError(f"RAG backend is unavailable: {rag.initialization_error}")

        _hybrid = HybridRetriever(rag)

    return _hybrid


def retrieve_vector_snippets(
    query: str,
    top_k: int = 3,
    filter_metadata: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    try:
        return get_rag().retrieve(query, top_k=top_k, filter_metadata=filter_metadata)
    except Exception as error:
        _logger.warning("retrieve_vector_snippets failed: %s", error)
        return []


def _pick_channel(results: Any, channel: str) -> List[Dict[str, Any]]:
    if not isinstance(results, dict):
        return []
    value = results.get(channel)
    return value if isinstance(value, list) else []


def retrieve_fused_evidence(
    query: str,
    top_k: int = 3,
    filter_metadata: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """返回融合后的证据列表（向量主导排序 + BM25 补召回）。

    旧实现只取 results["vector"]，BM25 那一整路检索白算；
    现在术语类查询也能靠 BM25 补回向量漏掉的片段（按文本去重）。
    注意长度可达 2 × top_k，调用方需自己截断。
    """
    try:
        results = get_hybrid().retrieve(query, top_k=top_k, filter_metadata=filter_metadata)
        fused = _pick_channel(results, "fused")
        if fused:
            return fused
        return _pick_channel(results, "vector")
    except Exception as error:
        _logger.warning(
            "retrieve_fused_evidence failed: %s (HybridRetriever=%s, hybrid=%s)",
            error,
            "set" if HybridRetriever is not None else "None",
            "set" if _hybrid is not None else "None",
        )
        return retrieve_vector_snippets(query, top_k=top_k, filter_metadata=filter_metadata)


# 历史名字保留为别名：字面意思是“取混合检索的向量那一路”，已与实际语义不符。
retrieve_hybrid_for_vector = retrieve_fused_evidence


def retrieve_hybrid_results(
    query: str,
    top_k: int = 3,
    filter_metadata: Optional[dict] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    try:
        results = get_hybrid().retrieve(query, top_k=top_k, filter_metadata=filter_metadata)
        return {
            "vector": _pick_channel(results, "vector"),
            "bm25": _pick_channel(results, "bm25"),
            "fused": _pick_channel(results, "fused"),
        }
    except Exception as error:
        _logger.warning(
            "retrieve_hybrid_results failed: %s (HybridRetriever=%s, hybrid=%s)",
            error,
            "set" if HybridRetriever is not None else "None",
            "set" if _hybrid is not None else "None",
        )
        return {
            "vector": retrieve_vector_snippets(query, top_k=top_k, filter_metadata=filter_metadata),
            "bm25": [],
            "fused": [],
        }


def preload_rag() -> None:
    rag = get_rag()
    if isinstance(rag, DummyRAG):
        raise RuntimeError(f"RAG backend is unavailable: {rag.initialization_error}")
