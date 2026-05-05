import tempfile
import unittest
from pathlib import Path

from core.outline_extractor import PdfTextLine, _build_pdf_heading_candidates, build_document_outline


def _write_tei(base_path: Path, body: str) -> str:
    tei_path = base_path / "paper.tei.xml"
    tei_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI>
  <text>
    <body>
      {body}
    </body>
  </text>
</TEI>
""",
        encoding="utf-8",
    )
    return str(tei_path)


class OutlineExtractorTests(unittest.TestCase):
    def test_outline_keeps_numbers_from_head_attributes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head n="3" coords="1,72,100,180,16">Experiments</head>
                  <p coords="1,72,124,460,12">We evaluate the proposed method.</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        self.assertEqual(outline[0]["displayTitle"], "3 Experiments")
        self.assertEqual(outline[0]["rawTitle"], "Experiments")
        self.assertEqual(outline[0]["headingNumber"], "3")
        self.assertEqual(outline[0]["level"], 1)

    def test_outline_recovers_multiple_same_page_subheadings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="2,72,80,180,16">2 Methods</head>
                  <p coords="2,72,110,200,14">2.1 Problem Formulation</p>
                  <p coords="2,72,130,460,12">The task is defined as a constrained optimization problem.</p>
                  <p coords="2,72,190,220,14">2.2 Model Architecture</p>
                  <p coords="2,72,212,460,12">The architecture contains an encoder and decoder.</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]

        self.assertIn("2 Methods", titles)
        self.assertIn("2.1 Problem Formulation", titles)
        self.assertIn("2.2 Model Architecture", titles)

        problem = next(item for item in outline if item["displayTitle"] == "2.1 Problem Formulation")
        architecture = next(item for item in outline if item["displayTitle"] == "2.2 Model Architecture")

        self.assertEqual(problem["level"], 2)
        self.assertEqual(architecture["level"], 2)
        self.assertEqual(problem["parentId"], outline[0]["id"])
        self.assertEqual(architecture["parentId"], outline[0]["id"])
        self.assertEqual(problem["pageIndex"], 1)
        self.assertEqual(architecture["pageIndex"], 1)

    def test_outline_extracts_numbered_heading_from_long_paragraph_prefix(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="4,72,80,220,16">3 Challenges</head>
                  <p coords="4,72,260,460,14">3.2 PLANNING IN EXPONENTIAL SIZED ACTION SPACE The action space in multi-agent environments grows exponentially with the number of agents, rendering it immensely challenging for vanilla methods.</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("3.2 PLANNING IN EXPONENTIAL SIZED ACTION SPACE", titles)
        recovered = next(
            item for item in outline if item["displayTitle"] == "3.2 PLANNING IN EXPONENTIAL SIZED ACTION SPACE"
        )
        self.assertEqual(recovered["headingNumber"], "3.2")
        self.assertEqual(recovered["level"], 2)
        self.assertEqual(recovered["source"], "layout")

    def test_outline_infers_missing_numbered_parent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="6,72,120,260,16">4.2 Optimistic Search Lambda</head>
                  <p coords="6,72,145,460,12">This subsection defines the optimistic search lambda.</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("4 Section 4", titles)
        self.assertIn("4.2 Optimistic Search Lambda", titles)

        parent = next(item for item in outline if item["displayTitle"] == "4 Section 4")
        child = next(item for item in outline if item["displayTitle"] == "4.2 Optimistic Search Lambda")
        self.assertEqual(parent["source"], "inferred")
        self.assertEqual(child["parentId"], parent["id"])

    def test_outline_restores_ieee_alpha_subsections_and_two_column_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,303,660,180,16">II. SYSTEM MODEL</head>
                  <p coords="1,303,684,220,12">The system model starts here.</p>
                </div>
                <div>
                  <head coords="2,303,86,160,14">B. Radar Model</head>
                  <p coords="2,303,108,220,12">Radar model details.</p>
                </div>
                <div>
                  <head coords="2,303,336,180,14">C. Problem Formulation</head>
                  <p coords="2,303,358,220,12">Problem formulation details.</p>
                </div>
                <div>
                  <head coords="2,47,488,180,14">A. Communication Model</head>
                  <p coords="2,47,510,220,12">Communication model details.</p>
                </div>
                <div>
                  <head coords="2,303,656,180,16">III. PROPOSED SOLUTIONS</head>
                  <p coords="2,303,678,220,12">Solution details.</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertEqual(
            titles,
            [
                "II. SYSTEM MODEL",
                "A. Communication Model",
                "B. Radar Model",
                "C. Problem Formulation",
                "III. PROPOSED SOLUTIONS",
            ],
        )

        system_model = outline[0]
        for title in ["A. Communication Model", "B. Radar Model", "C. Problem Formulation"]:
            item = next(current for current in outline if current["displayTitle"] == title)
            self.assertEqual(item["level"], 2)
            self.assertEqual(item["parentId"], system_model["id"])

        proposed = next(item for item in outline if item["displayTitle"] == "III. PROPOSED SOLUTIONS")
        self.assertEqual(proposed["level"], 1)
        self.assertIsNone(proposed["parentId"])

    def test_outline_skips_pure_numeric_tei_heads(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="4,308,181,80,12">5</head>
                  <p coords="4,308,200,220,12">Axis tick label accidentally marked as a head.</p>
                </div>
                <div>
                  <head coords="4,115,592,180,16">IV. NUMERICAL RESULTS</head>
                  <p coords="4,115,616,220,12">Numerical results.</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertNotIn("5", titles)
        self.assertEqual(titles, ["IV. NUMERICAL RESULTS"])

    def test_pdf_line_candidates_recover_same_page_heading_not_in_tei(self):
        lines = [
            PdfTextLine(
                text="3.2 PLANNING IN EXPONENTIAL SIZED ACTION SPACE",
                page_index=3,
                x=72,
                y=260,
                width=320,
                height=15,
                font_size=11.5,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=1,
            ),
            PdfTextLine(
                text="The action space in multi-agent environments grows exponentially with the number of agents.",
                page_index=3,
                x=72,
                y=280,
                width=460,
                height=12,
                font_size=9.5,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=2,
            ),
        ]

        candidates = _build_pdf_heading_candidates(lines, 0)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].display_title, "3.2 PLANNING IN EXPONENTIAL SIZED ACTION SPACE")
        self.assertEqual(candidates[0].heading_number, "3.2")
        self.assertEqual(candidates[0].source, "pdf-layout")
        self.assertIn("pdf-line-heading", candidates[0].source_details)

    def test_pdf_line_candidates_recover_split_number_and_heading(self):
        lines = [
            PdfTextLine(
                text="3.2",
                page_index=3,
                x=72,
                y=260,
                width=24,
                height=15,
                font_size=10,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=1,
            ),
            PdfTextLine(
                text="PLANNING IN EXPONENTIAL SIZED ACTION SPACE",
                page_index=3,
                x=108,
                y=260,
                width=280,
                height=15,
                font_size=10,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=2,
            ),
            PdfTextLine(
                text="The action space in multi-agent environments grows exponentially with the number of agents.",
                page_index=3,
                x=72,
                y=282,
                width=460,
                height=12,
                font_size=9,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=3,
            ),
        ]

        candidates = _build_pdf_heading_candidates(lines, 0)

        titles = [candidate.display_title for candidate in candidates]
        self.assertIn("3.2 PLANNING IN EXPONENTIAL SIZED ACTION SPACE", titles)
        recovered = next(
            candidate for candidate in candidates
            if candidate.display_title == "3.2 PLANNING IN EXPONENTIAL SIZED ACTION SPACE"
        )
        self.assertIn("split-number-title", recovered.source_details)

    def test_pdf_line_candidates_ignore_formula_units_and_footer_noise(self):
        lines = [
            PdfTextLine(
                text="2 2",
                page_index=2,
                x=310,
                y=320,
                width=30,
                height=11,
                font_size=10,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=1,
            ),
            PdfTextLine(
                text="1 GHz",
                page_index=2,
                x=84,
                y=420,
                width=44,
                height=11,
                font_size=10,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=2,
            ),
            PdfTextLine(
                text="2022 30th European Signal Processing Conference (EUSIPCO)",
                page_index=2,
                x=72,
                y=760,
                width=360,
                height=10,
                font_size=8,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=3,
            ),
            PdfTextLine(
                text="10 11 12 13 14 15 16 17 18 19 20 System power budget (W)",
                page_index=2,
                x=96,
                y=620,
                width=360,
                height=10,
                font_size=8,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=4,
            ),
            PdfTextLine(
                text="P. total = 15W",
                page_index=3,
                x=310,
                y=300,
                width=100,
                height=11,
                font_size=9,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=5,
            ),
            PdfTextLine(
                text="F. k /followsequal 0 and rank( F k",
                page_index=3,
                x=310,
                y=330,
                width=180,
                height=11,
                font_size=9,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=6,
            ),
            PdfTextLine(
                text="M. e ] , with",
                page_index=3,
                x=310,
                y=360,
                width=100,
                height=11,
                font_size=9,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=7,
            ),
        ]

        candidates = _build_pdf_heading_candidates(lines, 0)

        self.assertEqual(candidates, [])

    def test_pdf_line_candidates_ignore_numbered_contribution_list_items(self):
        lines = [
            PdfTextLine(
                text="1 Inspired by the Centralized Training with Decentralized Execution paradigm, we design a planner.",
                page_index=1,
                x=72,
                y=260,
                width=460,
                height=12,
                font_size=9.5,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=1,
            ),
            PdfTextLine(
                text="4 We conduct extensive experiments to evaluate our method across multiple environments.",
                page_index=1,
                x=72,
                y=290,
                width=460,
                height=12,
                font_size=9.5,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=2,
            ),
            PdfTextLine(
                text="4 MAZ ERO ALGORITHM",
                page_index=4,
                x=72,
                y=120,
                width=180,
                height=13,
                font_size=10.5,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=3,
            ),
        ]

        candidates = _build_pdf_heading_candidates(lines, 0)
        titles = [candidate.display_title for candidate in candidates]

        self.assertNotIn("1 Inspired by the Centralized Training with Decentralized Execution paradigm, we design a planner.", titles)
        self.assertNotIn("4 We conduct extensive experiments to evaluate our method across multiple environments.", titles)
        self.assertIn("4 MAZ ERO ALGORITHM", titles)


if __name__ == "__main__":
    unittest.main()
