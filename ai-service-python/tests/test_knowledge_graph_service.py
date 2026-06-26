import json
import os
import unittest
from unittest.mock import patch

from services.knowledge_graph_service import (
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


class _InjectedProvider:
    name = "crossref"
    enabled = True

    def search(self, query, limit=5):
        return []

    def status(self):
        return {"enabled": True, "status": "ready", "provider": self.name}


class _ExternalResultProvider:
    name = "crossref"
    enabled = True

    def __init__(self, results=None, match_query=None):
        self._results = results or []
        self._match_query = match_query

    def search(self, query, limit=5):
        if self._match_query is not None and self._match_query not in (query or ""):
            return []
        return self._results

    def status(self):
        return {"enabled": True, "status": "ready", "provider": self.name}


class _FailingProvider:
    name = "crossref"
    enabled = True

    def search(self, query, limit=5):
        raise RuntimeError("provider unavailable")

    def status(self):
        return {"enabled": True, "status": "error", "provider": self.name}


class _DisabledProvider:
    name = "disabled"
    enabled = False

    def search(self, query, limit=5):
        return []

    def status(self):
        return {"enabled": False, "status": "disabled"}


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

    def test_explicit_provider_injection_preserves_provider_status(self):
        provider = _InjectedProvider()
        llm = _SequenceLlm([{"concepts": []}])

        result = generate_current_paper_graph(
            paper_topic="RAG",
            paper_context="",
            paper_structure={},
            rag_sources=[],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        self.assertEqual(result["externalKnowledge"], {
            "enabled": True,
            "status": "ready",
            "provider": "crossref",
        })

    def test_default_provider_factory_exposes_registered_crossref_status(self):
        llm = _SequenceLlm([{"concepts": []}])

        with patch.dict(os.environ, {
            "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
            "PIXIU_EXTERNAL_SEARCH_PROVIDER": "crossref",
        }, clear=True):
            result = generate_current_paper_graph(
                paper_topic="RAG",
                paper_context="",
                paper_structure={},
                rag_sources=[],
                reader_profile={},
                pdf_id="paper.pdf",
                llm=llm,
            )

        self.assertEqual(result["externalKnowledge"], {
            "enabled": True,
            "status": "ready",
            "provider": "crossref",
        })

    def test_external_enrichment_upgrades_model_inference_concepts(self):
        provider = _ExternalResultProvider(results=[
            {
                "provider": "crossref",
                "providerId": "cr-1",
                "title": "Linear Algebra Foundations",
                "authors": ["Smith J"],
                "year": 2023,
                "doi": "10.1234/la",
                "url": "https://example.org/la",
                "abstract": "Foundational concepts in linear algebra.",
            },
        ])
        llm = _SequenceLlm([
            {
                "concepts": [
                    {"id": "attention", "label": "Attention", "sourceIds": ["source-1"]},
                    {"id": "linear-algebra", "label": "线性代数", "sourceIds": []},
                ]
            },
            {"edges": []},
        ])

        result = generate_current_paper_graph(
            paper_topic="Transformer",
            paper_context="",
            paper_structure={},
            rag_sources=[{"sourceId": "source-1", "text": "attention mechanism"}],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        nodes = {node["id"]: node for node in result["graph"]["nodes"]}
        self.assertEqual(nodes["attention"]["provenanceStatus"], "current_paper_supported")
        self.assertEqual(nodes["attention"]["confidence"], 0.85)
        self.assertEqual(nodes["linear-algebra"]["provenanceStatus"], "external_supported")
        self.assertEqual(nodes["linear-algebra"]["confidence"], 0.95)
        self.assertIn("crossref", nodes["linear-algebra"]["confidenceReason"])
        self.assertTrue(any(sid.startswith("external-") for sid in nodes["linear-algebra"]["sourceIds"]))

    def test_external_enrichment_skips_paper_supported_concepts(self):
        provider = _ExternalResultProvider(results=[
            {"provider": "crossref", "providerId": "cr-1", "title": "Attention Mechanisms", "doi": "10.1234/attn"},
        ])
        llm = _SequenceLlm([
            {"concepts": [{"id": "attention", "label": "Attention", "sourceIds": ["source-1"]}]},
            {"edges": []},
        ])

        result = generate_current_paper_graph(
            paper_topic="Transformer",
            paper_context="",
            paper_structure={},
            rag_sources=[{"sourceId": "source-1", "text": "attention"}],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        concept = next(node for node in result["graph"]["nodes"] if node["id"] == "attention")
        self.assertEqual(concept["provenanceStatus"], "current_paper_supported")
        self.assertEqual(concept["confidence"], 0.85)
        self.assertFalse(any(sid.startswith("external-") for sid in concept["sourceIds"]))

    def test_external_enrichment_graceful_on_provider_failure(self):
        provider = _FailingProvider()
        llm = _SequenceLlm([
            {"concepts": [{"id": "stats", "label": "统计学", "sourceIds": []}]},
            {"edges": []},
        ])

        result = generate_current_paper_graph(
            paper_topic="实验论文",
            paper_context="",
            paper_structure={},
            rag_sources=[],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        concept = next(node for node in result["graph"]["nodes"] if node["id"] == "stats")
        self.assertEqual(concept["provenanceStatus"], "model_inference")
        self.assertEqual(concept["confidence"], 0.6)

    def test_external_enrichment_graceful_on_disabled_provider(self):
        provider = _DisabledProvider()
        llm = _SequenceLlm([
            {"concepts": [{"id": "stats", "label": "统计学", "sourceIds": []}]},
            {"edges": []},
        ])

        result = generate_current_paper_graph(
            paper_topic="实验论文",
            paper_context="",
            paper_structure={},
            rag_sources=[],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        concept = next(node for node in result["graph"]["nodes"] if node["id"] == "stats")
        self.assertEqual(concept["provenanceStatus"], "model_inference")
        self.assertEqual(result["externalKnowledge"]["status"], "disabled")

    def test_edge_enrichment_upgrades_when_both_nodes_supported(self):
        provider = _ExternalResultProvider(results=[
            {"provider": "crossref", "providerId": "cr-1", "title": "Linear Algebra", "doi": "10.1234/la"},
        ])
        llm = _SequenceLlm([
            {
                "concepts": [
                    {"id": "attention", "label": "Attention", "sourceIds": ["source-1"]},
                    {"id": "linear-algebra", "label": "线性代数", "sourceIds": []},
                ]
            },
            {
                "edges": [
                    {"source": "linear-algebra", "target": "attention", "sourceIds": [], "confidence": 0.7},
                ]
            },
        ])

        result = generate_current_paper_graph(
            paper_topic="Transformer",
            paper_context="",
            paper_structure={},
            rag_sources=[{"sourceId": "source-1", "text": "attention"}],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        edges = result["graph"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["provenanceStatus"], "external_supported")
        self.assertEqual(edges[0]["confidence"], 0.95)

    def test_edge_not_upgraded_when_one_node_unsupported(self):
        provider = _ExternalResultProvider(
            results=[{"provider": "crossref", "providerId": "cr-1", "title": "Linear Algebra", "doi": "10.1234/la"}],
            match_query="线性代数",
        )
        llm = _SequenceLlm([
            {
                "concepts": [
                    {"id": "attention", "label": "Attention", "sourceIds": []},
                    {"id": "linear-algebra", "label": "线性代数", "sourceIds": []},
                ]
            },
            {
                "edges": [
                    {"source": "linear-algebra", "target": "attention", "sourceIds": [], "confidence": 0.7},
                ]
            },
        ])

        result = generate_current_paper_graph(
            paper_topic="Transformer",
            paper_context="",
            paper_structure={},
            rag_sources=[],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        nodes = {node["id"]: node for node in result["graph"]["nodes"]}
        self.assertEqual(nodes["linear-algebra"]["provenanceStatus"], "external_supported")
        self.assertEqual(nodes["attention"]["provenanceStatus"], "model_inference")
        edges = result["graph"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["provenanceStatus"], "model_inference")

    def test_provenance_summary_includes_external_counts(self):
        provider = _ExternalResultProvider(results=[
            {"provider": "crossref", "providerId": "cr-1", "title": "Linear Algebra", "doi": "10.1234/la"},
        ])
        llm = _SequenceLlm([
            {
                "concepts": [
                    {"id": "attention", "label": "Attention", "sourceIds": ["source-1"]},
                    {"id": "linear-algebra", "label": "线性代数", "sourceIds": []},
                ]
            },
            {
                "edges": [
                    {"source": "linear-algebra", "target": "attention", "sourceIds": [], "confidence": 0.7},
                ]
            },
        ])

        result = generate_current_paper_graph(
            paper_topic="Transformer",
            paper_context="",
            paper_structure={},
            rag_sources=[{"sourceId": "source-1", "text": "attention"}],
            reader_profile={},
            pdf_id="paper.pdf",
            llm=llm,
            external_provider=provider,
        )

        summary = result["provenanceSummary"]
        self.assertEqual(summary["nodes"]["externalSupported"], 1)
        self.assertEqual(summary["nodes"]["currentPaperSupported"], 1)
        self.assertEqual(summary["nodes"]["modelInference"], 0)
        self.assertEqual(summary["nodes"]["supportedRatio"], 1.0)
        self.assertEqual(summary["edges"]["externalSupported"], 1)


if __name__ == "__main__":
    unittest.main()
