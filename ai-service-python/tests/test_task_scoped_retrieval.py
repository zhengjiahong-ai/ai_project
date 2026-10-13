import unittest
from unittest.mock import patch

from services import chat_service
from services.chat_scope import ChatMaterialScope


class TaskScopedRetrievalTests(unittest.TestCase):
    def test_empty_task_never_queries_global_library(self):
        with (patch.object(chat_service, 'retrieve_fused_evidence') as filtered,
              patch.object(chat_service, 'retrieve_hybrid_results') as global_query):
            result = chat_service._retrieve_library_evidence(
                'question', material_scope=ChatMaterialScope(True, (), None, False))
        self.assertEqual(result, [])
        filtered.assert_not_called()
        global_query.assert_not_called()

    def test_filters_outside_hits_and_represents_both_papers_with_small_budget(self):
        def retrieve(_query, **kwargs):
            paper = kwargs['filter_metadata']['id']
            return [
                {'text': 'OUTSIDE SECRET', 'metadata': {'id': 'outside'}, 'similarity': 1},
                *[{'text': f'{paper} evidence {i}', 'metadata': {'id': paper}, 'similarity': 0.8}
                  for i in range(3)],
            ]
        with (patch.object(chat_service, 'retrieve_fused_evidence', side_effect=retrieve) as filtered,
              patch.object(chat_service, 'retrieve_hybrid_results') as global_query):
            result = chat_service._retrieve_library_evidence(
                'compare', library_limit=2,
                material_scope=ChatMaterialScope(True, ('a', 'b'), None, False))
        self.assertEqual([call.kwargs['filter_metadata'] for call in filtered.call_args_list],
                         [{'id': 'a'}, {'id': 'b'}])
        self.assertEqual([item['text'] for item in result], ['a evidence 0', 'b evidence 0'])
        global_query.assert_not_called()

    def test_legacy_library_search_remains_available(self):
        with patch.object(chat_service, 'retrieve_hybrid_results', return_value=[]) as search:
            chat_service._retrieve_library_evidence('legacy')
        search.assert_called_once_with('legacy', top_k=3)


if __name__ == '__main__':
    unittest.main()
