import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from schemas.requests import ResearchTaskCreateRequest
from services import research_task_service, trace_service


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
        self.assertIn("## 证据冲突/需人工核查", task["report"])
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
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["responseMeta"]["taskId"], task["taskId"])
        self.assertEqual(summary["responseMeta"]["findingCount"], 3)
        self.assertGreaterEqual(len(summary["steps"]), 1)

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
        self.assertEqual(response["trace"]["status"], "success")

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


if __name__ == "__main__":
    unittest.main()
