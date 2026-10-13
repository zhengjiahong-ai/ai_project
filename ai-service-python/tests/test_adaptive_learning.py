"""Offline contracts; mocked retrieval/LLM do not establish live Provider quality."""
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from schemas.adaptive_learning import AdaptiveLearningActionRequest, AdaptiveLearningStartRequest, LearningState
from services import adaptive_learning_service as service

EVIDENCE = [{"sourceId": "A:1", "pdfId": "A", "text": "The method optimizes Gaussian positions using photometric loss.", "sourceType": "current_paper"}]
PLAN = {"concepts": [{"label": "优化", "question": "位置如何优化？"}, {"label": "实验", "question": "实验说明什么？"}]}


class AdaptiveLearningTests(unittest.TestCase):
    def setUp(self):
        self.original_retrieve = service._retrieve
        self.retrieve_patch = patch.object(service, "_retrieve", return_value=EVIDENCE)
        self.retrieval = self.retrieve_patch.start()
        self.quality = patch.object(service, "_quality", return_value={"verdict": "CORRECT"}).start()
        self.model = patch.object(service, "_json", return_value=PLAN).start()
        self.addCleanup(patch.stopall)
        self.state = LearningState(**service.start_activity(AdaptiveLearningStartRequest(taskId="T", pdfId="A"))["state"])

    def action(self, action, text=""):
        return service.transition_activity(AdaptiveLearningActionRequest(taskId="T", activityId=self.state.activityId,
            expectedRevision=self.state.revision, state=self.state, action=action, text=text))

    def model_result(self, verdict, missing=None, references=None):
        self.model.return_value = {"verdict": verdict, "feedback": "根据位置优化这一原文关系，请再解释目标。",
            "missingAspects": missing or [], "references": references if references is not None else
            [{"sourceId": "A:1", "quote": "using photometric loss"}]}

    def test_partial_and_incorrect_keep_question_and_use_gap_for_followup(self):
        for verdict in ("partial", "incorrect"):
            self.model_result(verdict, ["光度损失如何监督位置"])
            out = self.action("answer", "位置固定不用优化")
            self.assertEqual(out["state"]["currentConceptId"], self.state.currentConceptId)
            self.assertEqual(out["evaluation"]["verdict"], verdict)
            self.assertEqual(out["suggestedAction"], "remediate")
            self.assertEqual(out["state"]["concepts"][0]["status"], "needs_review")
            self.state = LearningState(**out["state"])
            self.action("hint")
            self.assertIn("光度损失如何监督位置", self.retrieval.call_args.args[1])
            self.assertIn("光度损失如何监督位置", self.model.call_args.args[0])

    def test_read_explains_before_question_and_quiz_does_not_reveal_answer(self):
        self.model.return_value = {"concepts": [{"label": "优化", "question": "位置如何优化？",
            "explanation": "位置是待优化的变量，光度损失提供监督信号。",
            "references": [{"sourceId": "A:1", "quote": "using photometric loss"}]}]}
        read = service.start_activity(AdaptiveLearningStartRequest(taskId="T", pdfId="A", mode="read", goal="我不懂监督信号"))
        self.assertEqual(read["message"], "位置是待优化的变量，光度损失提供监督信号。")
        self.assertEqual(read["question"], "位置如何优化？")
        self.assertIn("我不懂监督信号", self.model.call_args.args[0])
        quiz = service.start_activity(AdaptiveLearningStartRequest(taskId="T", pdfId="A", mode="quiz"))
        self.assertNotIn("光度损失", quiz["message"])
        self.assertEqual(quiz["state"]["concepts"][0]["explanation"], "")

    def test_read_never_presents_unverified_explanation_as_paper_fact(self):
        self.model.return_value = {"concepts": [{"label": "优化", "question": "位置如何优化？",
            "explanation": "错误说明", "references": [{"sourceId": "missing", "quote": "invented source"}]}]}
        result = service.start_activity(AdaptiveLearningStartRequest(taskId="T", pdfId="A"))
        self.assertNotIn("错误说明", result["message"])
        self.assertIn("先从", result["message"])
        self.assertEqual(result["state"]["concepts"][0]["explanationReferences"], [])

    def test_next_read_concept_explanation_appears_only_after_demonstrated_answer(self):
        self.state.concepts[1].explanation = "接下来查看实验如何检验优化效果。"
        self.state.concepts[1].explanationSources = [{"sourceId": "A:2", "pdfId": "A", "text": "Experimental evidence."}]
        self.model_result("partial", ["监督关系"])
        self.assertNotIn("接下来查看", self.action("answer", "答案")["message"])
        self.model_result("demonstrated")
        result = self.action("answer", "光度损失监督位置")
        self.assertIn("接下来查看", result["message"])
        self.assertEqual(result["question"], self.state.concepts[1].question)
        self.assertEqual({source["sourceId"] for source in result["sources"]}, {"A:1", "A:2"})

    def test_title_quote_cannot_justify_a_learning_judgment(self):
        self.retrieval.return_value = [{"sourceId": "A:1", "text": "Paper: Gaussian Positions\n\nContent:\nThe method uses photometric loss."}]
        self.model_result("demonstrated", references=[{"sourceId": "A:1", "quote": "Gaussian Positions"}])
        self.assertEqual(self.action("answer", "答案")["evaluation"]["verdict"], "unassessable")

    def test_skip_in_read_mode_bridges_to_next_explanation_with_its_sources(self):
        self.state.concepts[1].explanation = "实验用于检查方法是否有效。"
        self.state.concepts[1].explanationSources = [{"sourceId": "A:2", "pdfId": "A", "text": "Experimental evidence."}]
        result = self.action("skip")
        self.assertIn("实验用于", result["message"])
        self.assertEqual(result["question"], self.state.concepts[1].question)
        self.assertIn("A:2", {source["sourceId"] for source in result["sources"]})

    def test_unverified_missing_aspects_do_not_trigger_remediation(self):
        self.model_result("incorrect", ["invented learning gap"], references=[])
        result = self.action("answer", "答案")
        self.assertEqual(result["evaluation"]["verdict"], "unassessable")
        self.assertEqual(result["evaluation"]["missingAspects"], [])
        self.assertEqual(result["suggestedAction"], "retry")

    def test_remediation_receives_the_previous_answer_of_the_same_concept(self):
        self.model_result("incorrect", ["有源负载"])
        answered = self.action("answer", "只能调整相位，不能放大")
        self.state = LearningState(**answered["state"])
        self.state.turns.append({"action": "answer", "conceptId": "other", "text": "另一概念的答案"})
        self.action("remediate")
        prompt = self.model.call_args.args[0]
        self.assertIn('"lastAnswer": "只能调整相位，不能放大"', prompt)
        self.assertNotIn("另一概念的答案", prompt)

    def test_pending_concepts_precede_skipped_concepts_after_correct_answer(self):
        from schemas.adaptive_learning import LearningConcept
        self.state.concepts[0].status = "skipped"
        self.state.currentConceptId = self.state.concepts[1].id
        self.state.concepts.append(LearningConcept(id="third", label="条件", question="适用条件是什么？"))
        self.model_result("demonstrated")
        result = self.action("answer", "正确解释")
        self.assertEqual(result["state"]["currentConceptId"], "third")

    def test_no_evidence_or_weak_evidence_does_not_mark_wrong(self):
        self.retrieval.return_value = []
        out = self.action("answer", "用户答案")
        self.assertEqual(out["evaluation"]["verdict"], "unassessable")
        self.assertEqual(out["state"]["concepts"][0]["status"], "pending")
        self.assertEqual(out["state"]["currentConceptId"], self.state.currentConceptId)
        self.retrieval.return_value = EVIDENCE
        self.quality.return_value = {"verdict": "AMBIGUOUS"}
        self.assertEqual(self.action("answer", "用户答案")["evaluation"]["verdict"], "unassessable")

    def test_forged_or_nonliteral_citation_cannot_justify_marking_wrong(self):
        for refs in ([{"sourceId": "B:9", "quote": "using photometric loss"}],
                     [{"sourceId": "A:1", "quote": "invented evidence"}], []):
            self.model_result("incorrect", references=refs)
            self.assertEqual(self.action("answer", "答案")["evaluation"]["verdict"], "unassessable")

    def test_demonstrated_advances_but_never_ends_at_five_or_any_count(self):
        self.model_result("demonstrated")
        self.state.turns = [{"action": "answer"}] * 5
        out = self.action("answer", "光度损失监督位置优化")
        self.assertNotEqual(out["state"]["currentConceptId"], self.state.currentConceptId)
        self.assertEqual(out["state"]["status"], "active")
        self.state = LearningState(**out["state"])
        out = self.action("answer", "实验答案")
        self.assertTrue(out["completionSuggested"])
        self.assertEqual(out["state"]["status"], "active")
        self.assertEqual(out["suggestedAction"], "finish")
        self.assertIsNone(out["question"])
        self.assertIn("本轮概念已核验", out["message"])
        self.state = LearningState(**out["state"])
        reviewed = self.action("retry")
        self.assertFalse(reviewed["completionSuggested"])
        self.assertTrue(reviewed["question"])

    def test_provider_failure_does_not_mutate_input_and_can_retry_revision(self):
        original = self.state.model_dump()
        self.model.side_effect = RuntimeError("Provider unavailable")
        with self.assertRaises(RuntimeError):
            self.action("answer", "答案")
        self.assertEqual(self.state.model_dump(), original)
        self.model.side_effect = None
        self.model_result("partial", ["监督信号"])
        out = self.action("answer", "答案")
        self.assertEqual(out["state"]["revision"], original["revision"] + 1)
        self.assertEqual(out["state"]["turns"][-1]["evidence"], EVIDENCE)

    def test_paper_snapshot_mismatch_is_rejected(self):
        self.state.paperIds = ["B"]
        with self.assertRaises(service.LearningConflict):
            self.action("pause")

    def test_serialized_pause_resume_and_temporary_question_keep_paper(self):
        original = self.state.currentConceptId
        self.state = LearningState(**json.loads(json.dumps(self.action("pause")["state"])))
        with self.assertRaises(service.LearningConflict):
            self.action("hint")
        self.state = LearningState(**self.action("resume")["state"])
        self.model_result("partial")
        out = self.action("ask", "光度损失是什么？")
        self.assertEqual(out["state"]["currentConceptId"], original)
        self.assertEqual(self.retrieval.call_args.args[0], "A")
        self.assertEqual(out["state"]["concepts"][0]["attempts"], 0)

    def test_skip_is_unresolved_retry_preserves_history_and_finish_is_explicit(self):
        out = self.action("skip")
        self.assertIn(self.state.currentConceptId, out["unresolvedConceptIds"])
        skipped = self.state.currentConceptId
        self.state = LearningState(**out["state"])
        self.state = LearningState(**self.action("retry", skipped)["state"])
        self.assertEqual(self.state.currentConceptId, skipped)
        out = self.action("finish")
        self.assertEqual(out["state"]["finishReason"], "user_requested")
        self.assertFalse(out["completionSuggested"])
        self.state = LearningState(**out["state"])
        with self.assertRaises(service.LearningConflict):
            self.action("answer", "答案")

    def test_snapshot_task_activity_and_revision_conflicts(self):
        request = AdaptiveLearningActionRequest(taskId="other", activityId=self.state.activityId,
            expectedRevision=0, action="pause", state=self.state)
        with self.assertRaises(service.LearningConflict):
            service.transition_activity(request)
        request.taskId = "T"
        request.expectedRevision = 42
        with self.assertRaises(service.LearningConflict):
            service.transition_activity(request)

    def test_retrieval_filters_and_discards_other_paper(self):
        with patch.object(service, "get_rag", return_value=Mock(normalize_id=lambda value: value)), \
             patch.object(service, "retrieve_fused_evidence", return_value=EVIDENCE +
                 [{"sourceId": "B:1", "pdfId": "B", "text": "out of scope"}]) as retrieve:
            self.assertEqual([item["pdfId"] for item in self.original_retrieve("A", "优化")], ["A"])
            self.assertEqual(retrieve.call_args.kwargs["filter_metadata"], {"id": "A"})

    def test_new_routes_and_legacy_endpoints_still_exist(self):
        from routes.adaptive_learning_routes import adaptive_learning_router, adaptive_learning_action
        self.assertEqual({r.path for r in adaptive_learning_router.routes},
                         {"/adaptive-learning/start", "/adaptive-learning/action"})
        file = Path(__file__).resolve().parents[1] / "routes" / "reading_routes.py"
        source = file.read_text(encoding="utf-8")
        for endpoint in ("/socratic-questions", "/socratic-session/start", "/socratic-session/answer"):
            self.assertIn(endpoint, source)
        request = AdaptiveLearningActionRequest(taskId="wrong", activityId=self.state.activityId,
            expectedRevision=0, action="pause", state=self.state)
        self.assertEqual(asyncio.run(adaptive_learning_action(request)).status_code, 409)


if __name__ == "__main__":
    unittest.main()
