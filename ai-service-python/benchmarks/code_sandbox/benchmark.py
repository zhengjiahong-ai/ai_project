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
    "cleanup",
)
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
    return {
        **candidate,
        "eligible": bool(candidate.get("available")) and not failed,
        "failedRequirements": failed,
    }


def build_benchmark_result(environment, candidates, generated_at=None):
    scored = {item["name"]: _score_candidate(item) for item in candidates}
    docker = scored.get("docker") or {}
    docker_passed = docker.get("eligible") is True
    return {
        "schemaVersion": "1.0",
        "generatedAt": generated_at or _utc_now(),
        "environment": sanitize_environment(environment),
        "limits": dict(LIMITS),
        "requiredProbes": list(REQUIRED_PROBES),
        "candidates": scored,
        "decision": {
            "status": "continue_to_p5_03" if docker_passed else "stop_p5",
            "selectedCandidate": "docker" if docker_passed else None,
            "productionAuthorized": False,
            "reasonCode": "docker_all_requirements_passed" if docker_passed else "no_eligible_sandbox",
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
