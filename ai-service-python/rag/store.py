from typing import Any, Dict, List, Optional

try:
    from core.hybrid_retriever import HybridRetriever
except ModuleNotFoundError:
    HybridRetriever = None


class DummyRAG:
    is_available = False

    def __init__(self, initialization_error: Exception | None = None):
        self.initialization_error = initialization_error

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


def get_rag():
    global _rag, _hybrid, _rag_initialization_error

    if _rag is None:
        try:
            from core.rag_vector_db import LiteratureRAG

            _rag = LiteratureRAG()
            _hybrid = None
            _rag_initialization_error = None
        except Exception as error:
            print(f"RAG initialization failed: {error}")
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


def retrieve_vector_snippets(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    try:
        return get_rag().retrieve(query, top_k=top_k)
    except Exception as error:
        print(f"retrieve_vector_snippets failed: {error}")
        return []


def retrieve_hybrid_for_vector(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    try:
        return get_hybrid().retrieve(query, top_k=top_k).get("vector", [])
    except Exception as error:
        print(
            "retrieve_hybrid_for_vector failed:",
            str(error),
            f"(HybridRetriever={'set' if HybridRetriever is not None else 'None'}, hybrid={'set' if _hybrid is not None else 'None'})",
        )
        return retrieve_vector_snippets(query, top_k=top_k)


def retrieve_hybrid_results(query: str, top_k: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    try:
        results = get_hybrid().retrieve(query, top_k=top_k)
        return {
            "vector": results.get("vector", []) if isinstance(results, dict) else [],
            "bm25": results.get("bm25", []) if isinstance(results, dict) else [],
        }
    except Exception as error:
        print(
            "retrieve_hybrid_results failed:",
            str(error),
            f"(HybridRetriever={'set' if HybridRetriever is not None else 'None'}, hybrid={'set' if _hybrid is not None else 'None'})",
        )
        return {
            "vector": retrieve_vector_snippets(query, top_k=top_k),
            "bm25": [],
        }


def preload_rag() -> None:
    rag = get_rag()
    if isinstance(rag, DummyRAG):
        raise RuntimeError(f"RAG backend is unavailable: {rag.initialization_error}")
