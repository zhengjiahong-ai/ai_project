import os
import sys
import types
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
