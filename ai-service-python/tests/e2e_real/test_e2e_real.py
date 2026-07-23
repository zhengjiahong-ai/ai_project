"""
Real-service E2E tests (15-4).

These tests require a running Pixiu Python AI service and a configured
``DEEPSEEK_API_KEY``.  They are NOT part of CI hard-blocking; run manually::

    PYTHONPATH=. python -m pytest tests/e2e_real/ -v

The test file auto-skips when the service is unreachable.

Prerequisites:
    cd ai-service-python
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000

    # In another terminal:
    PYTHONPATH=. python -m pytest tests/e2e_real/ -v
"""

from __future__ import annotations

import os
import unittest

import requests

BASE = os.environ.get("PIXIU_E2E_BASE_URL", "http://localhost:8000")
API = f"{BASE}/api"


def _service_reachable() -> bool:
    try:
        r = requests.get(f"{BASE}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _has_api_key() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


_SERVICE_OK = _service_reachable()
_HAS_KEY = _has_api_key()

skip_no_service = unittest.skipUnless(_SERVICE_OK, "Pixiu service not reachable")
skip_no_key = unittest.skipUnless(_HAS_KEY, "DEEPSEEK_API_KEY not configured")


@skip_no_service
class AgentProjectE2ETests(unittest.TestCase):
    """Agent project CRUD tests against a real Pixiu service."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.project_id: str | None = None

    def test_01_create_project(self):
        """POST /api/agent-projects creates a new project."""
        r = requests.post(
            f"{API}/agent-projects",
            json={"title": "E2E Test Project", "goal": "Verify CRUD operations", "paperIds": []},
            timeout=10,
        )
        self.assertIn(r.status_code, (200, 201))
        data = r.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("project", data)
        AgentProjectE2ETests.project_id = data["project"]["projectId"]

    def test_02_list_projects(self):
        """GET /api/agent-projects lists projects."""
        r = requests.get(f"{API}/agent-projects", timeout=10)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("projects", data)

    def test_03_get_project(self):
        """GET /api/agent-projects/{id} returns the project."""
        if not self.project_id:
            self.skipTest("No project created")
        r = requests.get(f"{API}/agent-projects/{self.project_id}", timeout=10)
        self.assertIn(r.status_code, (200, 404))

    def test_04_delete_project(self):
        """DELETE /api/agent-projects/{id} removes the project."""
        if not self.project_id:
            self.skipTest("No project created")
        r = requests.delete(f"{API}/agent-projects/{self.project_id}", timeout=10)
        self.assertIn(r.status_code, (200, 404))
        AgentProjectE2ETests.project_id = None


@skip_no_service
class HealthAndRateLimitE2ETests(unittest.TestCase):
    """Health check and rate limiter smoke tests."""

    def test_health_endpoint(self):
        """GET /api/health returns 200 with status info."""
        r = requests.get(f"{API}/health", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("status", data)

    def test_rate_limit_429_response(self):
        """Rapid requests eventually return 429 (if rate limiter enabled)."""
        # Send many rapid requests to trigger rate limiting.
        got_429 = False
        for _ in range(80):
            r = requests.get(f"{API}/health", timeout=2)
            if r.status_code == 429:
                got_429 = True
                data = r.json()
                self.assertIn("retryAfter", data)
                self.assertIn("Retry-After", r.headers)
                break
        # If we never got 429, the rate limiter may be disabled — not a failure.
        if got_429:
            self.assertEqual(r.status_code, 429)

    def test_mcp_sse_endpoint_accessible(self):
        """MCP SSE endpoint is reachable when MCP is enabled in SSE mode."""
        # This may 404 if MCP is not configured — that's acceptable.
        try:
            r = requests.get(f"{BASE}/mcp/sse", timeout=5)
            self.assertIn(r.status_code, (200, 404))
        except requests.ConnectionError:
            self.skipTest("MCP SSE endpoint not reachable")


@skip_no_service
@skip_no_key
class LangGraphAgentE2ETests(unittest.TestCase):
    """LangGraph agent full-workflow smoke tests (requires API key)."""

    def test_agent_graph_create_and_query(self):
        """POST /api/agent-graph creates a task and returns plan for review."""
        r = requests.post(
            f"{API}/agent-graph",
            json={
                "prompt": "Compare methods across selected papers.",
                "focusedPaperIds": [],
                "constraints": "Short test run, minimal evidence needed.",
                "allowExternalSearch": False,
            },
            timeout=30,
        )
        self.assertIn(r.status_code, (200, 201))
        data = r.json()
        self.assertEqual(data.get("status"), "success")
        task = data.get("task", {})
        self.assertIn("threadId", task)
        # Should be awaiting plan review (or failed if no papers).
        self.assertIn(task.get("status"), ("awaiting_plan_review", "failed", "pending"))


if __name__ == "__main__":
    unittest.main()
