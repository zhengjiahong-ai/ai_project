import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.code_sandbox.benchmark import (
    REQUIRED_PROBES,
    build_benchmark_result,
    sanitize_environment,
)
from benchmarks.code_sandbox.runner import _command_version, _docker_cleanup, existing_image_id, copy_windows_input, terminate_job_process


def _candidate(name="docker", *, failed_probe=None):
    probes = {
        probe: {"status": "passed", "durationMs": 10, "detail": "bounded"}
        for probe in REQUIRED_PROBES
    }
    if failed_probe:
        probes[failed_probe] = {
            "status": "failed",
            "durationMs": 10,
            "detail": "blocked requirement not satisfied",
        }
    return {
        "name": name,
        "available": True,
        "runtime": "docker" if name == "docker" else "windows_job_object",
        "probes": probes,
        "cleanup": {"status": "passed", "residualCount": 0},
    }


class CodeSandboxScoringTests(unittest.TestCase):
    def test_all_required_docker_probes_allow_only_p5_03_planning(self):
        result = build_benchmark_result(
            environment={"os": "Windows", "python": "3.13.9"},
            candidates=[_candidate("docker"), _candidate("windows_job_object", failed_probe="network")],
        )

        self.assertEqual(result["schemaVersion"], "1.0")
        self.assertEqual(result["decision"]["status"], "continue_to_p5_03")
        self.assertEqual(result["decision"]["selectedCandidate"], "docker")
        self.assertFalse(result["decision"]["productionAuthorized"])
        self.assertTrue(result["candidates"]["docker"]["eligible"])
        self.assertFalse(result["candidates"]["windows_job_object"]["eligible"])

    def test_any_required_docker_failure_stops_p5(self):
        result = build_benchmark_result(
            environment={},
            candidates=[_candidate("docker", failed_probe="read_only_input")],
        )

        self.assertEqual(result["decision"]["status"], "stop_p5")
        self.assertIsNone(result["decision"]["selectedCandidate"])

    def test_missing_docker_is_a_closed_failure(self):
        result = build_benchmark_result(
            environment={},
            candidates=[{
                "name": "docker",
                "available": False,
                "runtime": "docker",
                "reasonCode": "docker_unavailable",
                "probes": {},
                "cleanup": {"status": "not_run", "residualCount": 0},
            }],
        )

        docker = result["candidates"]["docker"]
        self.assertFalse(docker["eligible"])
        self.assertEqual(docker["failedRequirements"], list(REQUIRED_PROBES))
        self.assertEqual(result["decision"]["status"], "stop_p5")

    def test_environment_and_result_are_sanitized(self):
        environment = sanitize_environment({
            "os": "Windows 11",
            "python": "3.13.9",
            "dockerEngine": "27.5.1",
            "imageDigest": "sha256:" + "a" * 64,
            "cwd": "C:\\Users\\alice\\secret-project",
            "apiKey": "super-secret",
        })
        result = build_benchmark_result(environment=environment, candidates=[_candidate("docker")])
        serialized = json.dumps(result)

        self.assertEqual(set(environment), {"os", "python", "dockerEngine", "imageDigest"})
        self.assertNotIn("alice", serialized)
        self.assertNotIn("super-secret", serialized)


class _Pipe:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _Process:
    def __init__(self):
        self.stdout = _Pipe()
        self.stderr = _Pipe()
        self.killed = False
        self.waited = False

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        self.waited = timeout == 2


class _Kernel32:
    def __init__(self):
        self.terminated = False

    def TerminateJobObject(self, job, code):
        self.terminated = (job, code) == (7, 1)
        return 1


class CodeSandboxProcessCleanupTests(unittest.TestCase):
    @patch("benchmarks.code_sandbox.runner.subprocess.run")
    def test_docker_cleanup_timeout_is_a_failed_requirement_not_an_exception(self, run):
        run.side_effect = subprocess.TimeoutExpired(["docker", "ps"], 15)

        self.assertEqual(_docker_cleanup(), {"status": "failed", "residualCount": -1})

    @patch("benchmarks.code_sandbox.runner._command_version")
    def test_existing_benchmark_image_is_reused_by_immutable_id(self, version):
        version.return_value = "sha256:" + "a" * 64

        self.assertEqual(existing_image_id("pixiu-code-sandbox-benchmark:p5-02"), version.return_value)
        version.assert_called_once_with("docker", ["image", "inspect", "pixiu-code-sandbox-benchmark:p5-02", "--format", "{{.Id}}"])

    def test_windows_probe_uses_a_temporary_copy_of_the_tracked_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.csv"
            target_directory = Path(temp) / "job"
            source.write_text("name,value\nalpha,1\n", encoding="utf-8")

            copied = copy_windows_input(source, target_directory)
            copied.write_text("mutated", encoding="utf-8")

            self.assertEqual(source.read_text(encoding="utf-8"), "name,value\nalpha,1\n")
            self.assertEqual(copied.parent, target_directory)

    @patch("benchmarks.code_sandbox.runner.subprocess.run")
    def test_docker_version_timeout_is_reported_as_unavailable(self, run):
        run.side_effect = subprocess.TimeoutExpired(["docker", "version"], 5)

        self.assertEqual(_command_version("docker", ["version"]), "")

    def test_timeout_cleanup_closes_flooded_pipes_without_second_communicate(self):
        process = _Process()
        kernel32 = _Kernel32()

        terminate_job_process(process, kernel32, 7)

        self.assertTrue(kernel32.terminated)
        self.assertTrue(process.killed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)
        self.assertTrue(process.waited)


if __name__ == "__main__":
    unittest.main()
