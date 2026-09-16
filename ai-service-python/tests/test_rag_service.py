import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch

from rag import store
from rag.store import DummyRAG
from core.smart_chunker import chunk_sections
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
        self.deleted = []

    def get(self, where, include):
        return {"ids": ["previous-version"]}

    def delete(self, ids):
        assert self.added is not None
        self.deleted = ids

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

    def retrieve(self, query, top_k=5, filter_metadata=None):
        return []


class FakeHybridRetriever:
    def __init__(self, rag):
        self.rag = rag
        self.docs = rag.collection.get()["documents"]

    def retrieve(self, query, top_k=5, filter_metadata=None):
        ranked = [doc for doc in self.docs if query in doc] or list(self.docs)
        bm25 = [{"text": doc, "score": 1.0} for doc in ranked[:top_k]]
        return {
            "vector": [],
            "bm25": bm25,
            # 真实实现会同时返回 fused（向量主导 + BM25 补召回）；
            # fake 缺这个键会让走 rag_service.retrieve 的测试静默降级到 except 分支。
            "fused": list(bm25),
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
        self.assertEqual(rag.collection.deleted, ["previous-version"])
        self.assertEqual(rag.collection.added["metadatas"][0]["id"], "paper_one")
        invalidate.assert_called_once_with()

    def test_chunk_sections_preserves_section_location_metadata(self):
        chunks = chunk_sections(
            [
                {
                    "id": "section-2",
                    "section": "Methods",
                    "content": "short method text",
                    "pageIndex": 3,
                    "page": 4,
                }
            ]
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["section"], "Methods")
        self.assertEqual(chunks[0]["sectionId"], "section-2")
        self.assertEqual(chunks[0]["sectionTitle"], "Methods")
        self.assertEqual(chunks[0]["pageIndex"], 3)
        self.assertEqual(chunks[0]["page"], 4)

    def test_literature_rag_add_sections_writes_chunk_location_metadata(self):
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

        with patch.object(rag_vector_db, "invalidate_hybrid_cache"):
            chunk_count = rag.add_sections_to_db(
                [
                    {
                        "id": "section-2",
                        "section": "Methods",
                        "content": "method evidence",
                        "pageIndex": 3,
                        "page": 4,
                    }
                ],
                "paper.pdf",
                {"title": "Location Paper", "id": "Paper Two"},
            )

        metadata = rag.collection.added["metadatas"][0]
        self.assertEqual(chunk_count, 1)
        self.assertEqual(metadata["id"], "paper_two")
        self.assertEqual(metadata["chunk_index"], 0)
        self.assertEqual(metadata["section_id"], "section-2")
        self.assertEqual(metadata["section_title"], "Methods")
        self.assertEqual(metadata["page_index"], 3)
        self.assertEqual(metadata["page"], 4)

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


class RagRouteFilterParamTests(unittest.TestCase):
    """/rag/retrieve 与 /rag/add-literature 的对象参数必须真的能传到后端。

    回归背景：两个路由原本都声明 `xxx: dict | None = None`，而 FastAPI 无法把 dict
    当查询参数 —— 它会把该参数从 OpenAPI 里整个丢掉，并且无论客户端传什么都恒传
    None。实测传一个根本不存在的 pdf id，返回结果与完全不传过滤条件一模一样
    （7 条 vs 7 条），“只在这篇论文里检索”被静默跳过，解析失败也不报错，
    调用方无从察觉。改成 JSON 字符串 + 解析失败显式 400 后，bogus id 返回 0 条。
    """

    def test_parse_json_object_accepts_object_and_rejects_others(self):
        from routes.rag_routes import _parse_json_object

        self.assertIsNone(_parse_json_object(None, "filter_metadata"))
        self.assertIsNone(_parse_json_object("", "filter_metadata"))
        self.assertEqual(
            _parse_json_object('{"id": "paper-1"}', "filter_metadata"),
            {"id": "paper-1"},
        )
        # 空对象等价于“不过滤”；把空的 where 传下去会把检索限成 0 条
        self.assertIsNone(_parse_json_object("{}", "filter_metadata"))

        for bad in ("not json", "[1, 2]", '"scalar"', "42"):
            with self.assertRaises(ValueError):
                _parse_json_object(bad, "filter_metadata")

    def test_route_params_are_not_declared_as_dict(self):
        """FastAPI 会静默丢弃 dict 类型的查询参数，注解里不得再出现 dict。"""
        import inspect

        from routes import rag_routes

        for handler in (rag_routes.rag_retrieve, rag_routes.rag_add_literature):
            for name, param in inspect.signature(handler).parameters.items():
                annotation = param.annotation
                if annotation is inspect.Parameter.empty:
                    continue
                self.assertNotIn(
                    "dict",
                    str(annotation),
                    f"{handler.__name__}({name}) 声明为 {annotation}：FastAPI 无法把 dict "
                    "当查询参数，会把它从 OpenAPI 删掉并恒传 None，过滤静默失效",
                )


if __name__ == "__main__":
    unittest.main()
