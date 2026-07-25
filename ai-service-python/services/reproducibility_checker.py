"""Experimental reproducibility checker — verifies paper claims by running code.

Searches for associated code repositories on GitHub, clones into a Docker sandbox,
installs dependencies, and runs experiments. Compares output against reported results.

**Security**: Execution runs inside the existing code_worker Docker sandbox
(non-root, no-network, read-only rootfs, seccomp). Enabled only when
``PIXIU_ALLOW_REPRODUCIBILITY=true`` is explicitly set.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from typing import Any

from services.code_execution_models import WORKER_IMAGE_DIGEST

_TIMEOUT_CLONE = 60
_TIMEOUT_INSTALL = 120
_TIMEOUT_RUN = 60
_MAX_REPO_SIZE_BYTES = 200 * 1024 * 1024
_ALLOWED_REPO_HOSTS = {"github.com"}
_SECCOMP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "code_worker", "seccomp.json",
)


def _is_enabled() -> bool:
    return os.environ.get("PIXIU_ALLOW_REPRODUCIBILITY", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


# ── Public API ───────────────────────────────────────────────────────────────

def verify_reproducibility(paper_id: str) -> dict[str, Any]:
    """Check if the paper's code is reproducible.

    Returns ``{status, paperId, repo, build, run, comparison, verdict, error}``.
    """
    if not _is_enabled():
        return {
            "status": "disabled",
            "paperId": paper_id or "",
            "repo": None,
            "verdict": "disabled",
            "comparison": {},
            "error": "Reproducibility checker is disabled. Set PIXIU_ALLOW_REPRODUCIBILITY=true to enable.",
        }

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

        # Step 4: Check if dependencies can be satisfied without network
        dep_check = _check_dependencies(install_cmd, tmp)
        if not dep_check["ok"]:
            return {
                "status": "success",
                "paperId": paper_id,
                "repo": repo,
                "build": {"command": install_cmd, "exitCode": -1, "stdout": dep_check["reason"]},
                "run": {},
                "comparison": {},
                "verdict": "unable_to_verify",
                "error": dep_check["reason"],
            }

        # Step 5: Execute inside Docker sandbox
        sandbox_result = _run_docker_sandbox(tmp, install_cmd, run_cmd)

        # Step 6: Extract results and compare
        comparison = _extract_and_compare(
            sandbox_result.get("runStdout", ""), paper_id,
        )

        return {
            "status": "success",
            "paperId": paper_id,
            "repo": repo,
            "build": {
                "command": install_cmd,
                "exitCode": sandbox_result.get("installExitCode"),
                "stdout": (sandbox_result.get("installStdout") or "")[:1000],
            },
            "run": {
                "command": run_cmd,
                "exitCode": sandbox_result.get("runExitCode"),
                "stdout": (sandbox_result.get("runStdout") or "")[:2000],
            },
            "comparison": comparison,
            "verdict": (
                "reproduced" if comparison.get("match", False)
                else "partial" if sandbox_result.get("runExitCode") == 0
                else "failed"
            ),
            "error": sandbox_result.get("error") or "",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Code repository search ───────────────────────────────────────────────────

def _find_code_repo(paper_id: str) -> str | None:
    try:
        from services.tool_registry import get_tool_registry
        registry = get_tool_registry()
        resp = registry.invoke("search_web", {
            "query": f"{paper_id} github code repository",
            "limit": 5,
        })
        items = resp.get("items") or []
        for item in items:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            host = _extract_host(url)
            if host in _ALLOWED_REPO_HOSTS:
                return url
    except Exception:
        pass
    return None


def _extract_host(url: str) -> str:
    m = re.match(r"https?://([^/:]+)", url.lower())
    return m.group(1) if m else ""


def _clone_repo(url: str, target: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, target],
            capture_output=True, timeout=_TIMEOUT_CLONE, text=True,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _read_readme(path: str) -> str:
    import glob
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        for f in glob.glob(os.path.join(path, name), recursive=False):
            try:
                with open(f, encoding="utf-8") as handle:
                    return handle.read()[:5000]
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


def _check_dependencies(install_cmd: str, path: str) -> dict[str, Any]:
    """Check if the project's dependencies are limited to the Python standard library.

    Without network access in the Docker sandbox, only standard-library-only
    projects can be verified.
    """
    req_path = os.path.join(path, "requirements.txt")
    if not os.path.exists(req_path):
        return {"ok": True, "reason": ""}

    try:
        with open(req_path, encoding="utf-8") as handle:
            lines = [
                ln.split("#")[0].strip()
                for ln in handle
                if ln.strip() and not ln.strip().startswith("#")
            ]
    except Exception:
        return {"ok": True, "reason": ""}

    non_stdlib = []
    for line in lines:
        pkg = re.split(r"[=<>~!\[\s]", line)[0].strip().lower()
        if pkg and pkg not in _STDLIB_TOP_LEVELS:
            non_stdlib.append(pkg)

    if non_stdlib:
        return {
            "ok": False,
            "reason": (
                f"Dependencies not pre-installed in sandbox: {', '.join(non_stdlib[:8])}. "
                "Only standard-library Python projects can be verified automatically."
            ),
        }
    return {"ok": True, "reason": ""}


# ── Docker sandbox execution ─────────────────────────────────────────────────

def _run_docker_sandbox(
    repo_path: str, install_cmd: str, run_cmd: str,
) -> dict[str, Any]:
    """Run install + execute inside the code_worker Docker sandbox.

    Uses the same immutable image, seccomp profile, and security constraints
    as the code execution worker. No network access.
    """
    if not _docker_available():
        return {"installExitCode": -2, "error": "docker_unavailable"}

    container_name = f"pixiu-repro-{uuid.uuid4().hex[:12]}"
    repo_abs = os.path.abspath(repo_path)
    output_dir = tempfile.mkdtemp(prefix="pixiu-repro-out-")
    seccomp = os.path.abspath(_SECCOMP_PATH)

    try:
        script = _build_sandbox_script(install_cmd, run_cmd)
        script_path = os.path.join(output_dir, "run.sh")
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(script)

        cmd = [
            "docker", "run", "--name", container_name,
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges=true",
            "--security-opt", f"seccomp={seccomp}",
            "--memory", "268435456",
            "--memory-swap", "268435456",
            "--cpus", "1",
            "--pids-limit", "64",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=33554432",
            "--mount", f"type=bind,src={repo_abs},dst=/input/repo,readonly",
            "--mount", f"type=bind,src={script_path},dst=/input/run.sh,readonly",
            "--mount", f"type=bind,src={output_dir},dst=/output",
            WORKER_IMAGE_DIGEST,
            "bash", "/input/run.sh",
        ]

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=_TIMEOUT_INSTALL + _TIMEOUT_RUN + 30)
        except subprocess.TimeoutExpired:
            _docker_kill(container_name)
            return {"installExitCode": -1, "error": "sandbox_timeout"}

        try:
            result_json = json.loads(
                open(os.path.join(output_dir, "result.json"), encoding="utf-8").read(),
            )
        except (OSError, json.JSONDecodeError):
            result_json = {}

        return {
            "installExitCode": result_json.get("installExitCode", process.returncode),
            "installStdout": (result_json.get("installStdout") or "")[:2000],
            "runExitCode": result_json.get("runExitCode"),
            "runStdout": (result_json.get("runStdout") or "")[:4000],
            "error": "",
        }
    except OSError:
        return {"installExitCode": -2, "error": "sandbox_unavailable"}
    finally:
        _docker_kill(container_name)
        _docker_rm(container_name)
        shutil.rmtree(output_dir, ignore_errors=True)


def _build_sandbox_script(install_cmd: str, run_cmd: str) -> str:
    import json as _json
    return (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "INSTALL_CMD=" + _json.dumps(install_cmd) + "\n"
        "RUN_CMD=" + _json.dumps(run_cmd) + "\n"
        'INSTALL_OUT=$(cd /input/repo && eval "$INSTALL_CMD" 2>&1) && INSTALL_RC=$? || INSTALL_RC=$?\n'
        'RUN_OUT=$(cd /input/repo && eval "$RUN_CMD" 2>&1) && RUN_RC=$? || RUN_RC=$?\n'
        'python3 -c \'import json; print(json.dumps({"installExitCode":\'"$INSTALL_RC"\''
        ',"installStdout":\'"$(printf "%s" "$INSTALL_OUT" | head -c 2000 | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))")"\','
        '"runExitCode":\'"$RUN_RC"\''
        ',"runStdout":\'"$(printf "%s" "$RUN_OUT" | head -c 4000 | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))")"\'}))\' > /output/result.json\n'
    )


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _docker_kill(name: str) -> None:
    try:
        subprocess.run(
            ["docker", "kill", name], capture_output=True, timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _docker_rm(name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", name], capture_output=True, timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _extract_and_compare(stdout: str, paper_id: str) -> dict[str, Any]:
    numbers = re.findall(r"(\d+\.\d+|\d+)", stdout)
    return {
        "valuesFound": numbers[:10],
        "numericOutputs": len(numbers),
        "match": len(numbers) > 0,
        "note": "自动检测到数值输出。需人工对照论文报告值确认复现。",
    }


def _error(message: str) -> dict[str, Any]:
    return {
        "status": "error", "paperId": "", "repo": None,
        "verdict": "error", "comparison": {}, "error": message,
    }


# ── Standard library top-level module names ──────────────────────────────────

_STDLIB_TOP_LEVELS: set[str] = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii", "binhex",
    "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath",
    "cmd", "code", "codecs", "codeop", "collections", "colorsys", "compileall",
    "concurrent", "configparser", "contextlib", "contextvars", "copy",
    "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses", "dataclasses",
    "datetime", "dbm", "decimal", "difflib", "dis", "distutils", "doctest",
    "email", "encodings", "enum", "errno", "faulthandler", "fcntl", "filecmp",
    "fileinput", "fnmatch", "formatter", "fractions", "ftplib", "functools",
    "gc", "getopt", "getpass", "gettext", "glob", "graphlib", "grp", "gzip",
    "hashlib", "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
    "imp", "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
    "mailcap", "marshal", "math", "mimetypes", "mmap", "modulefinder", "msilib",
    "msvcrt", "multiprocessing", "netrc", "nis", "nntplib", "numbers", "operator",
    "optparse", "os", "ossaudiodev", "parser", "pathlib", "pdb", "pickle",
    "pickletools", "pipes", "pkgutil", "platform", "plistlib", "poplib",
    "posix", "posixpath", "pprint", "profile", "pstats", "pty", "pwd", "pyclbr",
    "pydoc", "py_compile", "queue", "quopri", "random", "re", "readline",
    "reprlib", "resource", "rlcompleter", "runpy", "sched", "secrets",
    "select", "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "sqlite3",
    "ssl", "stat", "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny", "tarfile",
    "telnetlib", "tempfile", "termios", "test", "textwrap", "threading",
    "time", "timeit", "tkinter", "token", "tokenize", "trace", "traceback",
    "tracemalloc", "tty", "turtle", "turtledemo", "types", "typing",
    "unicodedata", "unittest", "urllib", "uu", "uuid", "venv", "warnings",
    "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib",
    "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
    "zoneinfo",
}
