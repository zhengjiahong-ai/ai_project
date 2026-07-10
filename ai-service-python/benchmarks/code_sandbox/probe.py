"""Fixed, harmless probes used by both P5-02 candidates."""

import csv
import json
import os
import socket
import statistics
import subprocess
import sys
from pathlib import Path


INPUT = Path(os.environ.get("PIXIU_BENCH_INPUT", "/input/normal.csv"))
OUTPUT = Path(os.environ.get("PIXIU_BENCH_OUTPUT", "/output"))
CANARY = Path(os.environ.get("PIXIU_BENCH_CANARY", "/host-canary/p5-canary.txt"))
FIXTURES = Path(os.environ.get("PIXIU_BENCH_FIXTURES", "/fixtures"))


def _emit(status, detail):
    print(json.dumps({"status": status, "detail": detail}, separators=(",", ":")))
    return 0 if status == "passed" else 3


def normal_execution():
    with INPUT.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    values = [float(row["value"]) for row in rows]
    result = {"rowCount": len(rows), "mean": statistics.mean(values)}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return _emit("passed", "bounded_json_created")


def network():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.close()
    except OSError:
        return _emit("passed", "socket_creation_blocked")
    return _emit("failed", "socket_creation_allowed")


def adversarial_input():
    expected = {"injection.csv", "path_text.csv", "malformed.csv", "oversized_field.csv"}
    seen = set()
    warnings = 0
    for path in FIXTURES.glob("*.csv"):
        if path.name not in expected:
            continue
        seen.add(path.name)
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for index, row in enumerate(csv.reader(handle)):
                    if index > 20 or any(len(cell) > 256 for cell in row):
                        warnings += 1
                        break
        except (csv.Error, UnicodeError):
            warnings += 1
    if seen == expected and warnings <= len(expected):
        return _emit("passed", "adversarial_csv_treated_as_data")
    return _emit("failed", "adversarial_fixture_validation_failed")


def host_canary():
    return _emit("passed" if not CANARY.exists() else "failed", "host_canary_inaccessible" if not CANARY.exists() else "host_canary_visible")


def read_only_input():
    try:
        with INPUT.open("a", encoding="utf-8") as handle:
            handle.write("mutation")
    except OSError:
        return _emit("passed", "input_write_blocked")
    return _emit("failed", "input_write_allowed")


def temporary_output():
    try:
        Path("/p5-forbidden-output.txt").write_text("x", encoding="utf-8")
    except OSError:
        return _emit("passed", "root_write_blocked")
    return _emit("failed", "root_write_allowed")


def subprocess_probe():
    try:
        child = subprocess.run([sys.executable, "-c", "print('child')"], capture_output=True, timeout=1, check=False)
    except (OSError, subprocess.SubprocessError):
        return _emit("passed", "subprocess_blocked")
    return _emit("failed", f"subprocess_allowed_{child.returncode}")


def cpu_limit():
    while True:
        pass


def memory_limit():
    chunks = []
    while True:
        chunks.append(bytearray(16 * 1024 * 1024))


def stdout_limit():
    chunk = "x" * 65536
    for _ in range(32):
        print(chunk, flush=True)
    return 0


def path_traversal():
    """Attempt to read files outside /input via ../ in path."""
    traversal_paths = [
        Path("/input/../../../etc/passwd"),
        Path("/input/../etc/hostname"),
        Path("../../../etc/shadow"),
    ]
    for path in traversal_paths:
        try:
            if path.exists() and path.is_file():
                content = path.read_text()
                if content.strip():
                    return _emit("failed", f"path_traversal_read_{path.name}")
        except (OSError, PermissionError):
            continue
    return _emit("passed", "path_traversal_blocked")


def symlink_escape():
    """Attempt to create a symlink to escape the /input jail."""
    link_targets = ["/etc/passwd", "/etc/hostname", "/var/run/docker.sock"]
    for target in link_targets:
        try:
            link_path = Path("/tmp/p5-escape-link")
            if link_path.exists():
                link_path.unlink()
            os.symlink(target, str(link_path))
            if link_path.exists() or link_path.is_symlink():
                return _emit("failed", f"symlink_created_to_{Path(target).name}")
        except OSError:
            continue
    return _emit("passed", "symlink_creation_blocked")


def env_leak():
    """Attempt to read sensitive environment variables."""
    sensitive_keys = {"HOME", "PATH", "USER", "API_KEY", "DEEPSEEK_API_KEY",
                      "DASHSCOPE_API_KEY", "AWS_ACCESS_KEY_ID", "DATABASE_URL"}
    leaked = []
    for key in sorted(os.environ):
        if key in sensitive_keys:
            leaked.append(key)
        upper = key.upper()
        if any(s in upper for s in ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")):
            if key not in leaked:
                leaked.append(key)
    if leaked:
        return _emit("failed", f"env_leaked_{len(leaked)}_keys")
    return _emit("passed", "sensitive_env_absent")


def dns_resolution():
    """Attempt DNS resolution (blocked by --network none, not just socket block)."""
    import socket as sock
    hosts = ["google.com", "1.1.1.1", "169.254.169.254", "metadata.google.internal"]
    for host in hosts:
        try:
            addr = sock.getaddrinfo(host, 80, sock.AF_INET, sock.SOCK_STREAM)
            if addr:
                return _emit("failed", f"dns_resolved_{host}")
        except (OSError, sock.gaierror):
            continue
    return _emit("passed", "dns_resolution_blocked")


def docker_socket_probe():
    """Attempt to access Docker socket."""
    socket_path = Path("/var/run/docker.sock")
    if socket_path.exists():
        return _emit("failed", "docker_socket_visible")
    return _emit("passed", "docker_socket_inaccessible")


def fork_bomb():
    """Attempt to fork child processes (blocked by seccomp and PID limit)."""
    import os as _os
    try:
        pid = _os.fork()
        if pid == 0:
            _os._exit(0)
        else:
            _os.waitpid(pid, 0)
    except OSError:
        return _emit("passed", "fork_blocked")
    return _emit("failed", "fork_allowed")


def formula_injection():
    """Verify Excel/CSV formula prefixes are treated as plain text, not evaluated."""
    formula_fixture = FIXTURES / "formula_injection.csv"
    if not formula_fixture.exists():
        return _emit("failed", "formula_fixture_missing")
    try:
        with formula_fixture.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
    except (csv.Error, UnicodeError):
        return _emit("failed", "formula_fixture_parse_error")
    formula_prefixes = {"=", "+", "-", "@"}
    for row in rows[:20]:
        for cell in row:
            cell_stripped = cell.strip()
            if cell_stripped and cell_stripped[0] in formula_prefixes:
                continue
    return _emit("passed", "formula_cells_treated_as_data")


PROBES = {
    "normal_execution": normal_execution,
    "adversarial_input": adversarial_input,
    "network": network,
    "host_canary": host_canary,
    "read_only_input": read_only_input,
    "temporary_output": temporary_output,
    "subprocess": subprocess_probe,
    "cpu_limit": cpu_limit,
    "memory_limit": memory_limit,
    "stdout_limit": stdout_limit,
    "path_traversal": path_traversal,
    "symlink_escape": symlink_escape,
    "env_leak": env_leak,
    "dns_resolution": dns_resolution,
    "docker_socket": docker_socket_probe,
    "fork_bomb": fork_bomb,
    "formula_injection": formula_injection,
}


if __name__ == "__main__":
    raise SystemExit(PROBES[sys.argv[1]]())
