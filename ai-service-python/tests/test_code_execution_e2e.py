"""P5-11 end-to-end verification tests for the code execution lifecycle.

These tests verify the full lifecycle (proposal → approval → execution →
publication → audit) using a mock Worker runner. No Docker required.
"""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from code_worker.models import WorkerOutput, WorkerResult
from services import code_execution_service
from services.code_execution_store import (
    list_code_execution_audit_events,
)


def _mock_success_runner(job, input_path):
    """Mock Worker that returns a successful descriptive statistics result."""
    stats = {
        "schemaVersion": "1.0",
        "rowCount": 9,
        "columns": {
            "group": {"missingCount": 0, "numericCount": 0},
            "score": {"missingCount": 0, "numericCount": 9, "min": 68.0,
                       "max": 95.0, "mean": 81.66666666666667, "median": 82.0},
        },
    }
    output_dir = Path(tempfile.mkdtemp(prefix="mock-worker-output-"))
    output_file = output_dir / "statistics.json"
    output_file.write_text(json.dumps(stats), encoding="utf-8")
    digest = hashlib.sha256(output_file.read_bytes()).hexdigest()
    return WorkerResult(
        status="succeeded", reasonCode="completed", exitCode=0,
        outputs=[WorkerOutput(name="statistics", mediaType="application/json",
                               sizeBytes=output_file.stat().st_size, digest=digest)],
    )


def _mock_failure_runner(job, input_path):
    return WorkerResult(status="failed", reasonCode="container_failed", exitCode=1, outputs=[])


def _mock_timeout_runner(job, input_path):
    return WorkerResult(status="failed", reasonCode="wall_clock_limit_exceeded", exitCode=None, outputs=[])


class TestCodeExecutionE2ELifecycle(unittest.TestCase):
    """Full lifecycle tests using mock Worker (no Docker needed)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["CODE_EXECUTION_ARTIFACT_DIR"] = str(
            Path(self.temp_dir.name) / "artifacts"
        )
        self._prev_db = os.environ.get("CODE_EXECUTION_DB_PATH")
        os.environ["CODE_EXECUTION_DB_PATH"] = str(
            Path(self.temp_dir.name) / "code_execution.sqlite3"
        )

    def tearDown(self):
        self.temp_dir.cleanup()
        if self._prev_db is None:
            os.environ.pop("CODE_EXECUTION_DB_PATH", None)
        else:
            os.environ["CODE_EXECUTION_DB_PATH"] = self._prev_db
        os.environ.pop("CODE_EXECUTION_ARTIFACT_DIR", None)

    def _stage_artifact(self, content="group,score\nA,85\nA,92\nB,78\n"):
        return code_execution_service.stage_csv_artifact("test.csv", content.encode("utf-8"))

    def test_full_lifecycle_proposal_to_publication(self):
        """artifact → create_job → approve → execute(mock) → publish → result."""
        artifact = self._stage_artifact()
        job_result = code_execution_service.create_job(artifact["artifactId"])
        self.assertEqual(job_result["status"], "success")
        job = job_result["job"]
        self.assertEqual(job["status"], "awaiting_approval")
        self.assertFalse(job.get("publishable"))

        approved = code_execution_service.review_execution(
            job["jobId"], "approved", job["taskDigest"], runner=_mock_success_runner,
        )
        self.assertEqual(approved["status"], "success")
        self.assertEqual(approved["job"]["status"], "succeeded")
        self.assertFalse(approved["job"].get("publishable"))

        published = code_execution_service.review_publication(
            job["jobId"], "approved", approved["job"]["publicationDigest"],
        )
        self.assertEqual(published["status"], "success")
        self.assertTrue(published["job"].get("publishable"))

        events = list_code_execution_audit_events(job["jobId"])
        event_types = [e["eventType"] for e in events]
        self.assertIn("job_created", event_types)
        self.assertIn("job_approved", event_types)
        self.assertIn("execution_started", event_types)
        self.assertIn("execution_finished", event_types)
        self.assertIn("publication_approved", event_types)

    def test_job_cancellation_via_rejection(self):
        """Rejection is terminal and preserves audit."""
        artifact = self._stage_artifact()
        job_result = code_execution_service.create_job(artifact["artifactId"])
        job = job_result["job"]

        rejected = code_execution_service.review_execution(
            job["jobId"], "rejected", job["taskDigest"], reason="Not needed.",
        )
        self.assertEqual(rejected["status"], "success")
        self.assertEqual(rejected["job"]["status"], "rejected")
        self.assertFalse(rejected["job"].get("publishable"))

        events = list_code_execution_audit_events(job["jobId"])
        event_types = [e["eventType"] for e in events]
        self.assertIn("job_rejected", event_types)

    def test_job_timeout_handling(self):
        """Timeout produces a stable failed result."""
        artifact = self._stage_artifact()
        job_result = code_execution_service.create_job(artifact["artifactId"])
        job = job_result["job"]

        result = code_execution_service.review_execution(
            job["jobId"], "approved", job["taskDigest"], runner=_mock_timeout_runner,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["job"]["status"], "failed")
        self.assertEqual(result["job"]["executionResult"]["reasonCode"], "wall_clock_limit_exceeded")

    def test_publication_approval_required_before_publishable(self):
        """Publication must be approved for publishable to be True."""
        artifact = self._stage_artifact()
        job_result = code_execution_service.create_job(artifact["artifactId"])
        job = job_result["job"]

        approved = code_execution_service.review_execution(
            job["jobId"], "approved", job["taskDigest"], runner=_mock_success_runner,
        )
        self.assertEqual(approved["job"]["status"], "succeeded")
        self.assertFalse(approved["job"].get("publishable"))

        published = code_execution_service.review_publication(
            job["jobId"], "approved", approved["job"]["publicationDigest"],
        )
        self.assertTrue(published["job"].get("publishable"))

    def test_dual_approval_digest_binding(self):
        """Stale taskDigest causes 409 conflict on execution review."""
        artifact = self._stage_artifact()
        job_result = code_execution_service.create_job(artifact["artifactId"])
        job = job_result["job"]

        from services.code_execution_service import ReviewConflictError
        with self.assertRaises(ReviewConflictError):
            code_execution_service.review_execution(
                job["jobId"], "approved", "0" * 64, runner=_mock_success_runner,
            )

    def test_failed_execution_cannot_enter_publication(self):
        """Failed execution cannot be published."""
        artifact = self._stage_artifact()
        job_result = code_execution_service.create_job(artifact["artifactId"])
        job = job_result["job"]

        code_execution_service.review_execution(
            job["jobId"], "approved", job["taskDigest"], runner=_mock_failure_runner,
        )

        from services.code_execution_service import ReviewConflictError
        with self.assertRaises(ReviewConflictError):
            code_execution_service.review_publication(
                job["jobId"], "approved",
                hashlib.sha256(b"fake").hexdigest(),
            )

    def test_audit_events_exclude_script_text(self):
        """Audit events must not contain the raw script text."""
        artifact = self._stage_artifact()
        job_result = code_execution_service.create_job(artifact["artifactId"])
        job = job_result["job"]

        code_execution_service.review_execution(
            job["jobId"], "approved", job["taskDigest"], runner=_mock_success_runner,
        )

        events = list_code_execution_audit_events(job["jobId"])
        serialized = json.dumps(events, ensure_ascii=False)
        self.assertNotIn("def analyze_csv", serialized)
        self.assertNotIn("csv.DictReader", serialized)
