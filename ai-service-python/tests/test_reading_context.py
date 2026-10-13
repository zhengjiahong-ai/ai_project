import unittest
from services.reading_context import focus_page_context


class ReadingContextTests(unittest.TestCase):
    def test_keeps_selected_definition_and_following_formula_near_page_end(self):
        page = 'Earlier paragraph. ' * 200 + 'Global Significance Calculation. ' + 'The score includes opacity and transmittance T. ' * 15 + 'Later paragraph. ' * 200
        context = focus_page_context(page, 'Significance')
        self.assertIn('Global Significance Calculation.', context)
        self.assertIn('transmittance T', context)
        self.assertLessEqual(len(context), 3000)

    def test_case_variation_and_short_context(self):
        self.assertEqual(focus_page_context('Short text.', 'text'), 'Short text.')
        text = 'x' * 4000 + 'Selected definition and formula.' + 'y' * 4000
        self.assertIn('Selected definition', focus_page_context(text, 'SELECTED'))

    def test_missing_selection_stays_within_budget(self):
        self.assertEqual(focus_page_context('x' * 5000, 'missing', 1200), 'x' * 1200)

    def test_selection_matches_across_pdf_line_breaks(self):
        page = 'Earlier. ' * 600 + 'Global\n  Significance\tCalculation. Transmittance T.' + 'Later. ' * 600
        self.assertIn('Transmittance T.', focus_page_context(page, 'Global Significance Calculation.'))


if __name__ == '__main__':
    unittest.main()
