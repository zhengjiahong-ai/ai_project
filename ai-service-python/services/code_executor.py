from __future__ import annotations

import ast
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from services.code_execution_models import WORKER_IMAGE_DIGEST

# ── Constants ────────────────────────────────────────────────────────────────

ALLOWED_MODULES: frozenset[str] = frozenset({
    "base64", "bisect", "collections", "copy", "csv", "dataclasses",
    "datetime", "decimal", "enum", "fractions", "functools", "hashlib",
    "heapq", "io", "itertools", "json", "math", "operator", "pprint",
    "random", "re", "statistics", "string", "textwrap", "typing",
})

FORBIDDEN_BUILTINS: frozenset[str] = frozenset({
    "__import__", "breakpoint", "compile", "eval", "exec",
    "exit", "input", "memoryview", "open", "quit",
})

MAX_CODE_LENGTH: int = 65536  # 64 KiB
MAX_STDOUT_BYTES: int = 256 * 1024  # 256 KiB
MAX_STDERR_BYTES: int = 64 * 1024  # 64 KiB
DEFAULT_TIMEOUT: int = 30
MAX_TIMEOUT: int = 30
MEMORY_BYTES: int = 256 * 1024 * 1024  # 256 MiB
CPU_COUNT: str = "1"
PID_LIMIT: int = 64
TMPFS_BYTES: int = 32 * 1024 * 1024  # 32 MiB

_PACKAGE_DIR = Path(__file__).resolve().parent.parent / "code_worker"
_SECCOMP_PATH = _PACKAGE_DIR / "seccomp.json"

_OUTPUT_BUDGET_LOCK = threading.Lock()


# ── AST Safety Validation ────────────────────────────────────────────────────

def _check_import_name(name: str) -> None:
    """Raise ValueError if the top-level module name is not allowed."""
    root = name.split(".")[0]
    if root not in ALLOWED_MODULES:
        raise ValueError(f"Import not allowed: {root}")


