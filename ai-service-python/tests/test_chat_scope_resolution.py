import unittest

from schemas.requests import ChatRequest
from services.chat_scope import resolve_chat_material_scope


class ChatScopeResolutionTests(unittest.TestCase):
    def test_legacy_chat_keeps_single_paper_behavior(self):
        scope = resolve_chat_material_scope(ChatRequest(
            message="方法是什么", pdfId="Paper.PDF", paperSkeleton={"abstract": "summary"},
        ))
        self.assertFalse(scope.constrained)
        self.assertEqual(scope.primary_id, "Paper.PDF")
        self.assertTrue(scope.use_skeleton)

    def test_task_without_material_snapshot_fails_closed(self):
        scope = resolve_chat_material_scope(ChatRequest(
            message="方法是什么", taskId="task-1", pdfId="outside.pdf",
            paperSkeleton={"abstract": "outside"},
        ))
        self.assertTrue(scope.constrained)
        self.assertEqual(scope.allowed_ids, ())
        self.assertIsNone(scope.primary_id)
        self.assertFalse(scope.use_skeleton)

    def test_strict_multi_paper_scope_keeps_both_papers(self):
        scope = resolve_chat_material_scope(ChatRequest(
            message="只根据 A、B 比较", taskId="task-1",
            allowedPaperIds=["A.PDF", "B.PDF"], primaryPaperId="A.PDF",
            pdfId="A.PDF", strictScope=True,
        ))
        self.assertEqual(scope.allowed_ids, ("a.pdf", "b.pdf"))
        self.assertEqual(scope.primary_id, "a.pdf")

    def test_outside_primary_cannot_bind_client_skeleton(self):
        scope = resolve_chat_material_scope(ChatRequest(
            message="这篇呢", taskId="task-1", allowedPaperIds=["a.pdf"],
            primaryPaperId="outside.pdf", pdfId="outside.pdf",
            paperSkeleton={"abstract": "OUTSIDE SECRET"},
        ))
        self.assertEqual(scope.allowed_ids, ("a.pdf",))
        self.assertIsNone(scope.primary_id)
        self.assertFalse(scope.use_skeleton)

    def test_skeleton_must_match_primary_pdf_id(self):
        scope = resolve_chat_material_scope(ChatRequest(
            message="方法", taskId="task-1", allowedPaperIds=["a.pdf", "b.pdf"],
            primaryPaperId="a.pdf", pdfId="b.pdf",
            paperSkeleton={"abstract": "WRONG PAPER"},
        ))
        self.assertFalse(scope.use_skeleton)


if __name__ == "__main__":
    unittest.main()
