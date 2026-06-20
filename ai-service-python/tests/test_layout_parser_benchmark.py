import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.layout_parser.metrics import (
    bbox_iou,
    score_headings,
    score_reading_order,
    score_regions,
)
from benchmarks.layout_parser.runner import (
    INFINITY_PARSER_STATUS,
    load_manifest,
    process_grobid_document,
    run_grobid_batch,
)


class LayoutParserBenchmarkMetricsTests(unittest.TestCase):
    def test_bbox_iou_handles_identical_and_disjoint_boxes(self):
        box = {"left": 0.1, "top": 0.2, "width": 0.3, "height": 0.4}

        self.assertEqual(bbox_iou(box, box), 1.0)
        self.assertEqual(
            bbox_iou(box, {"left": 0.8, "top": 0.8, "width": 0.1, "height": 0.1}),
            0.0,
        )

    def test_heading_score_normalizes_numbering_and_case(self):
        result = score_headings(
            ["1 Introduction", "METHODS", "Unexpected"],
            ["Introduction", "2. Methods", "Results"],
        )

        self.assertEqual(result["matched"], 2)
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertAlmostEqual(result["recall"], 2 / 3)
        self.assertAlmostEqual(result["f1"], 2 / 3)

    def test_reading_order_uses_pairwise_anchor_accuracy(self):
        result = score_reading_order(["a", "c", "b"], ["a", "b", "c"])

        self.assertEqual(result["comparablePairs"], 3)
        self.assertEqual(result["correctPairs"], 2)
        self.assertAlmostEqual(result["accuracy"], 2 / 3)

    def test_region_score_requires_matching_type_and_iou_threshold(self):
        gold = [
            {"pageIndex": 0, "type": "formula", "bbox": {"left": 0.1, "top": 0.1, "width": 0.2, "height": 0.2}},
            {"pageIndex": 0, "type": "table", "bbox": {"left": 0.5, "top": 0.5, "width": 0.3, "height": 0.2}},
        ]
        predicted = [
            {"pageIndex": 0, "type": "formula", "bbox": {"left": 0.1, "top": 0.1, "width": 0.2, "height": 0.2}},
            {"pageIndex": 0, "type": "figure", "bbox": {"left": 0.5, "top": 0.5, "width": 0.3, "height": 0.2}},
        ]

        result = score_regions(predicted, gold, iou_threshold=0.5)

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["falsePositives"], 1)
        self.assertEqual(result["falseNegatives"], 1)
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)


class LayoutParserBenchmarkRunnerTests(unittest.TestCase):
    def test_manifest_marks_missing_pdf_without_fabricating_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "fixtures.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1.0",
                        "documents": [
                            {
                                "id": "missing",
                                "path": "missing.pdf",
                                "sha256": "0" * 64,
                                "tags": ["two-column"],
                                "gold": {"headings": [], "readingOrder": [], "regions": []},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = load_manifest(manifest_path, workspace_root=root)

        self.assertEqual(manifest["documents"][0]["fixtureStatus"], "missing")
        self.assertIsNone(manifest["documents"][0]["actualSha256"])

    def test_grobid_failure_is_reported_as_unavailable(self):
        document = {
            "id": "paper",
            "resolvedPath": "paper.pdf",
            "fixtureStatus": "available",
            "gold": {"headings": [], "readingOrder": [], "regions": []},
        }

        def failing_processor(_document, _output_dir):
            raise ConnectionError("connection refused")

        result = run_grobid_batch([document], processor=failing_processor)

        self.assertEqual(result[0]["status"], "grobid_unavailable")
        self.assertIsNone(result[0]["metrics"])
        self.assertIn("connection refused", result[0]["error"])

    def test_infinity_parser_is_explicitly_not_runnable(self):
        self.assertEqual(INFINITY_PARSER_STATUS["status"], "not_runnable")
        self.assertEqual(INFINITY_PARSER_STATUS["paperId"], "2506.03197")
        self.assertFalse(INFINITY_PARSER_STATUS["substituted"])

    def test_grobid_processor_reuses_tei_parser_and_scores_gold(self):
        tei = """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <facsimile><surface n="1" width="100" height="100" /><surface n="2" width="100" height="100" /></facsimile>
          <text><body><div><head n="1">Introduction</head><p coords="1,10,10,80,10">Body.</p></div>
          <div><head n="2">Methods</head><formula coords="1,10,40,40,20">x = 1</formula>
          <formula coords="2,10,40,40,20">y = 2</formula></div></body></text>
        </TEI>"""

        class FakeClient:
            def process(self, _service, input_path, output, **_kwargs):
                print("⏱ benchmark complete")
                self.input_path = input_path
                Path(output, "paper.tei.xml").write_text(tei, encoding="utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir, "paper.pdf")
            pdf_path.write_bytes(b"%PDF-fake")
            document = {
                "id": "paper",
                "resolvedPath": str(pdf_path),
                "fixtureStatus": "available",
                "gold": {
                    "headings": ["Introduction", "Methods"],
                    "pages": [
                        {
                            "pageIndex": 0,
                            "regions": [
                                {"type": "formula", "bbox": {"left": 0.1, "top": 0.4, "width": 0.4, "height": 0.2}}
                            ],
                        }
                    ],
                },
            }
            output_dir = Path(temp_dir, "output")
            output_dir.mkdir()
            ascii_stdout = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
            with patch("sys.stdout", ascii_stdout):
                result = process_grobid_document(
                    document,
                    output_dir,
                    client=FakeClient(),
                    outline_builder=lambda _tei, _pdf: [
                        {"title": "Introduction"},
                        {"title": "Methods"},
                    ],
                )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["metrics"]["headings"]["f1"], 1.0)
        self.assertEqual(result["metrics"]["regions"]["f1"], 1.0)
        self.assertEqual(result["metrics"]["regions"]["predicted"], 1)
        self.assertEqual(result["regionCount"], 2)
        self.assertEqual(result["excludedZonesByPage"]["0"][0]["type"], "formula")


if __name__ == "__main__":
    unittest.main()