def validate_code_safety(code: str) -> None:
    """Validate Python code safety via AST analysis.

    Checks performed:
      - Code is non-empty and within MAX_CODE_LENGTH.
      - Code is syntactically valid.
      - All imports use only modules from ALLOWED_MODULES.
      - No calls to dangerous builtins (eval, exec, __import__, etc.).
      - No dunder-attribute access patterns used for sandbox escapes.

    Raises ValueError with a descriptive message if the code is unsafe.
    """
    if not code or not code.strip():
        raise ValueError("Code cannot be empty.")
    if len(code) > MAX_CODE_LENGTH:
        raise ValueError(
            f"Code length {len(code)} exceeds maximum {MAX_CODE_LENGTH} characters."
        )

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in code: {exc}") from exc

    for node in ast.walk(tree):
        # ── Import / ImportFrom ──────────────────────────────────────────
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_import_name(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                _check_import_name(node.module)
        # ── Forbidden builtin calls ──────────────────────────────────────
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_BUILTINS:
                    raise ValueError(f"Forbidden built-in call: {node.func.id}")
        # ── Dunder attribute access (object.__subclasses__ etc.) ────────
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and len(node.attr) > 4:
                raise ValueError(
                    f"Forbidden dunder attribute access: .{node.attr}"
                )


# ── Docker Sandbox Execution ─────────────────────────────────────────────────

def _docker_command(container_name: str, timeout: int) -> list[str]:
    """Build the ``docker run`` command with full security hardening.

    Reuses the same image, seccomp profile, and resource limits as the
    existing ``code_worker/runner.py`` but overrides the entrypoint so
    arbitrary code can be passed via stdin.
    """
    return [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges=true",
        "--security-opt", f"seccomp={_SECCOMP_PATH}",
        "--memory", str(MEMORY_BYTES),
        "--memory-swap", str(MEMORY_BYTES),
        "--cpus", CPU_COUNT,
        "--pids-limit", str(PID_LIMIT),
        "--ulimit", f"cpu={timeout}:{timeout}",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,size={TMPFS_BYTES}",
        "-i",
        "--entrypoint", "python",
        WORKER_IMAGE_DIGEST,
        "-I", "-S", "-",
    ]


def _drain_bounded(pipe, limit: int) -> bytes:
    """Read *pipe* until EOF, stopping when *limit* bytes have been read."""
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = pipe.read(8192)
            if not chunk:
                break
            remaining = limit - total
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            chunks.append(chunk)
            total += len(chunk)
    finally:
        try:
            pipe.close()
        except OSError:
            pass
    return b"".join(chunks)


def execute_python_sandbox(
    code: str, timeout: int = DEFAULT_TIMEOUT
) -> dict[str, str]:
    """Execute *code* in a Docker sandbox and return ``{status, stdout, stderr, error}``.

    The sandbox has no network, a read-only root filesystem, no Linux
    capabilities, a restrictive seccomp profile, and CPU / memory / PID
    limits.  Before the container is launched the code is validated with
    :func:`validate_code_safety`.

    Returns
    -------
    dict
        ``status``   – one of ``"success"``, ``"timeout"``, ``"error"``, ``"forbidden_import"``.
        ``stdout``   – captured standard output (UTF-8).
        ``stderr``   – captured standard error (UTF-8).
        ``error``    – human-readable error description (empty string on success).
    """
    # ── Clamp timeout ────────────────────────────────────────────────────
    timeout = min(max(int(timeout), 1), MAX_TIMEOUT)

    # ── Pre-execution safety validation ──────────────────────────────────
    try:
        validate_code_safety(code)
    except ValueError as exc:
        return {
            "status": "forbidden_import",
            "stdout": "",
            "stderr": "",
            "error": str(exc),
        }

    container_name = f"pixiu-exec-{uuid.uuid4().hex[:12]}"
    cmd = _docker_command(container_name, timeout)

    # Temporary directory for cwd (clean isolation; discarded after run).
    temp_dir = tempfile.mkdtemp(prefix="pixiu-exec-")

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=temp_dir,
            text=False,
        )
    except (FileNotFoundError, OSError):
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "error": "Docker is not available for sandbox execution.",
        }

    # Drain stdout / stderr in background threads so the pipes never block.
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_exceeded = threading.Event()

    def _stdout_drain():
        data = _drain_bounded(process.stdout, MAX_STDOUT_BYTES)
        stdout_chunks.append(data)
        if len(data) >= MAX_STDOUT_BYTES:
            stdout_exceeded.set()

    def _stderr_drain():
        data = _drain_bounded(process.stderr, MAX_STDERR_BYTES)
        stderr_chunks.append(data)

    stdout_thread = threading.Thread(target=_stdout_drain, daemon=True)
    stderr_thread = threading.Thread(target=_stderr_drain, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    # Write code to stdin and close immediately.
    try:
        process.stdin.write(code.encode("utf-8"))
        process.stdin.close()
    except (BrokenPipeError, OSError):
        pass  # container may have exited already

    deadline = time.monotonic() + timeout
    timed_out = False

    while process.poll() is None:
        if stdout_exceeded.is_set():
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        time.sleep(0.02)

    if timed_out or process.poll() is None:
        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True, timeout=3, check=False,
            )
            process.wait(timeout=3)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            try:
                process.kill()
            except OSError:
                pass

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    stdout_bytes = stdout_chunks[0] if stdout_chunks else b""
    stderr_bytes = stderr_chunks[0] if stderr_chunks else b""

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")

    exit_code = process.returncode

    if timed_out:
        return {
            "status": "timeout",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "error": f"Execution timed out after {timeout}s.",
        }
    if stdout_exceeded.is_set():
        return {
            "status": "error",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "error": "stdout exceeded the 256 KiB limit.",
        }
    if exit_code != 0:
        return {
            "status": "error",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "error": f"Process exited with code {exit_code}.",
        }
    return {
        "status": "success",
        "stdout": stdout_text,
        "stderr": stderr_text,
        "error": "",
    }
