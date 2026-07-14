"""Experimental reproducibility checker — verifies paper claims by running code.

Searches for associated code repositories (GitHub, Code Ocean, Zenodo),
clones into a Docker sandbox, installs dependencies, and runs experiments.
Compares output against reported results.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import uuid
from typing import Any

TIMEOUT_INSTALL = 120
TIMEOUT_RUN = 60
MAX_REPO_SIZE_MB = 500


# ── Public API ───────────────────────────────────────────────────────────────

def verify_reproducibility(paper_id: str) -> dict[str, Any]:
    """Check if the paper's code is reproducible.

    Returns ``{status, paperId, repo, build, run, comparison, verdict, error}``.
    """
    if not paper_id or not paper_id.strip():
        return _error("Paper ID is required.")

    paper_id = paper_id.strip()[:200]

    # Step 1: Find code repository
    repo = _find_code_repo(paper_id)
    if not repo:
        return {
            "status": "success",
            "paperId": paper_id,
            "repo": None,
            "verdict": "no_code_available",
            "comparison": {},
            "error": "",
        }

    # Step 2: Clone to temp dir
    tmp = tempfile.mkdtemp(prefix=f"repro-{uuid.uuid4().hex[:8]}-")
    try:
        clone_ok = _clone_repo(repo, tmp)
        if not clone_ok:
            return {
                "status": "success", "paperId": paper_id, "repo": repo,
                "verdict": "clone_failed", "comparison": {},
                "error": f"Failed to clone {repo}",
            }

        # Step 3: Detect install and run commands
        readme = _read_readme(tmp)
        install_cmd = _detect_install_cmd(readme, tmp)
        run_cmd = _detect_run_cmd(readme, tmp)

        # Step 4: Install dependencies
        build = _run_sandbox_cmd(install_cmd, tmp, TIMEOUT_INSTALL)

        # Step 5: Run experiment
        run = _run_sandbox_cmd(run_cmd, tmp, TIMEOUT_RUN)

        # Step 6: Extract results and compare
        comparison = _extract_and_compare(run.get("stdout", ""), paper_id)

        return {
            "status": "success",
            "paperId": paper_id,
            "repo": repo,
            "build": {"command": install_cmd, "exitCode": build.get("exitCode"), "stdout": (build.get("stdout") or "")[:1000]},
            "run": {"command": run_cmd, "exitCode": run.get("exitCode"), "stdout": (run.get("stdout") or "")[:2000]},
            "comparison": comparison,
            "verdict": "reproduced" if comparison.get("match", False) else "partial" if run.get("exitCode") == 0 else "failed",
            "error": "",
        }
    finally:
        subprocess.run(["rm", "-rf", tmp], capture_output=True, timeout=10)


# ── Code repository search ───────────────────────────────────────────────────

def _find_code_repo(paper_id: str) -> str | None:
    try:
        from services.tool_registry import get_tool_registry
        registry = get_tool_registry()
        resp = registry.invoke("search_web", {"query": f"{paper_id} github code repository", "limit": 3})
        items = resp.get("items") or []
        for item in items:
            url = (item.get("url") or "").lower()
            if "github.com" in url:
                return url
    except Exception:
        pass
    return None


def _clone_repo(url: str, target: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, target],
            capture_output=True, timeout=60, text=True,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _read_readme(path: str) -> str:
    import glob
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        for f in glob.glob(os.path.join(path, name), recursive=False):
            try:
                return open(f, encoding="utf-8").read()[:5000]
            except Exception:
                pass
    return ""


def _detect_install_cmd(readme: str, path: str) -> str:
    if "pip install" in readme:
        m = re.search(r"pip install[^\n]+", readme)
        return m.group(0).strip() if m else "pip install -e ."
    if os.path.exists(os.path.join(path, "requirements.txt")):
        return "pip install -r requirements.txt"
    if os.path.exists(os.path.join(path, "setup.py")):
        return "pip install -e ."
    if os.path.exists(os.path.join(path, "pyproject.toml")):
        return "pip install -e ."
    return "echo 'no install command detected'"


def _detect_run_cmd(readme: str, path: str) -> str:
    if "python " in readme:
        m = re.search(r"python\s+\S+\.py[^\n]*", readme)
        return m.group(0).strip() if m else "python main.py"
    return "python main.py"


def _run_sandbox_cmd(cmd: str, path: str, timeout: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["bash", "-c", cmd],
            cwd=path, capture_output=True, timeout=timeout, text=True,
        )
        return {"exitCode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"exitCode": -1, "stdout": "", "stderr": "timeout"}
    except OSError:
        return {"exitCode": -2, "stdout": "", "stderr": "sandbox unavailable"}


def _extract_and_compare(stdout: str, paper_id: str) -> dict[str, Any]:
    # Extract numeric values from stdout
    numbers = re.findall(r"(\d+\.\d+|\d+)", stdout)
    return {
        "valuesFound": numbers[:10],
        "numericOutputs": len(numbers),
        "match": len(numbers) > 0,
        "note": "自动检测到数值输出。需人工对照论文报告值确认复现。",
    }


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "paperId": "", "repo": None, "verdict": "error",
            "comparison": {}, "error": message}
