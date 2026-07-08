import unittest

from services.agent_review_service import (
    build_final_review_packet,
    build_plan_review_packet,
)


class AgentReviewServiceTests(unittest.TestCase):
    def test_build_plan_review_packet_carries_external_search_request(self):
        packet = build_plan_review_packet(
            run={"runId": "run-1"},
            plan_items=[{"id": "evidence", "label": "Collect claim-level evidence"}],
            focused_paper_ids=["paper-a"],
            constraints="Only compare methods.",
            allow_external_search=True,
        )

        self.assertEqual(packet["runId"], "run-1")
        self.assertEqual(packet["status"], "pending")
        self.assertTrue(packet["externalSearchRequest"]["allowed"])
        self.assertEqual(packet["focusedPaperIds"], ["paper-a"])

    def test_build_final_review_packet_derives_risk_items_from_artifacts(self):
        artifacts = {
            "conflicts": [
                {
                    "id": "conflict-1",
                    "summary": "Method conflict",
                    "severity": "medium",
                }
            ],
            "openQuestions": ["Need stronger evidence for paper-b."],
            "draftReport": "# Draft",
        }

        packet = build_final_review_packet(
            run={"runId": "run-2"},
            artifacts=artifacts,
        )

        self.assertEqual(packet["runId"], "run-2")
        self.assertEqual(packet["status"], "pending")
        self.assertEqual(len(packet["riskItems"]), 2)
