import unittest
from unittest.mock import patch

from services import chat_service


class _FakeRag:
    @staticmethod
    def normalize_id(value):
        return str(value).lower()

    def __init__(self, documents):
        self.documents = documents
        self.filters = []

    def get_documents_by_metadata(self, filter_metadata=None, limit=200):
        self.filters.append((filter_metadata, limit))
        return self.documents[:limit]


class ChatExhaustiveRetrievalTests(unittest.TestCase):
    def test_ablation_existence_question_forces_two_current_paper_queries(self):
        plan = {
            "original": "他有做消融实验吗",
            "rewritten": "消融实验 模块贡献",
            "keywords": ["消融实验", "模块贡献"],
            "needsRetrieval": True,
            "queries": [
                {"query": "消融实验 模块贡献", "scope": "current_paper"},
                {"query": "related ablation work", "scope": "library"},
            ],
        }

        queries, profile = chat_service._prepare_chat_queries(
            "他有做消融实验吗", plan, "paper.pdf"
        )

        self.assertEqual(profile["name"], "ablation")
        self.assertEqual([item["scope"] for item in queries], ["current_paper", "current_paper"])
        self.assertIn("fixed threshold", queries[1]["query"])
        self.assertIn("dynamic threshold", queries[1]["query"])

    def test_keyword_scan_returns_ablation_hit_before_adjacent_context(self):
        documents = [
            {"text": "Previous page describes the densification method.", "metadata": {"chunk_index": 4}},
            {
                "text": "Figure 5. Ablation study. A fixed threshold creates artifacts, while our dynamic threshold improves rendering.",
                "metadata": {"chunk_index": 5, "page_index": 8},
            },
            {"text": "The next page reports quantitative rendering performance.", "metadata": {"chunk_index": 6}},
        ]
        fake_rag = _FakeRag(documents)
        profile = chat_service._get_exhaustive_search_profile("有没有消融实验？")

        with patch.object(chat_service, "get_rag", return_value=fake_rag):
            evidence = chat_service._retrieve_current_paper_lexical_evidence(
                "PAPER.PDF", profile, limit=3
            )

        self.assertEqual(fake_rag.filters, [({"id": "paper.pdf"}, 240)])
        self.assertEqual(evidence[0]["chunkIndex"], 5)
        self.assertIn("Ablation study", evidence[0]["text"])
        self.assertEqual({item["chunkIndex"] for item in evidence}, {4, 5, 6})

    def test_high_similarity_without_direct_existence_evidence_cannot_finish_search(self):
        judge = {
            "verdict": "CORRECT",
            "confidence": 0.91,
            "reason": "high similarity",
            "missingAspects": [],
            "shouldRetry": False,
        }
        evidence = [{"text": "The paper compares overall rendering quality with several baselines."}]

        gated = chat_service._enforce_existence_evidence_gate(
            "论文做了消融实验吗？", evidence, judge
        )

        self.assertEqual(gated["verdict"], "AMBIGUOUS")
        self.assertTrue(gated["shouldRetry"])
        self.assertLessEqual(gated["confidence"], 0.55)

    def test_bibliography_title_alone_is_not_direct_ablation_evidence(self):
        profile = chat_service._get_exhaustive_search_profile("是否做过消融实验？")
        evidence = [{"text": "Smith et al. A Survey of Ablation Studies. References."}]

        self.assertFalse(chat_service._has_profile_direct_evidence(evidence, profile))
        self.assertEqual(chat_service._score_profile_document(evidence[0]["text"], profile), 0.0)

    def test_agentic_retrieval_runs_specialized_query_even_when_primary_judge_is_correct(self):
        plan = {
            "original": "他有做消融实验吗",
            "rewritten": "ablation study",
            "keywords": ["ablation"],
            "needsRetrieval": True,
            "queries": [{"query": "ablation study", "scope": "current_paper"}],
        }
        calls = []

        def execute(step, **_kwargs):
            calls.append(step)
            if len(calls) == 1:
                return ([{"text": "Overall comparison with NeRF baselines.", "similarity": 0.94}], "current_paper")
            return ([{
                "text": "Figure 5 presents an ablation study comparing a fixed threshold with a dynamic threshold.",
                "similarity": 0.82,
            }], "current_paper")

        with (
            patch.object(chat_service, "_execute_chat_query_step", side_effect=execute),
            patch.object(chat_service, "_retrieve_current_paper_lexical_evidence", return_value=[]),
        ):
            evidence, scope, judge = chat_service._run_chat_agentic_retrieval(
                "他有做消融实验吗", plan, pdf_id="paper.pdf"
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["scope"], "current_paper")
        self.assertEqual(scope, "current_paper")
        self.assertTrue(any("Figure 5" in item["text"] for item in evidence))
        self.assertEqual(judge["verdict"], "CORRECT")


if __name__ == "__main__":
    unittest.main()
