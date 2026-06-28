import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from llm.client import DeepSeekLLM
from schemas.requests import ResearchFinalReviewRequest, ResearchPlanReviewRequest, ResearchTaskCreateRequest
from services import research_executor, research_task_service, trace_service


ADVERSARIAL_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "external_search_adversarial.json").read_text(encoding="utf-8")
)


class DeepSeekLLMTraceCounterTests(unittest.TestCase):
    def tearDown(self):
        trace_service.clear_traces()

    def test_call_records_llm_and_estimated_token_counters(self):
        trace_id = trace_service.start_trace("unit_test")
        fake_response = Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "short answer",
                    }
                }
            ]
        }

        with patch("llm.client.requests.post", return_value=fake_response):
            result = DeepSeekLLM(api_key="test-key")._call(
                messages=[
                    {"role": "system", "content": "system instruction"},
                    {"role": "user", "content": "user question"},
                ]
            )

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(result, "short answer")
        self.assertEqual(snapshot["counters"]["llmCalls"], 1)
        self.assertGreater(snapshot["counters"]["estimatedInputTokens"], 0)
        self.assertGreater(snapshot["counters"]["estimatedOutputTokens"], 0)


class ResearchTaskDynamicReplanningTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("RESEARCH_TASK_DB_PATH")
        os.environ["RESEARCH_TASK_DB_PATH"] = os.path.join(self.temp_dir.name, "research_tasks.sqlite3")
        research_task_service.clear_research_tasks(clear_storage=True)

    def tearDown(self):
        trace_service.clear_traces()
        research_task_service.clear_research_tasks(clear_storage=True)
        if self.previous_db_path is None:
            os.environ.pop("RESEARCH_TASK_DB_PATH", None)
        else:
            os.environ["RESEARCH_TASK_DB_PATH"] = self.previous_db_path
        self.temp_dir.cleanup()

    def _create_task(self):
        response = research_task_service.create_research_task(
            ResearchTaskCreateRequest(question="验证实验结论是否充分", pdfId="paper-1", paperSkeleton={}),
            start_async=False,
        )
        return response["task"]["taskId"]

    def test_plan_and_final_review_gate_task_execution(self):
        task_id = self._create_task()
        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
        ):
            planned = research_task_service.prepare_research_task_now(task_id)

        self.assertEqual(planned["status"], "awaiting_plan_review")
        self.assertEqual(planned["plan"][0]["question"], "子问题一")

        with patch.object(research_task_service._TASK_EXECUTOR, "submit") as submit:
            approved = research_task_service.review_research_plan(
                task_id,
                ResearchPlanReviewRequest(subQuestions=["修改后的子问题"], reviewNotes="聚焦实验"),
            )["task"]
        self.assertEqual(approved["status"], "running")
        self.assertEqual(approved["plan"][0]["question"], "修改后的子问题")
        submit.assert_called_once()

        research_task_service._update_task_snapshot(
            task_id,
            status="awaiting_final_review",
            reviewRisks=[{"riskId": "missing:finding-1", "type": "missing_evidence", "label": "证据缺口", "detail": "缺少消融", "sourceIds": [], "reviewStatus": "pending"}],
        )
        completed = research_task_service.review_research_final(
            task_id,
            ResearchFinalReviewRequest(
                reviewNotes="保留待核查提示",
                riskReviews=[{"riskId": "missing:finding-1", "reviewStatus": "needs_follow_up"}],
            ),
        )["task"]
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["humanReview"]["final"]["riskReviews"][0]["reviewStatus"], "needs_follow_up")

    def _run_task_with_findings(self, findings):
        task_id = self._create_task()
        calls = []

        def fake_research_sub_question(sub_question, **_kwargs):
            calls.append(sub_question)
            if len(calls) <= len(findings):
                return {**findings[len(calls) - 1], "subQuestion": sub_question}
            return {
                "subQuestion": sub_question,
                "summary": "follow-up evidence checked",
                "verdict": "CORRECT",
                "judgeScore": 80,
                "coverage": {"score": 0.8, "matchedAspects": 2, "totalAspects": 2, "evidenceCount": 2, "sourceTypes": ["current_paper"]},
                "missingAspects": [],
                "retryReason": "",
                "sourceIds": ["source-follow"],
                "sources": [{"sourceId": "source-follow", "text": "follow evidence"}],
            }

        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一", "子问题二", "子问题三"])),
            patch.object(research_task_service, "_research_sub_question", side_effect=fake_research_sub_question),
        ):
            task = research_task_service.run_research_task_now(task_id)

        return task, calls

    def test_insufficient_finding_adds_one_follow_up_plan_item_and_finding(self):
        task, calls = self._run_task_with_findings(
            [
                {
                    "summary": "缺少消融实验证据",
                    "verdict": "INCORRECT",
                    "judgeScore": 25,
                    "coverage": {"score": 0.2, "matchedAspects": 0, "totalAspects": 2, "evidenceCount": 0, "sourceTypes": []},
                    "missingAspects": ["消融实验", "关键指标"],
                    "retryReason": "证据不足",
                    "sourceIds": [],
                    "sources": [],
                },
                {
                    "summary": "已有方法证据",
                    "verdict": "CORRECT",
                    "judgeScore": 86,
                    "coverage": {"score": 0.9, "matchedAspects": 2, "totalAspects": 2, "evidenceCount": 2, "sourceTypes": ["current_paper"]},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["source-2"],
                    "sources": [],
                },
                {
                    "summary": "已有局限证据",
                    "verdict": "CORRECT",
                    "judgeScore": 84,
                    "coverage": {"score": 0.8, "matchedAspects": 2, "totalAspects": 2, "evidenceCount": 2, "sourceTypes": ["current_paper"]},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["source-3"],
                    "sources": [],
                },
            ]
        )

        self.assertEqual(len(calls), 4)
        self.assertEqual(len(task["plan"]), 4)
        self.assertEqual(task["plan"][0]["kind"], "initial")
        self.assertEqual(task["plan"][0]["status"], "done")
        follow_up_item = task["plan"][-1]
        self.assertEqual(follow_up_item["kind"], "follow_up")
        self.assertEqual(follow_up_item["status"], "done")
        self.assertEqual(follow_up_item["sourceQuestion"], "子问题一")
        self.assertEqual(follow_up_item["sourceMissingAspects"], ["消融实验", "关键指标"])
        self.assertIn("消融实验", follow_up_item["question"])

        follow_up_finding = task["findings"][-1]
        self.assertTrue(follow_up_finding["isFollowUp"])
        self.assertEqual(follow_up_finding["followUpOf"], "子问题一")
        self.assertEqual(follow_up_finding["sourceMissingAspects"], ["消融实验", "关键指标"])

    def test_multiple_insufficient_findings_still_add_only_one_follow_up(self):
        task, calls = self._run_task_with_findings(
            [
                {"summary": "不足一", "verdict": "INCORRECT", "judgeScore": 20, "coverage": {}, "missingAspects": ["指标 A"], "retryReason": "", "sourceIds": [], "sources": []},
                {"summary": "不足二", "verdict": "INCORRECT", "judgeScore": 30, "coverage": {}, "missingAspects": ["指标 B"], "retryReason": "", "sourceIds": [], "sources": []},
                {"summary": "不足三", "verdict": "INCORRECT", "judgeScore": 35, "coverage": {}, "missingAspects": ["指标 C"], "retryReason": "", "sourceIds": [], "sources": []},
            ]
        )

        self.assertEqual(len(calls), 4)
        self.assertEqual([item["kind"] for item in task["plan"]].count("follow_up"), 1)
        self.assertEqual(sum(1 for finding in task["findings"] if finding.get("isFollowUp")), 1)

    def test_ambiguous_or_missing_gap_does_not_add_follow_up(self):
        task, calls = self._run_task_with_findings(
            [
                {"summary": "部分相关", "verdict": "AMBIGUOUS", "judgeScore": 55, "coverage": {}, "missingAspects": ["更多指标"], "retryReason": "", "sourceIds": [], "sources": []},
                {"summary": "无缺口", "verdict": "INCORRECT", "judgeScore": 30, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": [], "sources": []},
                {"summary": "充分", "verdict": "CORRECT", "judgeScore": 90, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": [], "sources": []},
            ]
        )

        self.assertEqual(len(calls), 3)
        self.assertEqual([item["kind"] for item in task["plan"]].count("follow_up"), 0)
        self.assertEqual(len(task["findings"]), 3)

    def test_detects_numeric_conflicts_and_persists_them(self):
        task, _calls = self._run_task_with_findings(
            [
                {
                    "summary": "当前论文报告 accuracy 达到 91.2%。",
                    "verdict": "CORRECT",
                    "judgeScore": 82,
                    "coverage": {},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["paper-accuracy"],
                    "sources": [
                        {
                            "sourceId": "paper-accuracy",
                            "text": "The accuracy reaches 91.2% on the benchmark.",
                            "sourceType": "current_paper",
                            "pageIndex": 3,
                            "chunkIndex": 2,
                        }
                    ],
                },
                {
                    "summary": "内部文献库记录 accuracy 为 87.5%。",
                    "verdict": "CORRECT",
                    "judgeScore": 80,
                    "coverage": {},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["library-accuracy"],
                    "sources": [
                        {
                            "sourceId": "library-accuracy",
                            "text": "A replication reports accuracy of 87.5% under the same benchmark.",
                            "sourceType": "library",
                            "pageIndex": 5,
                            "chunkIndex": 9,
                        }
                    ],
                },
                {"summary": "无额外冲突。", "verdict": "CORRECT", "judgeScore": 90, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": [], "sources": []},
            ]
        )

        self.assertEqual(task["conflicts"][0]["conflictType"], "numeric_mismatch")
        self.assertEqual(task["conflicts"][0]["severity"], "high")
        self.assertIn("91.2%", task["conflicts"][0]["summary"])
        self.assertIn("87.5%", task["conflicts"][0]["summary"])
        self.assertEqual(task["conflicts"][0]["sourceIds"], ["paper-accuracy", "library-accuracy"])
        self.assertIn("graphContext", task["conflicts"][0])
        self.assertIn("## 证据冲突/需人工核查", task["report"])
        self.assertIn("图谱上下文", task["report"])
        self.assertIn("未自动裁决", task["report"])
        self.assertIn("paper-accuracy", task["report"])

        research_task_service.reload_research_tasks_from_storage()
        restored = research_task_service.get_research_task(task["taskId"])["task"]
        self.assertEqual(restored["conflicts"][0]["sourceIds"], ["paper-accuracy", "library-accuracy"])

    def test_detects_opposing_conclusion_conflicts(self):
        task, _calls = self._run_task_with_findings(
            [
                {
                    "summary": "方法显著提升效果。",
                    "verdict": "CORRECT",
                    "judgeScore": 82,
                    "coverage": {},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["paper-effect"],
                    "sources": [
                        {
                            "sourceId": "paper-effect",
                            "text": "The proposed method significantly improves retrieval quality.",
                            "sourceType": "current_paper",
                        }
                    ],
                },
                {
                    "summary": "复现实验显示没有提升。",
                    "verdict": "AMBIGUOUS",
                    "judgeScore": 58,
                    "coverage": {},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["library-effect"],
                    "sources": [
                        {
                            "sourceId": "library-effect",
                            "text": "The replication shows no improvement in retrieval quality.",
                            "sourceType": "library",
                        }
                    ],
                },
                {"summary": "无额外冲突。", "verdict": "CORRECT", "judgeScore": 90, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": [], "sources": []},
            ]
        )

        conflict_types = [item["conflictType"] for item in task["conflicts"]]
        self.assertIn("opposing_conclusion", conflict_types)

    def test_does_not_report_conflict_for_unrelated_or_matching_values(self):
        task, _calls = self._run_task_with_findings(
            [
                {
                    "summary": "accuracy 为 91.2%。",
                    "verdict": "CORRECT",
                    "judgeScore": 82,
                    "coverage": {},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["paper-accuracy"],
                    "sources": [{"sourceId": "paper-accuracy", "text": "Accuracy is 91.2%.", "sourceType": "current_paper"}],
                },
                {
                    "summary": "f1 为 87.5%。",
                    "verdict": "CORRECT",
                    "judgeScore": 80,
                    "coverage": {},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["library-f1"],
                    "sources": [{"sourceId": "library-f1", "text": "F1 is 87.5%.", "sourceType": "library"}],
                },
                {
                    "summary": "accuracy 同样为 91.2%。",
                    "verdict": "CORRECT",
                    "judgeScore": 90,
                    "coverage": {},
                    "missingAspects": [],
                    "retryReason": "",
                    "sourceIds": ["library-accuracy"],
                    "sources": [{"sourceId": "library-accuracy", "text": "Accuracy reaches 91.2%.", "sourceType": "library"}],
                },
            ]
        )

        self.assertEqual(task["conflicts"], [])
        self.assertNotIn("## 证据冲突/需人工核查", task["report"])

    def test_successful_task_persists_public_trace_summary(self):
        task, _calls = self._run_task_with_findings(
            [
                {"summary": "已有方法证据", "verdict": "CORRECT", "judgeScore": 86, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": ["source-1"], "sources": []},
                {"summary": "已有实验支撑", "verdict": "CORRECT", "judgeScore": 84, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": ["source-2"], "sources": []},
                {"summary": "已有局限说明", "verdict": "CORRECT", "judgeScore": 82, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": ["source-3"], "sources": []},
            ]
        )

        summary = task["traceSummary"]
        self.assertEqual(summary["traceId"], task["traceId"])
        self.assertEqual(summary["taskType"], "deep_research")
        self.assertEqual(summary["status"], "awaiting_review")
        self.assertEqual(summary["responseMeta"]["taskId"], task["taskId"])
        self.assertEqual(summary["responseMeta"]["findingCount"], 3)
        self.assertGreaterEqual(len(summary["steps"]), 1)
        self.assertTrue(
            {
                "llmCalls",
                "retrievalCalls",
                "retryCount",
                "truncationCount",
                "estimatedInputTokens",
                "estimatedOutputTokens",
            }.issubset(set(summary["counters"].keys()))
        )
        self.assertEqual(summary["counters"]["retryCount"], 0)
        self.assertEqual(summary["counters"]["truncationCount"], 0)

    def test_research_retry_increments_trace_retry_counter(self):
        task_id = self._create_task()
        judge_calls = []

        def fake_judge(_sub_question, _evidence, **_kwargs):
            judge_calls.append(True)
            if len(judge_calls) == 1:
                return {
                    "verdict": "INCORRECT",
                    "judgeScore": 20,
                    "coverage": {"score": 0.1, "matchedAspects": 0, "totalAspects": 2, "evidenceCount": 1, "sourceTypes": ["current_paper"]},
                    "missingAspects": ["消融实验"],
                    "retryReason": "证据不足，需要补查消融实验。",
                    "shouldRetry": False,
                }
            if len(judge_calls) == 2:
                return {
                    "verdict": "INCORRECT",
                    "judgeScore": 30,
                    "coverage": {"score": 0.2, "matchedAspects": 0, "totalAspects": 2, "evidenceCount": 2, "sourceTypes": ["current_paper", "library"]},
                    "missingAspects": ["消融实验"],
                    "retryReason": "证据不足，需要补查消融实验。",
                    "shouldRetry": True,
                }
            return {
                "verdict": "CORRECT",
                "judgeScore": 88,
                "coverage": {"score": 0.9, "matchedAspects": 2, "totalAspects": 2, "evidenceCount": 2, "sourceTypes": ["current_paper", "library"]},
                "missingAspects": [],
                "retryReason": "",
                "shouldRetry": False,
            }

        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
            patch.object(research_executor, "retrieve_current_paper_evidence", return_value=[{"sourceId": "paper-1", "text": "paper evidence", "sourceType": "current_paper"}]),
            patch.object(research_executor, "retrieve_library_evidence", return_value=[{"sourceId": "lib-1", "text": "library evidence", "sourceType": "library"}]),
            patch.object(research_executor, "judge_research_evidence", side_effect=fake_judge),
        ):
            task = research_task_service.run_research_task_now(task_id)

        self.assertGreaterEqual(task["traceSummary"]["counters"]["retryCount"], 1)

    def test_research_safety_budget_clamp_increments_truncation_counter(self):
        trace_id = trace_service.start_trace("deep_research")
        block = research_task_service.wrap_untrusted_context("large block", "x" * 200, max_tokens=10)

        research_task_service._record_safety_budget_counters(block)

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["truncationCount"], 1)

    def test_trace_summary_can_be_loaded_from_task_snapshot_after_restart(self):
        task, _calls = self._run_task_with_findings(
            [
                {"summary": "已有方法证据", "verdict": "CORRECT", "judgeScore": 86, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": ["source-1"], "sources": []},
                {"summary": "已有实验支撑", "verdict": "CORRECT", "judgeScore": 84, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": ["source-2"], "sources": []},
                {"summary": "已有局限说明", "verdict": "CORRECT", "judgeScore": 82, "coverage": {}, "missingAspects": [], "retryReason": "", "sourceIds": ["source-3"], "sources": []},
            ]
        )

        trace_service.clear_traces()
        research_task_service.reload_research_tasks_from_storage()

        response = trace_service.get_trace_summary(task["traceId"])

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["trace"]["traceId"], task["traceId"])
        self.assertEqual(response["trace"]["responseMeta"]["taskId"], task["taskId"])
        self.assertEqual(response["trace"]["status"], "awaiting_review")

    def test_trace_lookup_missing_persisted_summary_still_raises_not_found(self):
        task_id = self._create_task()
        task = research_task_service.get_research_task(task_id)["task"]

        trace_service.clear_traces()
        research_task_service.reload_research_tasks_from_storage()

        with self.assertRaises(trace_service.TraceNotFoundError):
            trace_service.get_trace_summary(task["traceId"])

    def test_storage_migration_adds_trace_summary_column_to_old_database(self):
        db_path = os.environ["RESEARCH_TASK_DB_PATH"]
        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("DROP TABLE IF EXISTS research_tasks")
            connection.execute(
                """
                CREATE TABLE research_tasks (
                    taskId TEXT PRIMARY KEY,
                    traceId TEXT,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress REAL NOT NULL,
                    question TEXT NOT NULL,
                    pdfId TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    findings TEXT NOT NULL,
                    conflicts TEXT NOT NULL DEFAULT '[]',
                    report TEXT NOT NULL,
                    error TEXT NOT NULL,
                    createdAt TEXT NOT NULL,
                    updatedAt TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO research_tasks (
                    taskId, traceId, status, stage, progress, question, pdfId,
                    plan, findings, conflicts, report, error, createdAt, updatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "old-task",
                    "old-trace",
                    "succeeded",
                    "done",
                    1.0,
                    "旧任务",
                    "paper-1",
                    "[]",
                    "[]",
                    "[]",
                    "旧报告",
                    "",
                    "2026-06-13T00:00:00Z",
                    "2026-06-13T00:00:00Z",
                ),
            )
            connection.commit()

        research_task_service.reload_research_tasks_from_storage()
        restored = research_task_service.get_research_task("old-task")["task"]

        self.assertEqual(restored["traceSummary"], {})
        with closing(sqlite3.connect(db_path)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(research_tasks)").fetchall()}
        self.assertIn("traceSummary", columns)


class ResearchTaskExternalSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("RESEARCH_TASK_DB_PATH")
        os.environ["RESEARCH_TASK_DB_PATH"] = os.path.join(self.temp_dir.name, "research_tasks.sqlite3")
        research_task_service.clear_research_tasks(clear_storage=True)

    def tearDown(self):
        trace_service.clear_traces()
        research_task_service.clear_research_tasks(clear_storage=True)
        if self.previous_db_path is None:
            os.environ.pop("RESEARCH_TASK_DB_PATH", None)
        else:
            os.environ["RESEARCH_TASK_DB_PATH"] = self.previous_db_path
        self.temp_dir.cleanup()

    def _create_task(self, allow_external_search=False):
        response = research_task_service.create_research_task(
            ResearchTaskCreateRequest(question="验证实验结论是否充分", pdfId="paper-1", paperSkeleton={}, allowExternalSearch=allow_external_search),
            start_async=False,
        )
        return response["task"]["taskId"]

    def _insufficient_judge(self, call_count_list):
        call_count_list.append(True)
        if len(call_count_list) == 1:
            return {
                "verdict": "INCORRECT", "judgeScore": 20,
                "coverage": {"score": 0.1, "matchedAspects": 0, "totalAspects": 2, "evidenceCount": 1, "sourceTypes": ["current_paper"]},
                "missingAspects": ["消融实验"], "retryReason": "", "shouldRetry": False,
            }
        if len(call_count_list) == 2:
            return {
                "verdict": "INCORRECT", "judgeScore": 30,
                "coverage": {"score": 0.2, "matchedAspects": 0, "totalAspects": 2, "evidenceCount": 2, "sourceTypes": ["current_paper", "library"]},
                "missingAspects": ["消融实验", "关键指标"], "retryReason": "", "shouldRetry": False,
            }
        return {
            "verdict": "CORRECT", "judgeScore": 85,
            "coverage": {"score": 0.85, "matchedAspects": 2, "totalAspects": 2, "evidenceCount": 4, "sourceTypes": ["current_paper", "library", "external_academic"]},
            "missingAspects": [], "retryReason": "", "shouldRetry": False,
        }

    def test_external_search_disabled_by_default_no_change(self):
        task_id = self._create_task()
        judge_calls = []
        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
            patch.object(research_executor, "retrieve_current_paper_evidence", return_value=[{"sourceId": "cp-1", "text": "paper evidence", "sourceType": "current_paper"}]),
            patch.object(research_executor, "retrieve_library_evidence", return_value=[{"sourceId": "lib-1", "text": "library evidence", "sourceType": "library"}]),
            patch.object(research_executor, "judge_research_evidence", side_effect=lambda q, e, **kw: self._insufficient_judge(judge_calls)),
            patch.object(research_executor, "retrieve_external_academic_evidence", return_value={"status": "disabled", "items": [], "degradation": "disabled"}),
        ):
            task = research_task_service.run_research_task_now(task_id)

        finding = task["findings"][0]
        self.assertEqual(finding.get("externalSearchDegradation"), "disabled")
        self.assertEqual(finding["verdict"], "INCORRECT")
        source_ids = finding.get("sourceIds") or []
        self.assertNotIn("external-doi-", "\n".join(source_ids))
        self.assertEqual(task["status"], "awaiting_final_review")

    def test_external_search_with_success_adds_evidence_and_rejudges(self):
        task_id = self._create_task()
        judge_calls = []
        external_items = [
            {"sourceId": "external-doi-abc123", "text": "external ablation study results",
             "sourceType": "external_academic", "title": "Ablation Study X", "year": 2024},
        ]
        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
            patch.object(research_executor, "retrieve_current_paper_evidence", return_value=[{"sourceId": "cp-1", "text": "paper evidence", "sourceType": "current_paper"}]),
            patch.object(research_executor, "retrieve_library_evidence", return_value=[{"sourceId": "lib-1", "text": "library evidence", "sourceType": "library"}]),
            patch.object(research_executor, "judge_research_evidence", side_effect=lambda q, e, **kw: self._insufficient_judge(judge_calls)),
            patch.object(research_executor, "retrieve_external_academic_evidence", return_value={"status": "success", "items": external_items, "degradation": ""}),
        ):
            task = research_task_service.run_research_task_now(task_id)

        finding = task["findings"][0]
        self.assertEqual(finding.get("externalSearchDegradation") or "", "")
        self.assertEqual(finding["verdict"], "CORRECT")
        source_ids = finding.get("sourceIds") or []
        self.assertIn("external-doi-abc123", source_ids)
        self.assertIn("外部学术检索", task["report"])

    def test_external_search_budget_exceeded_degrades_gracefully(self):
        task_id = self._create_task()
        judge_calls = []
        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
            patch.object(research_executor, "retrieve_current_paper_evidence", return_value=[{"sourceId": "cp-1", "text": "paper evidence", "sourceType": "current_paper"}]),
            patch.object(research_executor, "retrieve_library_evidence", return_value=[{"sourceId": "lib-1", "text": "library evidence", "sourceType": "library"}]),
            patch.object(research_executor, "judge_research_evidence", side_effect=lambda q, e, **kw: self._insufficient_judge(judge_calls)),
            patch.object(research_executor, "retrieve_external_academic_evidence", return_value={"status": "budget_exceeded", "items": [], "degradation": "External academic search call budget exceeded."}),
        ):
            task = research_task_service.run_research_task_now(task_id)

        finding = task["findings"][0]
        self.assertEqual(finding["externalSearchDegradation"], "External academic search call budget exceeded.")
        self.assertEqual(finding["verdict"], "INCORRECT")
        self.assertEqual(task["status"], "awaiting_final_review")
        self.assertIn("外部检索降级", task["report"])

    def test_external_search_provider_failure_degrades_gracefully(self):
        task_id = self._create_task()
        judge_calls = []
        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
            patch.object(research_executor, "retrieve_current_paper_evidence", return_value=[{"sourceId": "cp-1", "text": "paper evidence", "sourceType": "current_paper"}]),
            patch.object(research_executor, "retrieve_library_evidence", return_value=[{"sourceId": "lib-1", "text": "library evidence", "sourceType": "library"}]),
            patch.object(research_executor, "judge_research_evidence", side_effect=lambda q, e, **kw: self._insufficient_judge(judge_calls)),
            patch.object(research_executor, "retrieve_external_academic_evidence", return_value={"status": "failed", "items": [], "degradation": "External academic provider failed."}),
        ):
            task = research_task_service.run_research_task_now(task_id)

        finding = task["findings"][0]
        self.assertEqual(finding["externalSearchDegradation"], "External academic provider failed.")
        self.assertEqual(finding["verdict"], "INCORRECT")
        self.assertEqual(task["status"], "awaiting_final_review")

    def test_external_tool_failure_reason_cannot_leak_credentials(self):
        secret = ADVERSARIAL_FIXTURE["secretToken"]
        with patch.object(
            research_executor,
            "invoke_tool",
            return_value={
                "status": "failed",
                "provider": "crossref",
                "items": [],
                "reason": f"provider response contained credential {secret}",
            },
        ):
            result = research_executor.retrieve_external_academic_evidence(
                research_question="retrieval robustness",
                sub_question="compare methods",
                missing_aspects=["adversarial evaluation"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["degradation"], "External academic provider failed.")
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_external_evidence_participates_in_conflict_detection(self):
        task_id = self._create_task()
        judge_calls = []
        external_items = [
            {"sourceId": "external-doi-abc", "text": "accuracy 91.2% on benchmark",
             "sourceType": "external_academic", "title": "External Paper A", "year": 2024},
        ]

        def fake_judge(_q, evidence, **_kw):
            judge_calls.append(True)
            if len(judge_calls) == 1:
                return {"verdict": "INCORRECT", "judgeScore": 25, "coverage": {}, "missingAspects": ["消融实验"], "retryReason": "", "shouldRetry": False}
            if len(judge_calls) == 2:
                return {"verdict": "INCORRECT", "judgeScore": 30, "coverage": {}, "missingAspects": ["消融实验"], "retryReason": "", "shouldRetry": False}
            return {"verdict": "CORRECT", "judgeScore": 85, "coverage": {}, "missingAspects": [], "retryReason": "", "shouldRetry": False}

        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper accuracy 87.5% on benchmark"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
            patch.object(research_executor, "retrieve_current_paper_evidence", return_value=[{"sourceId": "cp-1", "text": "paper accuracy 87.5% on benchmark", "sourceType": "current_paper"}]),
            patch.object(research_executor, "retrieve_library_evidence", return_value=[{"sourceId": "lib-1", "text": "library result", "sourceType": "library"}]),
            patch.object(research_executor, "judge_research_evidence", side_effect=fake_judge),
            patch.object(research_executor, "retrieve_external_academic_evidence", return_value={"status": "success", "items": external_items, "degradation": ""}),
        ):
            task = research_task_service.run_research_task_now(task_id)

        conflicts = task.get("conflicts") or []
        self.assertGreater(len(conflicts), 0)
        conflict_source_ids = "\n".join(
            str(sid) for conflict in conflicts for sid in (conflict.get("sourceIds") or [])
        )
        self.assertIn("external-doi-abc", conflict_source_ids)

    def test_correct_verdict_skips_external_search(self):
        task_id = self._create_task()
        judge_calls = []

        def fake_judge_correct(_q, _evidence, **_kw):
            judge_calls.append(True)
            return {"verdict": "CORRECT", "judgeScore": 90, "coverage": {}, "missingAspects": [], "retryReason": "", "shouldRetry": False}

        external_called = []
        with (
            patch.object(research_task_service, "_load_current_paper_documents", return_value=([{"sourceId": "doc-1", "text": "paper evidence"}], "paper-1")),
            patch.object(research_task_service, "_build_research_plan", return_value=("brief", ["子问题一"])),
            patch.object(research_executor, "retrieve_current_paper_evidence", return_value=[{"sourceId": "cp-1", "text": "paper evidence", "sourceType": "current_paper"}]),
            patch.object(research_executor, "retrieve_library_evidence", return_value=[{"sourceId": "lib-1", "text": "library evidence", "sourceType": "library"}]),
            patch.object(research_executor, "judge_research_evidence", side_effect=fake_judge_correct),
            patch.object(research_executor, "retrieve_external_academic_evidence", side_effect=lambda **kw: external_called.append(True) or {"status": "success", "items": [], "degradation": ""}),
        ):
            task = research_task_service.run_research_task_now(task_id)

        self.assertEqual(len(external_called), 0)
        finding = task["findings"][0]
        self.assertEqual(finding.get("externalSearchDegradation") or "", "")


    def test_external_search_config_survives_sqlite_roundtrip(self):
        task_id = self._create_task(allow_external_search=True)
        task_before = research_task_service.get_research_task(task_id)["task"]
        config_before = task_before.get("externalSearchConfig") or {}
        self.assertTrue(config_before.get("allowExternalSearch"))
        self.assertEqual(config_before.get("provider"), "disabled")
        self.assertEqual(config_before.get("budget", {}).get("callLimit"), 3)
        self.assertEqual(config_before.get("status"), "disabled")

        research_task_service.reload_research_tasks_from_storage()
        task_after = research_task_service.get_research_task(task_id)["task"]
        config_after = task_after.get("externalSearchConfig") or {}
        self.assertTrue(config_after.get("allowExternalSearch"))
        self.assertEqual(config_after.get("budget"), config_before.get("budget"))

    def test_legacy_research_snapshot_without_external_search_config_loads(self):
        task_id = self._create_task()
        research_task_service._update_task_snapshot(task_id, externalSearchConfig={"allowExternalSearch": True, "provider": "crossref", "budget": {"callLimit": 3, "evidenceLimit": 15, "callsUsed": 2, "evidenceUsed": 10}, "status": "success", "degradation": ""})
        task_before = research_task_service.get_research_task(task_id)["task"]
        self.assertEqual(task_before["externalSearchConfig"]["provider"], "crossref")

        research_task_service.reload_research_tasks_from_storage()
        task_after = research_task_service.get_research_task(task_id)["task"]
        self.assertEqual(task_after["externalSearchConfig"]["provider"], "crossref")
        self.assertEqual(task_after["externalSearchConfig"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
