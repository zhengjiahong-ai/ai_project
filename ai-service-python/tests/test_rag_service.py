import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch

from rag import store
from rag.store import DummyRAG
from services import rag_service


class FakeUploadFile:
    def __init__(self, filename="paper.pdf", content=b"%PDF-1.4"):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


class FakeRAG:
    def __init__(self, chunk_num=2, total_chunks=7):
        self.chunk_num = chunk_num
        self.total_chunks = total_chunks
        self.added_file_path = None
        self.added_metadata = None
        self.file_existed_during_add = False

    def add_literature_to_db(self, file_path, metadata=None):
        self.added_file_path = file_path
        self.added_metadata = metadata
        self.file_existed_during_add = os.path.exists(file_path)
        return self.chunk_num

    def get_db_stats(self):
        return self.total_chunks


class FakeCollection:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakeAddCollection:
    def __init__(self):
        self.added = None

    def add(self, ids, documents, embeddings, metadatas):
        self.added = {
            "ids": ids,
            "documents": documents,
            "embeddings": embeddings,
            "metadatas": metadatas,
        }


class FakeEmbeddingResult:
    def __init__(self, embeddings):
        self.embeddings = embeddings

    def tolist(self):
        return self.embeddings


class FakeEmbeddingModel:
    def encode(self, texts, normalize_embeddings=True):
        return FakeEmbeddingResult([[0.1, 0.2] for _ in texts])


class FakeHybridCollection:
    def __init__(self, documents):
        self.documents = documents

    def get(self):
        return {"documents": list(self.documents)}


class FakeHybridRAG:
    def __init__(self, documents):
        self.collection = FakeHybridCollection(documents)

    def retrieve(self, query, top_k=5):
        return []


class FakeHybridRetriever:
    def __init__(self, rag):
        self.rag = rag
        self.docs = rag.collection.get()["documents"]

    def retrieve(self, query, top_k=5):
        ranked = [doc for doc in self.docs if query in doc] or list(self.docs)
        return {
            "vector": [],
            "bm25": [{"text": doc, "score": 1.0} for doc in ranked[:top_k]],
        }


class RagServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_literature_returns_index_counts_after_successful_add(self):
        fake_rag = FakeRAG(chunk_num=2, total_chunks=7)
        metadata = {"title": "RAG Paper", "id": "paper-1"}

        with patch.object(rag_service, "get_rag", return_value=fake_rag):
            response = await rag_service.add_literature(FakeUploadFile(), metadata)

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["chunk_num"], 2)
        self.assertEqual(response["total_chunks"], 7)
        self.assertEqual(response["message"], "Indexed literature into 2 chunks.")
        self.assertEqual(fake_rag.added_metadata, metadata)
        self.assertTrue(fake_rag.file_existed_during_add)
        self.assertFalse(os.path.exists(fake_rag.added_file_path))

    async def test_add_literature_falls_back_to_zero_counts_when_rag_is_unavailable(self):
        dummy_rag = DummyRAG(Exception("init failed"))

        with patch.object(rag_service, "get_rag", return_value=dummy_rag):
            response = await rag_service.add_literature(FakeUploadFile(), {"title": "Fallback"})

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["chunk_num"], 0)
        self.assertEqual(response["total_chunks"], 0)

    def test_literature_rag_db_stats_returns_collection_count(self):
        fake_chromadb = types.ModuleType("chromadb")
        fake_chromadb.PersistentClient = object
        fake_chromadb_config = types.ModuleType("chromadb.config")
        fake_chromadb_config.Settings = object
        fake_sentence_transformers = types.ModuleType("sentence_transformers")
        fake_sentence_transformers.SentenceTransformer = object
        fake_grobid_client = types.ModuleType("grobid_client")
        fake_grobid_client_module = types.ModuleType("grobid_client.grobid_client")
        fake_grobid_client_module.GrobidClient = object

        with patch.dict(
            sys.modules,
            {
                "chromadb": fake_chromadb,
                "chromadb.config": fake_chromadb_config,
                "sentence_transformers": fake_sentence_transformers,
                "grobid_client": fake_grobid_client,
                "grobid_client.grobid_client": fake_grobid_client_module,
            },
        ):
            from core.rag_vector_db import LiteratureRAG

        rag = object.__new__(LiteratureRAG)
        rag.collection = FakeCollection(count=11)

        self.assertEqual(rag.get_db_stats(), 11)

    def test_literature_rag_add_sections_invalidates_hybrid_cache_after_successful_add(self):
        fake_chromadb = types.ModuleType("chromadb")
        fake_chromadb.PersistentClient = object
        fake_chromadb_config = types.ModuleType("chromadb.config")
        fake_chromadb_config.Settings = object
        fake_sentence_transformers = types.ModuleType("sentence_transformers")
        fake_sentence_transformers.SentenceTransformer = object
        fake_grobid_client = types.ModuleType("grobid_client")
        fake_grobid_client_module = types.ModuleType("grobid_client.grobid_client")
        fake_grobid_client_module.GrobidClient = object

        with patch.dict(
            sys.modules,
            {
                "chromadb": fake_chromadb,
                "chromadb.config": fake_chromadb_config,
                "sentence_transformers": fake_sentence_transformers,
                "grobid_client": fake_grobid_client,
                "grobid_client.grobid_client": fake_grobid_client_module,
            },
        ):
            rag_vector_db = importlib.import_module("core.rag_vector_db")

        rag = object.__new__(rag_vector_db.LiteratureRAG)
        rag.embedding_model = FakeEmbeddingModel()
        rag.collection = FakeAddCollection()

        with patch.object(
            rag_vector_db,
            "chunk_sections",
            return_value=[{"section": "Intro", "text": "fresh indexed chunk"}],
        ), patch.object(rag_vector_db, "invalidate_hybrid_cache") as invalidate:
            chunk_count = rag.add_sections_to_db(
                [{"section": "Intro", "content": "fresh indexed chunk"}],
                "paper.pdf",
                {"title": "Cache Paper", "id": "Paper One"},
            )

        self.assertEqual(chunk_count, 1)
        self.assertIn("fresh indexed chunk", rag.collection.added["documents"][0])
        self.assertEqual(rag.collection.added["metadatas"][0]["id"], "paper_one")
        invalidate.assert_called_once_with()

    def test_hybrid_cache_invalidation_rebuilds_bm25_from_updated_collection(self):
        original_rag = store._rag
        original_hybrid = store._hybrid
        original_hybrid_retriever = store.HybridRetriever
        try:
            fake_rag = FakeHybridRAG(["Paper: old\n\nContent:\nlegacy baseline"])
            store._rag = fake_rag
            store._hybrid = None
            store.HybridRetriever = FakeHybridRetriever

            first_hybrid = store.get_hybrid()
            first_bm25 = first_hybrid.retrieve("legacy", top_k=1)["bm25"]
            self.assertIn("legacy baseline", first_bm25[0]["text"])

            fake_rag.collection.documents = ["Paper: new\n\nContent:\nfresh chunk marker"]
            store.invalidate_hybrid_cache()

            second_hybrid = store.get_hybrid()
            second_bm25 = second_hybrid.retrieve("fresh", top_k=1)["bm25"]

            self.assertIsNot(second_hybrid, first_hybrid)
            self.assertIn("fresh chunk marker", second_bm25[0]["text"])
        finally:
            store._rag = original_rag
            store._hybrid = original_hybrid
            store.HybridRetriever = original_hybrid_retriever

    def test_hybrid_cache_invalidation_keeps_rag_instance(self):
        original_rag = store._rag
        original_hybrid = store._hybrid
        try:
            sentinel_rag = object()
            sentinel_hybrid = object()
            store._rag = sentinel_rag
            store._hybrid = sentinel_hybrid

            store.invalidate_hybrid_cache()

            self.assertIs(store._rag, sentinel_rag)
            self.assertIsNone(store._hybrid)
        finally:
            store._rag = original_rag
            store._hybrid = original_hybrid


if __name__ == "__main__":
    unittest.main()
