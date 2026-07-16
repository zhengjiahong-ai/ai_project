"""P5-10 adversarial security tests for the Worker validation layer.

These tests verify that _validate_job() rejects malicious inputs without
requiring Docker. They test the code-level security enforcement points.
"""

import hashlib
import os
import tempfile
from pathlib import Path

from services.code_execution_models import (
    WORKER_IMAGE_DIGEST,
    approve_code_execution_job,
    create_code_execution_job,
)

from code_worker import FIXED_TEMPLATE_TEXT
from code_worker.runner import _validate_job


def _make_job(input_path, *, script_text=None, image=None, status_approved=True):
    data = input_path.read_bytes() if input_path.exists() else b"a,b\n1,2\n"
    job = create_code_execution_job(
        job_id="job-adversarial-001",
        artifact_id="artifact-001",
        artifact_digest=hashlib.sha256(data).hexdigest(),
        artifact_size_bytes=len(data),
        script_text=script_text if script_text is not None else FIXED_TEMPLATE_TEXT,
        image=image if image is not None else WORKER_IMAGE_DIGEST,
    )
    if status_approved:
        job = approve_code_execution_job(
            job, approved_by="user-001", approved_at="2026-07-10T10:00:00Z",
        )
    return job


def _write_csv(path, content):
    path.write_text(content, encoding="utf-8")
    return path


class TestWorkerValidationRejectsMaliciousInputs:
    """Verify _validate_job rejects invalid states without Docker."""

    def test_rejects_non_fixed_template_script(self, tmp_path):
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        malicious_script = "import os; os.system('rm -rf /')"
        job = _make_job(input_path, script_text=malicious_script)
        result = _validate_job(job, input_path)
        assert result is not None
        assert result.reason_code == "template_mismatch"

    def test_rejects_wrong_image_digest(self, tmp_path):
        """Model rejects non-WORKER_IMAGE_DIGEST at creation time."""
        import pytest
        from pydantic import ValidationError
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        data = input_path.read_bytes()
        with pytest.raises(ValidationError):
            create_code_execution_job(
                job_id="job-001", artifact_id="artifact-001",
                artifact_digest=hashlib.sha256(data).hexdigest(),
                artifact_size_bytes=len(data),
                script_text=FIXED_TEMPLATE_TEXT,
                image="sha256:" + "f" * 64,
            )

    def test_rejects_symlink_input(self, tmp_path):
        real_path = _write_csv(tmp_path / "real.csv", "a,b\n1,2\n")
        symlink_path = tmp_path / "link.csv"
        try:
            os.symlink(str(real_path), str(symlink_path))
        except OSError:
            import pytest
            pytest.skip("symlink creation not supported on this platform")
        data = real_path.read_bytes()
        job = create_code_execution_job(
            job_id="job-001", artifact_id="artifact-001",
            artifact_digest=hashlib.sha256(data).hexdigest(),
            artifact_size_bytes=len(data),
            script_text=FIXED_TEMPLATE_TEXT,
        )
        job = approve_code_execution_job(job, approved_by="user-001", approved_at="2026-07-10T10:00:00Z")
        result = _validate_job(job, symlink_path)
        assert result is not None
        assert result.reason_code == "input_not_regular_file"

    def test_rejects_size_mismatch(self, tmp_path):
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        actual_size = input_path.stat().st_size
        job = create_code_execution_job(
            job_id="job-001", artifact_id="artifact-001",
            artifact_digest=hashlib.sha256(input_path.read_bytes()).hexdigest(),
            artifact_size_bytes=actual_size + 100,
            script_text=FIXED_TEMPLATE_TEXT,
        )
        job = approve_code_execution_job(job, approved_by="user-001", approved_at="2026-07-10T10:00:00Z")
        result = _validate_job(job, input_path)
        assert result is not None
        assert result.reason_code == "input_size_mismatch"

    def test_rejects_digest_mismatch(self, tmp_path):
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        actual_size = input_path.stat().st_size
        job = create_code_execution_job(
            job_id="job-001", artifact_id="artifact-001",
            artifact_digest="a" * 64,
            artifact_size_bytes=actual_size,
            script_text=FIXED_TEMPLATE_TEXT,
        )
        job = approve_code_execution_job(job, approved_by="user-001", approved_at="2026-07-10T10:00:00Z")
        result = _validate_job(job, input_path)
        assert result is not None
        assert result.reason_code == "input_digest_mismatch"

    def test_rejects_unapproved_job(self, tmp_path):
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        job = _make_job(input_path, status_approved=False)
        result = _validate_job(job, input_path)
        assert result is not None
        assert result.reason_code == "job_not_approved"

    def test_rejects_script_with_import_os(self, tmp_path):
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        malicious = "import os\nimport csv\nprint('hello')\n"
        job = _make_job(input_path, script_text=malicious)
        result = _validate_job(job, input_path)
        assert result is not None
        assert result.reason_code == "template_mismatch"

    def test_rejects_script_with_eval(self, tmp_path):
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        malicious = "eval('print(1+1)')\n"
        job = _make_job(input_path, script_text=malicious)
        result = _validate_job(job, input_path)
        assert result is not None
        assert result.reason_code == "template_mismatch"

    def test_rejects_script_with_subprocess_import(self, tmp_path):
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        malicious = "import subprocess\nsubprocess.run(['ls'])\n"
        job = _make_job(input_path, script_text=malicious)
        result = _validate_job(job, input_path)
        assert result is not None
        assert result.reason_code == "template_mismatch"

    def test_rejects_empty_script(self, tmp_path):
        """Model rejects empty script_text at creation time."""
        import pytest
        from pydantic import ValidationError
        input_path = _write_csv(tmp_path / "input.csv", "a,b\n1,2\n")
        data = input_path.read_bytes()
        with pytest.raises(ValidationError):
            create_code_execution_job(
                job_id="job-001", artifact_id="artifact-001",
                artifact_digest=hashlib.sha256(data).hexdigest(),
                artifact_size_bytes=len(data),
                script_text="",
            )


