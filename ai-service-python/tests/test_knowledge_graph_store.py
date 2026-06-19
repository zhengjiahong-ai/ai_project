import os
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from services.knowledge_graph_store import enrich_conflicts_with_graph_context, read_graph_neighborhood, save_graph_snapshot


class KnowledgeGraphStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = os.environ.get("KNOWLEDGE_GRAPH_DB_PATH")
        os.environ["KNOWLEDGE_GRAPH_DB_PATH"] = str(Path(self.temp_dir.name) / "knowledge.sqlite3")

    def tearDown(self):
        if self.previous_path is None:
            os.environ.pop("KNOWLEDGE_GRAPH_DB_PATH", None)
        else:
            os.environ["KNOWLEDGE_GRAPH_DB_PATH"] = self.previous_path
        self.temp_dir.cleanup()

    def _payload(self, *, label="Accuracy", extra_nodes=0):
        nodes = [
            {
                "id": "accuracy",
                "label": label,
                "summary": "Evaluation metric for model quality.",
                "sourceIds": ["source-accuracy"],
                "provenanceStatus": "current_paper_supported",
                "confidence": 0.85,
                "confidenceReason": "The paper reports this metric.",
            },
            {
                "id": "evaluation",
                "label": "Evaluation",
                "summary": "Experimental evaluation context.",
                "sourceIds": [],
                "provenanceStatus": "model_inference",
                "confidence": 0.6,
                "confidenceReason": "Inferred prerequisite context.",
            },
        ]
        edges = [
            {
                "source": "evaluation",
                "target": "accuracy",
                "type": "prerequisite",
                "sourceIds": ["source-accuracy"],
                "provenanceStatus": "current_paper_supported",
                "confidence": 0.85,
                "confidenceReason": "The paper links evaluation and accuracy.",
            }
        ]
        for index in range(extra_nodes):
            node_id = f"neighbor-{index}"
            nodes.append({"id": node_id, "label": f"Neighbor {index}", "sourceIds": []})
            edges.append({"source": "accuracy", "target": node_id, "type": "related"})
        return {
            "pdfId": "paper-a",
            "paper_topic": "Model Evaluation",
            "graph": {"nodes": nodes, "edges": edges, "links": []},
        }

    def test_snapshot_is_overwritten_by_pdf_id(self):
        save_graph_snapshot(self._payload(label="Old Accuracy"))
        save_graph_snapshot(self._payload(label="Updated Accuracy"))

        result = read_graph_neighborhood({"paperIds": ["paper-a"], "seedTerms": ["updated accuracy"]})

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["paperIds"], ["paper-a"])
        self.assertEqual(result["nodes"][0]["label"], "Updated Accuracy")

    def test_reads_one_hop_by_source_id_and_enforces_limits(self):
        save_graph_snapshot(self._payload(extra_nodes=12))

        result = read_graph_neighborhood({
            "paperIds": [],
            "sourceIds": ["source-accuracy"],
            "seedTerms": [],
            "maxNodes": 8,
            "maxEdges": 12,
        })

        self.assertEqual(result["status"], "available")
        self.assertIn("paper-a", result["paperIds"])
        self.assertLessEqual(len(result["nodes"]), 8)
        self.assertLessEqual(len(result["edges"]), 12)
        self.assertIn("source-accuracy", result["sourceIds"])
        self.assertEqual(result["provenanceSummary"]["nodes"]["currentPaperSupported"], 1)

    def test_returns_unavailable_without_matching_snapshot(self):
        result = read_graph_neighborhood({"paperIds": ["missing-paper"], "seedTerms": ["accuracy"]})

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["edges"], [])
        self.assertIn("不代表自动裁决", result["contextNote"])

    def test_enriches_real_conflicts_but_skips_no_conflict_marker(self):
        graph_context = read_graph_neighborhood({"paperIds": ["missing-paper"], "seedTerms": ["accuracy"]})
        conflicts = [
            {
                "id": "conflict-1",
                "topic": "accuracy",
                "claim": "accuracy differs",
                "papers": ["paper-a"],
                "sourceIds": ["source-accuracy"],
            },
            {"id": "no-major-conflict", "claim": "No major conflict."},
        ]

        with patch("services.knowledge_graph_store.read_graph_neighborhood", return_value=graph_context) as reader:
            result = enrich_conflicts_with_graph_context(conflicts)

        self.assertEqual(result[0]["graphContext"], graph_context)
        self.assertNotIn("graphContext", result[1])
        reader.assert_called_once()


if __name__ == "__main__":
    unittest.main()
