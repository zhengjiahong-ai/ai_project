import tempfile
import unittest
from pathlib import Path

from core.outline_extractor import (
    PdfTextLine,
    _build_pdf_heading_candidates,
    _chinese_digit_to_arabic,
    _extract_standalone_heading_number,
    build_document_outline,
)


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

    def test_pdf_line_candidates_keep_complex_two_column_subheading_order(self):
        lines = [
            PdfTextLine(
                text="II. SYSTEM MODEL",
                page_index=1,
                x=303,
                y=86,
                width=160,
                height=14,
                font_size=11,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=1,
            ),
            PdfTextLine(
                text="B. Radar Model",
                page_index=1,
                x=303,
                y=118,
                width=130,
                height=12,
                font_size=10,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=2,
            ),
            PdfTextLine(
                text="The radar echo is processed by the receiver.",
                page_index=1,
                x=303,
                y=138,
                width=220,
                height=10,
                font_size=9,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=3,
            ),
            PdfTextLine(
                text="A. Communication Model",
                page_index=1,
                x=47,
                y=488,
                width=165,
                height=12,
                font_size=10,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=4,
            ),
            PdfTextLine(
                text="The communication channel is modeled here.",
                page_index=1,
                x=47,
                y=508,
                width=220,
                height=10,
                font_size=9,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=5,
            ),
            PdfTextLine(
                text="III. PROPOSED SOLUTIONS",
                page_index=1,
                x=303,
                y=656,
                width=180,
                height=14,
                font_size=11,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=6,
            ),
        ]

        candidates = _build_pdf_heading_candidates(lines, 0)
        titles = [candidate.display_title for candidate in candidates]

        self.assertIn("II. SYSTEM MODEL", titles)
        self.assertIn("A. Communication Model", titles)
        self.assertIn("B. Radar Model", titles)
        self.assertIn("III. PROPOSED SOLUTIONS", titles)
        self.assertLess(titles.index("A. Communication Model"), titles.index("B. Radar Model"))

    def test_pdf_line_candidates_ignore_complex_layout_noise_and_body_sentences(self):
        lines = [
            PdfTextLine(
                text="Algorithm 1 Proposed AO Algorithm to Solve Problem (P0). Inputs: G, gk, PBS.",
                page_index=2,
                x=303,
                y=92,
                width=220,
                height=10,
                font_size=8,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=1,
            ),
            PdfTextLine(
                text="1: Initialize w, fk, fr and Phi in a feasible region.",
                page_index=2,
                x=303,
                y=112,
                width=220,
                height=10,
                font_size=8,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=2,
            ),
            PdfTextLine(
                text="SINRc,k >= gamma th,k, for all k",
                page_index=2,
                x=330,
                y=340,
                width=150,
                height=10,
                font_size=8,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=3,
            ),
            PdfTextLine(
                text="f | 1GHz",
                page_index=2,
                x=500,
                y=420,
                width=40,
                height=10,
                font_size=8,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=4,
            ),
            PdfTextLine(
                text="The retained body paragraph explains why the algorithm converges.",
                page_index=2,
                x=47,
                y=520,
                width=260,
                height=10,
                font_size=9,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=5,
            ),
            PdfTextLine(
                text="IV. NUMERICAL RESULTS",
                page_index=2,
                x=47,
                y=580,
                width=180,
                height=13,
                font_size=11,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=6,
            ),
        ]

        candidates = _build_pdf_heading_candidates(lines, 0)
        titles = [candidate.display_title for candidate in candidates]

        self.assertEqual(titles, ["IV. NUMERICAL RESULTS"])

    # ── Chinese heading tests ─────────────────────────────────────────────

    def test_outline_detects_chinese_chapter_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,100,180,16">第一章 研究背景与意义</head>
                  <p coords="1,72,124,460,12">本章介绍研究背景。</p>
                </div>
                <div>
                  <head coords="2,72,100,180,16">第2节 系统模型设计</head>
                  <p coords="2,72,124,460,12">系统模型详细说明。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        # Chapter prefix ("第X章") is structural metadata; the title is the meaningful part
        self.assertIn("研究背景与意义", titles)
        self.assertIn("系统模型设计", titles)
        self.assertTrue(
            any("研究背景与意义" in item["rawTitle"] for item in outline)
        )
        self.assertTrue(
            any("系统模型设计" in item["rawTitle"] for item in outline)
        )

    def test_outline_detects_chinese_digit_numbered_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,100,180,16">一、引言</head>
                  <p coords="1,72,124,460,12">本文研究自然语言处理领域。</p>
                </div>
                <div>
                  <head coords="2,72,100,180,16">二、相关工作</head>
                  <p coords="2,72,124,460,12">相关工作介绍。</p>
                </div>
                <div>
                  <head coords="3,72,100,180,16">三、研究方法</head>
                  <p coords="3,72,124,460,12">研究方法详细描述。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("1 引言", titles)
        self.assertIn("2 相关工作", titles)
        self.assertIn("3 研究方法", titles)

        intro = next(item for item in outline if item["rawTitle"] == "引言")
        self.assertEqual(intro["headingNumber"], "1")

    def test_outline_detects_mixed_cn_en_numbered_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,100,180,16">1.1 研究背景</head>
                  <p coords="1,72,124,460,12">研究背景详细描述。</p>
                </div>
                <div>
                  <head coords="2,72,100,180,16">2.1 系统模型</head>
                  <p coords="2,72,124,460,12">系统模型说明。</p>
                </div>
                <div>
                  <head coords="3,72,100,180,16">3.2 实验结果与讨论</head>
                  <p coords="3,72,124,460,12">实验结果分析。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("1.1 研究背景", titles)
        self.assertIn("2.1 系统模型", titles)
        self.assertIn("3.2 实验结果与讨论", titles)

        bg = next(item for item in outline if item["rawTitle"] == "研究背景")
        self.assertEqual(bg["headingNumber"], "1.1")
        self.assertEqual(bg["source"], "tei")

    def test_outline_detects_common_chinese_unnumbered_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,100,180,16">摘要</head>
                  <p coords="1,72,124,460,12">本文提出了一种新的方法。</p>
                </div>
                <div>
                  <head coords="2,72,100,180,16">结论</head>
                  <p coords="2,72,124,460,12">本文总结了研究成果。</p>
                </div>
                <div>
                  <head coords="3,72,100,180,16">致谢</head>
                  <p coords="3,72,124,460,12">感谢资助机构。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("摘要", titles)
        self.assertIn("结论", titles)
        self.assertIn("致谢", titles)

        abstract = next(item for item in outline if item["rawTitle"] == "摘要")
        self.assertEqual(abstract["headingNumber"], "")

    def test_outline_paragraph_level_chinese_heading(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,80,180,16">3 方法</head>
                  <p coords="1,72,110,200,14">3.1 数据预处理</p>
                  <p coords="1,72,130,460,12">数据预处理包括清洗和标准化两个步骤。</p>
                  <p coords="1,72,190,220,14">3.2 模型训练</p>
                  <p coords="1,72,212,460,12">模型训练使用Adam优化器。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("3 方法", titles)
        self.assertIn("3.1 数据预处理", titles)
        self.assertIn("3.2 模型训练", titles)

    def test_outline_preserves_english_regression_after_cn_changes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,80,180,16">1 Introduction</head>
                  <p coords="1,72,100,220,12">This paper addresses the problem.</p>
                </div>
                <div>
                  <head coords="2,72,80,180,16">2 Related Work</head>
                  <p coords="2,72,100,220,12">Prior work has shown.</p>
                </div>
                <div>
                  <head coords="3,72,80,180,16">3.1 Model Architecture</head>
                  <p coords="3,72,100,220,12">The model consists of.</p>
                </div>
                <div>
                  <head coords="4,72,80,180,16">IV. EXPERIMENTS</head>
                  <p coords="4,72,100,220,12">We conduct experiments.</p>
                </div>
                <div>
                  <head coords="5,72,80,180,16">A. Ablation Study</head>
                  <p coords="5,72,100,220,12">Ablation results.</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("1 Introduction", titles)
        self.assertIn("2 Related Work", titles)
        self.assertIn("3.1 Model Architecture", titles)
        self.assertIn("IV. EXPERIMENTS", titles)
        self.assertIn("A. Ablation Study", titles)

    # ── Extended Chinese heading tests (13-3) ───────────────────────────────

    def test_chinese_digit_to_arabic_extended_range(self):
        cases = [
            ("一", "1"), ("五", "5"), ("十", "10"),
            ("十一", "11"), ("十五", "15"), ("十九", "19"),
            ("二十", "20"), ("二十一", "21"), ("二十五", "25"),
            ("三十", "30"), ("三十五", "35"),
            ("四十五", "45"), ("九十九", "99"),
            ("一百", "100"), ("一百零五", "105"),
            ("一百二十", "120"), ("一百二十三", "123"),
            ("二百", "200"), ("九百九十九", "999"),
        ]
        for cn, expected in cases:
            with self.subTest(cn=cn):
                self.assertEqual(_chinese_digit_to_arabic(cn), expected)

    def test_chinese_digit_to_arabic_unknown_returns_text(self):
        self.assertEqual(_chinese_digit_to_arabic(""), "")
        self.assertEqual(_chinese_digit_to_arabic("hello"), "hello")

    def test_extract_standalone_heading_number_chinese(self):
        self.assertEqual(_extract_standalone_heading_number("一、"), "1")
        self.assertEqual(_extract_standalone_heading_number("三、"), "3")
        self.assertEqual(_extract_standalone_heading_number("十、"), "10")
        self.assertEqual(_extract_standalone_heading_number("十五"), "15")
        self.assertEqual(_extract_standalone_heading_number("（一）"), "1")
        self.assertEqual(_extract_standalone_heading_number("(二)"), "2")
        self.assertEqual(_extract_standalone_heading_number("（3）"), "3")

    def test_extract_standalone_heading_number_english_unchanged(self):
        self.assertEqual(_extract_standalone_heading_number("1.1"), "1.1")
        self.assertEqual(_extract_standalone_heading_number("2.3.1"), "2.3.1")
        self.assertEqual(_extract_standalone_heading_number("42"), "")

    def test_outline_detects_chinese_paren_numbered_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,100,180,16">（一）研究动机</head>
                  <p coords="1,72,124,460,12">研究动机部分描述。</p>
                </div>
                <div>
                  <head coords="2,72,100,180,16">（二）创新点</head>
                  <p coords="2,72,124,460,12">创新点详细说明。</p>
                </div>
                <div>
                  <head coords="3,72,100,180,16">(三) 系统架构</head>
                  <p coords="3,72,124,460,12">系统架构描述。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("1 研究动机", titles)
        self.assertIn("2 创新点", titles)
        self.assertIn("3 系统架构", titles)

        item = next(item for item in outline if item["rawTitle"] == "研究动机")
        self.assertEqual(item["headingNumber"], "1")

    def test_outline_detects_new_chinese_unnumbered_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,100,180,16">研究动机</head>
                  <p coords="1,72,124,460,12">研究动机。</p>
                </div>
                <div>
                  <head coords="2,72,100,180,16">理论分析</head>
                  <p coords="2,72,124,460,12">理论分析。</p>
                </div>
                <div>
                  <head coords="3,72,100,180,16">敏感性分析</head>
                  <p coords="3,72,124,460,12">敏感性分析。</p>
                </div>
                <div>
                  <head coords="4,72,100,180,16">系统实现</head>
                  <p coords="4,72,124,460,12">系统实现。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("研究动机", titles)
        self.assertIn("理论分析", titles)
        self.assertIn("敏感性分析", titles)
        self.assertIn("系统实现", titles)

    def test_outline_chinese_section_with_digit_conversion(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tei_path = _write_tei(
                Path(tmp_dir),
                """
                <div>
                  <head coords="1,72,100,180,16">十二、实验结果与讨论</head>
                  <p coords="1,72,124,460,12">实验结果分析。</p>
                </div>
                <div>
                  <head coords="2,72,100,180,16">二十五、结论与展望</head>
                  <p coords="2,72,124,460,12">结论。</p>
                </div>
                """,
            )

            outline = build_document_outline(tei_path)

        titles = [item["displayTitle"] for item in outline]
        self.assertIn("12 实验结果与讨论", titles)
        self.assertIn("25 结论与展望", titles)

    def test_pdf_split_recovery_chinese_standalone_number(self):
        lines = [
            PdfTextLine(
                text="一、",
                page_index=1,
                x=72,
                y=100,
                width=30,
                height=15,
                font_size=11,
                bold_ratio=0.0,
                page_width=612,
                page_height=792,
                order=1,
            ),
            PdfTextLine(
                text="研究背景与意义",
                page_index=1,
                x=108,
                y=100,
                width=200,
                height=15,
                font_size=11,
                bold_ratio=1.0,
                page_width=612,
                page_height=792,
                order=2,
            ),
        ]

        candidates = _build_pdf_heading_candidates(lines, 0)

        titles = [candidate.display_title for candidate in candidates]
        self.assertIn("1 研究背景与意义", titles)
