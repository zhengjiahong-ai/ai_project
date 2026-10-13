"""Offline tests for services.deep_research.quote_pages."""

import copy
import unittest

from services.deep_research.quote_pages import resolve_quote_location

QUOTE = "The mitochondrial membrane potential drives ATP synthesis in healthy cells."


class ResolveQuoteLocationTests(unittest.TestCase):
    def test_inline_punctuation_spacing_without_merging_words_or_numbers(self):
        quote = 'The Example-GS method (i.e. anchor prediction) preserves quality.'
        result = resolve_quote_location(quote, [{'page': 2, 'text':
            'The Example -GS method ( i.e. anchor prediction ) preserves quality.'}], {})
        self.assertEqual(result['page'], 2)
        for quote, text in [
            ('The measured count was 1234 samples in this experiment.',
             'The measured count was 12-\n34 samples in this experiment.'),
            ('This therapist performs the complete evaluation procedure.',
             'This the rapist performs the complete evaluation procedure.'),
        ]:
            self.assertEqual(resolve_quote_location(quote, [{'page': 1, 'text': text}], {})['pageResolution'], 'unresolved')

    def test_wrong_page_is_corrected(self):
        pages = [
            {"page": 1, "text": "Introduction discusses prior work on mitochondria."},
            {"page": 3, "text": "Results show that " + QUOTE + " This is important."},
        ]
        location = {"page": 1, "pageIndex": 0, "section": "Results", "chunk": 2}
        result = resolve_quote_location(QUOTE, pages, location)
        self.assertEqual(result["page"], 3)
        self.assertEqual(result["pageIndex"], 2)
        self.assertEqual(result["pageResolution"], "exact")
        self.assertEqual(result["section"], "Results")
        self.assertEqual(result["chunk"], 2)

    def test_normalization_whitespace_soft_hyphen_ligature_wrap(self):
        page_text = (
            "We observe that efficient computation of attention weights "
            "reduces latency greatly."
        )
        quote = "e\ufb03cient  com\u00adputation\nof atten-\ntion weights reduces latency"
        pages = [{"page": 4, "text": page_text}]
        result = resolve_quote_location(quote, pages, {"page": 1})
        self.assertEqual(result["pageResolution"], "exact")
        self.assertEqual(result["page"], 4)
        self.assertEqual(result["pageIndex"], 3)

    def test_repeated_quote_is_ambiguous_and_ignores_old_page(self):
        pages = [
            {"page": 2, "text": "A. " + QUOTE},
            {"page": 5, "text": "B. " + QUOTE},
            {"page": 7, "text": "Unrelated filler text for page seven of the document."},
        ]
        location = {"page": 2, "pageIndex": 1, "pageStart": 2, "pageEnd": 2}
        result = resolve_quote_location(QUOTE, pages, location)
        self.assertEqual(result["pageResolution"], "ambiguous")
        self.assertEqual(result["pageCandidates"], [2, 5])
        for key in ("page", "pageIndex", "page_index", "pageStart", "pageEnd"):
            self.assertNotIn(key, result)

    def test_number_difference_is_unresolved(self):
        quote = "The model achieved 92.4% accuracy on the held-out evaluation split."
        pages = [
            {"page": 1, "text": "The model achieved 93.4% accuracy on the held-out split."}
        ]
        result = resolve_quote_location(quote, pages, {"page": 1})
        self.assertEqual(result["pageResolution"], "unresolved")
        self.assertNotIn("page", result)
        self.assertNotIn("pageCandidates", result)

    def test_short_quotes_never_match(self):
        short = "ATP synthesis."
        pages = [{"page": 1, "text": "Discussion of " + short + " continues here."}]
        result = resolve_quote_location(short, pages, {"page": 1})
        self.assertEqual(result["pageResolution"], "unresolved")
        self.assertNotIn("page", result)

    def test_inputs_are_not_mutated(self):
        pages = [
            {"page": 1, "text": QUOTE},
            {"page": 2, "text": QUOTE},
        ]
        location = {"page": 9, "pageIndex": 8, "bbox": [0, 0, 1, 1], "table": "t1"}
        pages_snapshot = copy.deepcopy(pages)
        location_snapshot = copy.deepcopy(location)
        resolve_quote_location(QUOTE, pages, location)
        self.assertEqual(pages, pages_snapshot)
        self.assertEqual(location, location_snapshot)

    def test_invalid_page_records_are_ignored(self):
        pages = [
            {"page": True, "text": QUOTE},
            {"page": "2", "text": QUOTE},
            {"page": 0, "text": QUOTE},
            {"page": -3, "text": QUOTE},
            {"text": QUOTE},
            {"page": 4},
            "junk",
            None,
            {"page": 6, "text": QUOTE},
        ]
        result = resolve_quote_location(QUOTE, pages, {})
        self.assertEqual(result["pageResolution"], "exact")
        self.assertEqual(result["page"], 6)
        self.assertEqual(result["pageIndex"], 5)

        all_invalid = [{"page": True, "text": QUOTE}, {"page": "1", "text": QUOTE}]
        result = resolve_quote_location(QUOTE, all_invalid, {"page": 1})
        self.assertEqual(result["pageResolution"], "unresolved")
        self.assertNotIn("page", result)

    def test_stale_geometry_fields_are_removed(self):
        pages = [{"page": 2, "text": "Body text: " + QUOTE}]
        location = {
            "page": 1,
            "pageIndex": 0,
            "pageStart": 1,
            "pageEnd": 1,
            "bbox": [10, 20, 30, 40],
            "coords": [[10, 20]],
            "offsets": {"start": 3, "end": 44},
            "section": "Methods",
        }
        result = resolve_quote_location(QUOTE, pages, location)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["pageResolution"], "exact")
        for key in ("pageStart", "pageEnd", "bbox", "coords", "offsets"):
            self.assertNotIn(key, result)
        self.assertEqual(result["section"], "Methods")

    def test_cross_page_quote_is_not_falsely_located(self):
        first_half = "The mitochondrial membrane potential drives"
        second_half = "ATP synthesis in healthy cells."
        self.assertEqual(QUOTE, first_half + " " + second_half)
        pages = [
            {"page": 1, "text": "Section opens. " + first_half},
            {"page": 2, "text": second_half + " Section continues."},
        ]
        result = resolve_quote_location(QUOTE, pages, {"page": 1, "pageIndex": 0})
        self.assertEqual(result["pageResolution"], "unresolved")
        self.assertNotIn("page", result)
        self.assertNotIn("pageIndex", result)
        self.assertNotIn("pageCandidates", result)


if __name__ == "__main__":
    unittest.main()
