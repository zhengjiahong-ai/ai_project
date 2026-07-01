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
}


if __name__ == "__main__":
    raise SystemExit(PROBES[sys.argv[1]]())
