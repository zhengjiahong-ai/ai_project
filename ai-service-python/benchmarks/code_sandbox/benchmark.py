"""P5-02 deterministic scoring and opt-in live sandbox probes."""

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .runner import LIMITS, run_live_candidates


REQUIRED_PROBES = (
    "normal_execution",
    "adversarial_input",
    "network",
    "host_canary",
    "read_only_input",
    "temporary_output",
    "subprocess",
    "cpu_limit",
    "memory_limit",
    "stdout_limit",
    "path_traversal",
    "symlink_escape",
    "env_leak",
    "dns_resolution",
    "docker_socket",
    "fork_bomb",
    "formula_injection",
    "cleanup",
)

ADVERSARIAL_PROBES = {
    "path_traversal", "symlink_escape", "env_leak", "dns_resolution",
    "docker_socket", "fork_bomb", "formula_injection",
}
ENVIRONMENT_FIELDS = ("os", "python", "dockerEngine", "imageDigest")


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_environment(environment):
    return {
        key: str(environment[key])[:160]
        for key in ENVIRONMENT_FIELDS
        if environment.get(key)
    }


def _score_candidate(candidate):
    probes = candidate.get("probes") or {}
    failed = [
        name for name in REQUIRED_PROBES
        if (probes.get(name) or {}).get("status") != "passed"
    ]
    cleanup = candidate.get("cleanup") or {}
    if cleanup.get("status") != "passed" and "cleanup" not in failed:
        failed.append("cleanup")
    escape_vectors = [
        name for name in failed
        if name in ADVERSARIAL_PROBES
    ]
    return {
        **candidate,
        "eligible": bool(candidate.get("available")) and not failed,
        "failedRequirements": failed,
        "escapeVectorsFound": escape_vectors,
    }


def build_benchmark_result(environment, candidates, generated_at=None):
    scored = {item["name"]: _score_candidate(item) for item in candidates}
    docker = scored.get("docker") or {}
    docker_passed = docker.get("eligible") is True
    escape_vectors = docker.get("escapeVectorsFound") or []
    no_escapes = docker_passed and not escape_vectors
    return {
        "schemaVersion": "1.0",
        "generatedAt": generated_at or _utc_now(),
        "environment": sanitize_environment(environment),
        "limits": dict(LIMITS),
        "requiredProbes": list(REQUIRED_PROBES),
        "adversarialProbes": sorted(ADVERSARIAL_PROBES),
        "candidates": scored,
        "decision": {
            "status": "continue_limited" if no_escapes else ("stop_p5" if not docker_passed else "continue_to_p5_03"),
            "selectedCandidate": "docker" if docker_passed else None,
            "productionAuthorized": False,
            "reasonCode": (
                "all_probes_passed_no_escapes_limited_open" if no_escapes
                else "escape_vectors_found" if escape_vectors
                else "docker_all_requirements_passed" if docker_passed
                else "no_eligible_sandbox"
            ),
            "escapeVectorsFound": escape_vectors,
            "authorizedCapabilities": ["descriptive_statistics_on_approved_csv"] if no_escapes else [],
            "permanentlyForbidden": [
                "run_shell", "run_python", "arbitrary_code", "network_access",
                "package_install", "filesystem_write",
            ],
            "conditions": [
                "Dual human approval required before execution",
                "Dual human approval required before publication",
                "Only fixed template scripts allowed",
                "Network always disabled in sandbox",
                "All adversarial probes must pass before any demo",
            ] if no_escapes else [],
        },
    }


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="P5-02 code sandbox security benchmark")
    parser.add_argument("--live", action="store_true", help="run fixed local Docker and Windows probes")
    parser.add_argument("--output", type=Path, default=directory / "benchmark-results.json")
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("P5-02 has no synthetic mode; use --live for measured results")

    environment = {"os": platform.platform(), "python": platform.python_version()}
    candidates, runtime_environment = run_live_candidates(directory)
    environment.update(runtime_environment)
    result = build_benchmark_result(environment, candidates)
    _write_json(args.output, result)
    print(json.dumps(result["decision"], ensure_ascii=False))
    return 0 if result["decision"]["status"] == "continue_to_p5_03" else 2


if __name__ == "__main__":
    sys.exit(main())
