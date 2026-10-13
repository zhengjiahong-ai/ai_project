import unittest
from unittest.mock import patch
from services import research_executor as executor


class ResearchMaterialScopeTests(unittest.TestCase):
    def test_empty_snapshot_never_invokes_global_retrieval(self):
        with patch.object(executor, 'invoke_tool') as tool:
            self.assertEqual(executor.retrieve_library_evidence('question', allowed_paper_ids=[]), [])
        tool.assert_not_called()

    def test_snapshot_excludes_current_and_filters_leaked_hits(self):
        def retrieve(query, pdf_id, **kwargs):
            return [{'text': f'{pdf_id} finding', 'pdfId': pdf_id, 'sourceId': pdf_id},
                    {'text': 'outside secret', 'pdfId': 'outside', 'sourceId': 'outside'}]
        with (patch.object(executor, 'retrieve_current_paper_evidence', side_effect=retrieve) as current,
              patch.object(executor, 'invoke_tool') as global_tool):
            items = executor.retrieve_library_evidence('compare', exclude_pdf_id='a', allowed_paper_ids=['a', 'b', 'c'], limit=2)
        self.assertEqual([call.args[1] for call in current.call_args_list], ['b', 'c'])
        self.assertEqual({item['pdfId'] for item in items}, {'b', 'c'})
        global_tool.assert_not_called()

    def test_primary_outside_snapshot_fails_before_planning(self):
        with patch.object(executor, 'build_retrieval_queries') as planner:
            with self.assertRaises(ValueError):
                executor.research_sub_question('q', 'q', 'outside', {}, [], allowed_paper_ids=['a'])
        planner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
