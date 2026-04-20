from typing import Any, Dict, List, Optional

try:
    from core.hybrid_retriever import HybridRetriever
except ModuleNotFoundError:
    HybridRetriever = None


class DummyRAG:
    @staticmethod
    def normalize_id(id_str: Any) -> str:
        import re

        if not id_str:
            return "unknown"

        return re.sub(r"[^a-zA-Z0-9.\-_]", "_", str(id_str)).lower()

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


def get_rag():
    global _rag

    if _rag is None:
        try:
            from core.rag_vector_db import LiteratureRAG

            _rag = LiteratureRAG()
        except Exception as error:
            print(f"RAG initialization failed: {error}")
            _rag = DummyRAG()

    return _rag


def get_hybrid():
    global _hybrid

    if _hybrid is None:
        if HybridRetriever is None:
            raise RuntimeError("HybridRetriever is unavailable because rank-bm25 is not installed.")

        _hybrid = HybridRetriever(get_rag())

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
    get_rag()
