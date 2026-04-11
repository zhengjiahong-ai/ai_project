import os
import unittest
from unittest.mock import patch

from schemas.requests import BackgroundKnowledgeRequest
from services.background_knowledge_service import get_background_knowledge


class FakeRag:
    @staticmethod
    def normalize_id(pdf_id):
        return str(pdf_id).lower()

    def get_documents_by_metadata(self, filter_metadata=None, limit=40):
        return [
            {
                "text": "Paper: test\nSection: abstract\nContent: Retrieval augmented generation with a graph.",
                "metadata": {"id": "paper-1", "chunk_index": 0},
            }
        ]

    def retrieve(self, query, top_k=5, filter_metadata=None):
        return [{"text": "Filtered current paper source.", "metadata": {"id": "paper-1"}}]


class BackgroundKnowledgeServiceTests(unittest.TestCase):
    def setUp(self):
        self.neo4j_env = {
            "NEO4J_URI": "",
            "NEO4J_USER": "",
            "NEO4J_PASSWORD": "",
        }

    def test_legacy_topic_payload_returns_graph_and_list(self):
        with (
            patch.dict(os.environ, self.neo4j_env, clear=False),
            patch("services.background_knowledge_service.retrieve_hybrid_for_vector", return_value=[]),
            patch("services.background_knowledge_service.get_llm") as mocked_llm,
        ):
            mocked_llm.return_value._call.return_value = "RAG\nKnowledge graph\nPrerequisites"

            response = get_background_knowledge(BackgroundKnowledgeRequest(
                paper_topic="AcademicRAG",
                user_knowledge_level="beginner",
            ))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["paper_topic"], "AcademicRAG")
        self.assertEqual(response["background_knowledge"][0], "RAG")
        self.assertGreaterEqual(len(response["graph"]["nodes"]), 2)
        self.assertEqual(response["neo4j"]["status"], "skipped")

    def test_pdf_payload_uses_rag_and_structured_llm_json(self):
        llm_json = """
        {
          "paper_topic": "AcademicRAG",
          "background_knowledge": ["RAG", "Knowledge graph"],
          "learning_path": [{"step": 1, "title": "RAG", "goal": "Understand retrieval", "conceptIds": ["rag"]}],
          "graph": {
            "nodes": [
              {"id": "current-paper", "label": "AcademicRAG", "type": "paper", "level": "target", "summary": "", "why": "", "sourceIds": []},
              {"id": "rag", "label": "RAG", "type": "concept", "level": "basic", "summary": "Retrieval augmented generation", "why": "Core method", "sourceIds": ["source-1"]}
            ],
            "links": [{"source": "rag", "target": "current-paper", "relation": "prerequisite", "label": "prerequisite"}]
          }
        }
        """

        with (
            patch.dict(os.environ, self.neo4j_env, clear=False),
            patch("services.background_knowledge_service.get_rag", return_value=FakeRag()),
            patch(
                "services.background_knowledge_service.retrieve_hybrid_for_vector",
                return_value=[{"text": "Related literature source.", "metadata": {"title": "source"}}],
            ),
            patch("services.background_knowledge_service.get_llm") as mocked_llm,
        ):
            mocked_llm.return_value._call.return_value = llm_json

            response = get_background_knowledge(BackgroundKnowledgeRequest(
                pdfId="paper-1",
                paperSkeleton={"abstract": "AcademicRAG combines KG and RAG."},
                paperStructure={"research_problem": "AcademicRAG"},
            ))

        self.assertEqual(response["pdfId"], "paper-1")
        self.assertEqual(response["graph"]["nodes"][1]["id"], "rag")
        self.assertEqual(response["learning_path"][0]["title"], "RAG")
        self.assertEqual(response["rag_sources"][0]["id"], "source-1")
        self.assertEqual(response["neo4j"]["enabled"], False)

    def test_unstructured_llm_response_falls_back_to_linear_graph(self):
        with (
            patch.dict(os.environ, self.neo4j_env, clear=False),
            patch("services.background_knowledge_service.retrieve_hybrid_for_vector", return_value=[]),
            patch("services.background_knowledge_service.get_llm") as mocked_llm,
        ):
            mocked_llm.return_value._call.return_value = "1. Embeddings\n2. Vector search"

            response = get_background_knowledge(BackgroundKnowledgeRequest(paper_topic="RAG"))

        self.assertEqual(response["background_knowledge"], ["Embeddings", "Vector search"])
        self.assertTrue(any(link["target"] == "current-paper" for link in response["graph"]["links"]))


if __name__ == "__main__":
    unittest.main()
