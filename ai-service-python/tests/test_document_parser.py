import unittest
from pathlib import Path

from core.document_parser import extract_translation_layout_index


class DocumentParserTests(unittest.TestCase):
    def test_extract_translation_layout_index_normalizes_coords(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<TEI>
  <facsimile>
    <surface n="1" lrx="600" lry="800" />
    <surface n="2" lrx="600" lry="800" />
  </facsimile>
  <text>
    <body>
      <figure coords="1,300,160,120,80">
        <head>Figure 1. Overview</head>
      </figure>
      <formula coords="2,60,500,150,40">E = mc^2</formula>
    </body>
  </text>
</TEI>
"""
        tei_path = Path("test_document_parser_sample.tei.xml")
        try:
            tei_path.write_text(xml, encoding="utf-8")
            index = extract_translation_layout_index(str(tei_path))
        finally:
            if tei_path.exists():
                tei_path.unlink()

        self.assertIn(0, index)
        self.assertIn(1, index)
        self.assertEqual(index[0]["pageSize"]["width"], 600.0)
        figure_zone = index[0]["excludedZones"][0]
        self.assertEqual(figure_zone["type"], "figure")
        self.assertAlmostEqual(figure_zone["bbox"]["left"], 0.5)
        self.assertAlmostEqual(figure_zone["bbox"]["top"], 0.2)
        formula_zone = index[1]["excludedZones"][0]
        self.assertEqual(formula_zone["type"], "formula")


if __name__ == "__main__":
    unittest.main()