class TestFormulaInjectionTreatedAsData:
    """Verify CSV formula prefixes are not evaluated by the fixed template."""

    def test_formula_prefix_equals_is_data(self, tmp_path):
        from code_worker.fixed_template import analyze_csv
        import json

        input_path = tmp_path / "formula.csv"
        input_path.write_text("col_a\n=cmd|'calc'!A0\n=IMPORTANT\n=2+2\n", encoding="utf-8")
        output_path = tmp_path / "out.json"
        analyze_csv(input_path, output_path)
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["rowCount"] == 3
        assert payload["columns"]["col_a"]["numericCount"] == 0
        assert payload["columns"]["col_a"]["missingCount"] == 0

    def test_formula_prefix_plus_minus_at_is_data(self, tmp_path):
        from code_worker.fixed_template import analyze_csv
        import json

        input_path = tmp_path / "formula2.csv"
        input_path.write_text("col_b\n+launch\n-shutdown\n\"@SUM(1,2)\"\n42\n", encoding="utf-8")
        output_path = tmp_path / "out2.json"
        analyze_csv(input_path, output_path)
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["rowCount"] == 4
        assert payload["columns"]["col_b"]["numericCount"] == 1
        assert payload["columns"]["col_b"]["mean"] == 42.0


class TestPathTraversalTreatedAsData:
    """Verify path-like strings in CSV are not traversed."""

    def test_path_traversal_in_csv_is_data(self, tmp_path):
        from code_worker.fixed_template import analyze_csv
        import json

        input_path = tmp_path / "paths.csv"
        input_path.write_text(
            "filename,size\n"
            "../../../etc/passwd,100\n"
            "/etc/shadow,200\n"
            "C:\\Windows\\System32,300\n"
            "normal_file.csv,50\n",
            encoding="utf-8",
        )
        output_path = tmp_path / "out.json"
        analyze_csv(input_path, output_path)
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["rowCount"] == 4
        assert payload["columns"]["filename"]["numericCount"] == 0
        assert payload["columns"]["size"]["numericCount"] == 4
