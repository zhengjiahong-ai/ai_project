import os
import tempfile
import unittest
from unittest.mock import patch

from schemas.requests import ResearchTaskCreateRequest
from services import research_task_service


class ResearchTaskDynamicReplanningTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("RESEARCH_TASK_DB_PATH")
        os.environ["RESEARCH_TASK_DB_PATH"] = os.path.join(self.temp_dir.name, "research_tasks.sqlite3")
        research_task_service.clear_research_tasks(clear_storage=True)

    def tearDown(self):
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


if __name__ == "__main__":
    unittest.main()
