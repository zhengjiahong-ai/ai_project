import unittest
from unittest.mock import Mock, patch

from services import background_knowledge_service as service


class BackgroundKnowledgeProvenanceIntegrationTest(unittest.TestCase):
    @patch.object(service, "get_rag")
    def test_related_sources_are_restricted_to_current_paper(self, get_rag):
        rag = Mock()
        rag.retrieve.return_value = [{"text": "current paper", "metadata": {"id": "paper.pdf"}}]
        get_rag.return_value = rag

        result = service._retrieve_related_sources({"rewritten": "attention"}, "paper.pdf")

        rag.retrieve.assert_called_once_with("attention", top_k=5, filter_metadata={"id": "paper.pdf"})
        self.assertEqual(result[0]["text"], "current paper")

    def test_normalization_preserves_provenance_and_suppresses_implicit_edges(self):
        raw = {
            "background_knowledge": ["Attention"],
            "graph": {
                "suppressImplicitEdges": True,
                "nodes": [
                    {"id": "current-paper", "label": "Paper", "type": "paper"},
                    {
                        "id": "attention",
                        "label": "Attention",
                        "sourceIds": [],
                        "provenanceStatus": "model_inference",
                        "confidence": 0.6,
                        "confidenceReason": "模型推断。",
                    },
                ],
                "links": [],
                "edges": [],
            },
            "provenanceSummary": {
                "nodes": {"total": 1, "currentPaperSupported": 0, "modelInference": 1, "externalSupported": 0, "supportedRatio": 0.0},
                "edges": {"total": 0, "currentPaperSupported": 0, "modelInference": 0, "externalSupported": 0, "supportedRatio": 0.0},
            },
            "warnings": ["前置关系判断失败"],
            "externalKnowledge": {"enabled": False, "status": "disabled"},
        }

        result = service._normalize_payload(
            raw,
            paper_topic="Paper",
            reader_profile={"user_knowledge_level": "一般"},
            pdf_id="paper.pdf",
            rag_sources=[],
        )

        attention = next(node for node in result["graph"]["nodes"] if node["id"] == "attention")
        self.assertEqual(attention["provenanceStatus"], "model_inference")
        self.assertEqual(attention["confidenceReason"], "模型推断。")
        self.assertEqual(result["graph"]["links"], [])
        self.assertEqual(result["graph"]["edges"], [])
        self.assertEqual(result["provenanceSummary"]["nodes"]["modelInference"], 1)
        self.assertEqual(result["warnings"], ["前置关系判断失败"])
        self.assertEqual(result["externalKnowledge"]["status"], "disabled")

    def test_neo4j_write_includes_provenance_fields(self):
        tx = Mock()
        payload = {"pdfId": "paper.pdf", "paper_topic": "Paper", "user_knowledge_level": "一般"}
        graph = {
            "nodes": [
                {
                    "id": "attention",
                    "label": "Attention",
                    "type": "concept",
                    "level": "basic",
                    "summary": "",
                    "why": "",
                    "stage": "foundation",
                    "confidence": 0.6,
                    "sourceIds": [],
                    "provenanceStatus": "model_inference",
                    "confidenceReason": "模型推断。",
                }
            ],
            "links": [],
            "edges": [
                {
                    "source": "attention",
                    "target": "current-paper",
                    "type": "prerequisite",
                    "sourceIds": [],
                    "provenanceStatus": "model_inference",
                    "confidence": 0.6,
                    "confidenceReason": "模型推断。",
                }
            ],
        }

        service._write_graph_tx(tx, payload, graph)

        queries = "\n".join(call.args[0] for call in tx.run.call_args_list)
        self.assertIn("c.provenanceStatus", queries)
        self.assertIn("r.provenanceStatus", queries)


if __name__ == "__main__":
    unittest.main()
