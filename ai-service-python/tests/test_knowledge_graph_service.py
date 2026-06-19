import json
import unittest

from services.knowledge_graph_service import (
    DisabledExternalKnowledgeProvider,
    generate_current_paper_graph,
)


class _SequenceLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def _call(self, prompt="", messages=None, **_kwargs):
        self.prompts.append({"prompt": prompt, "messages": messages})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response, ensure_ascii=False)


class KnowledgeGraphServiceTest(unittest.TestCase):
    def test_two_stage_graph_caps_confidence_and_classifies_provenance(self):
        llm = _SequenceLlm([
            {
                "concepts": [
                    {"id": "attention", "label": "Attention", "sourceIds": ["source-1"]},
                    {"id": "linear-algebra", "label": "线性代数", "sourceIds": []},
                ]
            },
            {
                "edges": [
                    {
                        "source": "linear-algebra",
                        "target": "attention",
                        "sourceIds": [],
                        "confidence": 0.98,
                        "confidenceReason": "理解矩阵运算后才能理解注意力。",
                    },
                    {
                        "source": "attention",
                        "target": "current-paper",
                        "sourceIds": ["source-1"],
                        "confidence": 0.99,
                        "confidenceReason": "论文方法章节明确使用注意力。",
                    },
                ]
            },
        ])

        result = generate_current_paper_graph(
            paper_topic="Transformer",
            paper_context="The method uses attention.",
            paper_structure={"method": "attention"},
            rag_sources=[{"sourceId": "source-1", "text": "The method uses attention."}],
            reader_profile={"user_knowledge_level": "一般"},
            pdf_id="paper.pdf",
            llm=llm,
        )

        self.assertEqual(len(llm.prompts), 2)
        nodes = {node["id"]: node for node in result["graph"]["nodes"]}
        self.assertEqual(nodes["attention"]["provenanceStatus"], "current_paper_supported")
        self.assertEqual(nodes["attention"]["confidence"], 0.85)
        self.assertEqual(nodes["linear-algebra"]["provenanceStatus"], "model_inference")
        self.assertEqual(nodes["linear-algebra"]["confidence"], 0.6)
        edges = result["graph"]["edges"]
        self.assertEqual(edges[0]["provenanceStatus"], "model_inference")
        self.assertEqual(edges[0]["confidence"], 0.6)
        self.assertEqual(edges[1]["provenanceStatus"], "current_paper_supported")
        self.assertEqual(edges[1]["confidence"], 0.85)
        self.assertEqual(result["provenanceSummary"]["edges"]["modelInference"], 1)
        self.assertEqual(result["externalKnowledge"]["status"], "disabled")

    def test_without_pdf_id_never_marks_current_paper_support(self):
        llm = _SequenceLlm([
            {"concepts": [{"id": "rag", "label": "RAG", "sourceIds": ["source-1"]}]},
            {"edges": []},
        ])

        result = generate_current_paper_graph(
            paper_topic="RAG",
            paper_context="RAG combines retrieval and generation.",
            paper_structure={},
            rag_sources=[{"sourceId": "source-1", "text": "RAG combines retrieval and generation."}],
            reader_profile={},
            pdf_id=None,
            llm=llm,
        )

        concept = next(node for node in result["graph"]["nodes"] if node["id"] == "rag")
        self.assertEqual(concept["provenanceStatus"], "model_inference")
        self.assertEqual(concept["sourceIds"], [])

    def test_resolver_failure_preserves_nodes_without_fabricating_edges(self):
        llm = _SequenceLlm([
            {"concepts": [{"id": "statistics", "label": "统计学", "sourceIds": []}]},
            RuntimeError("resolver unavailable"),
        ])

        result = generate_current_paper_graph(
            paper_topic="实验论文",
            paper_context="",
            paper_structure={},
            rag_sources=[],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
        )

        self.assertEqual(result["graph"]["edges"], [])
        self.assertEqual(result["graph"]["links"], [])
        self.assertTrue(result["graph"]["suppressImplicitEdges"])
        self.assertIn("前置关系判断失败", result["warnings"][0])

    def test_disabled_external_provider_is_read_only_and_returns_no_results(self):
        provider = DisabledExternalKnowledgeProvider()

        self.assertFalse(provider.enabled)
        self.assertEqual(provider.search(["attention prerequisites"]), [])
        self.assertEqual(provider.status()["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
