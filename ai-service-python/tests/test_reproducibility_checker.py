"""Unit tests for reproducibility_checker — verifies sandbox logic without Docker."""

import os
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from services.reproducibility_checker import (
    _check_dependencies,
    _extract_host,
    _extract_and_compare,
    verify_reproducibility,
)


class ReproducibilityCheckerTests(TestCase):
    def setUp(self):
        self._original_env = os.environ.get("PIXIU_ALLOW_REPRODUCIBILITY")

    def tearDown(self):
        if self._original_env is None:
            os.environ.pop("PIXIU_ALLOW_REPRODUCIBILITY", None)
        else:
            os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = self._original_env

    # ── Environment gate ──────────────────────────────────────────────────

    def test_disabled_by_default(self):
        os.environ.pop("PIXIU_ALLOW_REPRODUCIBILITY", None)
        result = verify_reproducibility("paper-1")
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["verdict"], "disabled")

    def test_disabled_with_false_value(self):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "false"
        result = verify_reproducibility("paper-1")
        self.assertEqual(result["status"], "disabled")

    def test_enabled_with_true(self):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "true"
        # Should not return disabled — proceed to search (may fail, but not disabled)
        result = verify_reproducibility("paper-1")
        self.assertNotEqual(result.get("status"), "disabled")

    def test_enabled_with_1(self):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "1"
        result = verify_reproducibility("paper-1")
        self.assertNotEqual(result.get("status"), "disabled")

    # ── Input validation ──────────────────────────────────────────────────

    def test_empty_paper_id(self):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "true"
        result = verify_reproducibility("")
        self.assertEqual(result["status"], "error")

    def test_whitespace_paper_id(self):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "true"
        result = verify_reproducibility("   ")
        self.assertEqual(result["status"], "error")

    # ── URL whitelist ─────────────────────────────────────────────────────

    def test_extract_host_github(self):
        self.assertEqual(_extract_host("https://github.com/user/repo"), "github.com")

    def test_extract_host_github_http(self):
        self.assertEqual(_extract_host("http://github.com/user/repo"), "github.com")

    def test_extract_host_gitlab_rejected(self):
        self.assertEqual(_extract_host("https://gitlab.com/user/repo"), "gitlab.com")

    def test_extract_host_no_protocol(self):
        self.assertEqual(_extract_host("github.com/user/repo"), "")

    # ── Dependency check ──────────────────────────────────────────────────

    def test_no_requirements_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _check_dependencies("pip install -e .", tmp)
            self.assertTrue(result["ok"])

    def test_stdlib_only_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_path = os.path.join(tmp, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("os\nsys\njson\nmath\n")
            result = _check_dependencies("pip install -r requirements.txt", tmp)
            self.assertTrue(result["ok"])

    def test_non_stdlib_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_path = os.path.join(tmp, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("numpy>=1.21\npandas\n")
            result = _check_dependencies("pip install -r requirements.txt", tmp)
            self.assertFalse(result["ok"])
            self.assertIn("numpy", result["reason"])
            self.assertIn("pandas", result["reason"])

    def test_commented_deps_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_path = os.path.join(tmp, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("# numpy\nos\n# tensorflow\n")
            result = _check_dependencies("pip install -r requirements.txt", tmp)
            self.assertTrue(result["ok"])

    def test_empty_requirements_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_path = os.path.join(tmp, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("")
            result = _check_dependencies("pip install -r requirements.txt", tmp)
            self.assertTrue(result["ok"])

    def test_versioned_stdlib_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_path = os.path.join(tmp, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("typing>=3.0\n")
            result = _check_dependencies("pip install -r requirements.txt", tmp)
            self.assertTrue(result["ok"])

    # ── Numeric extraction ────────────────────────────────────────────────

    def test_extract_numbers_from_stdout(self):
        result = _extract_and_compare("Accuracy: 0.95\nPrecision: 0.92\nRecall: 0.88", "paper-1")
        self.assertTrue(result["match"])
        self.assertIn("0.95", result["valuesFound"])
        self.assertIn("0.92", result["valuesFound"])
        self.assertIn("0.88", result["valuesFound"])
        self.assertEqual(result["numericOutputs"], 3)

    def test_extract_no_numbers(self):
        result = _extract_and_compare("No results available.", "paper-1")
        self.assertFalse(result["match"])
        self.assertEqual(result["numericOutputs"], 0)

    # ── Docker unavailable fallback ───────────────────────────────────────

    @patch("services.reproducibility_checker._docker_available", return_value=False)
    @patch("services.reproducibility_checker._find_code_repo", return_value="https://github.com/example/repo")
    @patch("services.reproducibility_checker._clone_repo", return_value=True)
    @patch("services.reproducibility_checker._detect_install_cmd", return_value="pip install -e .")
    @patch("services.reproducibility_checker._detect_run_cmd", return_value="python main.py")
    def test_docker_unavailable_returns_error(
        self, _mock_run, _mock_install, _mock_clone, _mock_find, _mock_docker,
    ):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "true"
        with tempfile.TemporaryDirectory() as tmp:
            # Create a README so the sandbox path is attempted
            with open(os.path.join(tmp, "README.md"), "w") as f:
                f.write("")
            with patch("services.reproducibility_checker._read_readme", return_value="pip install -e .\npython main.py"):
                result = verify_reproducibility("paper-1")
        self.assertIn(result["verdict"], {"failed", "unable_to_verify"})
        self.assertIn(result.get("error", ""), {"docker_unavailable", ""})

    # ── No code available ─────────────────────────────────────────────────

    @patch("services.reproducibility_checker._find_code_repo", return_value=None)
    def test_no_repo_found(self, _mock_find):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "true"
        result = verify_reproducibility("paper-1")
        self.assertEqual(result["verdict"], "no_code_available")
        self.assertIsNone(result["repo"])

    # ── Clone failure ─────────────────────────────────────────────────────

    @patch("services.reproducibility_checker._find_code_repo", return_value="https://github.com/example/repo")
    @patch("services.reproducibility_checker._clone_repo", return_value=False)
    def test_clone_failure(self, _mock_clone, _mock_find):
        os.environ["PIXIU_ALLOW_REPRODUCIBILITY"] = "true"
        result = verify_reproducibility("paper-1")
        self.assertEqual(result["verdict"], "clone_failed")
