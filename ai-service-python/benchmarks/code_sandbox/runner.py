"""Live Docker and Windows Job Object candidate runners for P5-02."""

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


LIMITS = {
    "wallClockSeconds": 5,
    "cpuCount": 1,
    "memoryBytes": 128 * 1024 * 1024,
    "pids": 32,
    "stdoutBytes": 1024 * 1024,
    "tmpfsBytes": 16 * 1024 * 1024,
    "inputBytes": 1024 * 1024,
}
PROBE_NAMES = (
    "normal_execution", "adversarial_input", "network", "host_canary", "read_only_input",
    "temporary_output", "subprocess", "cpu_limit", "memory_limit", "stdout_limit",
)
RESOURCE_PROBES = {"cpu_limit", "memory_limit", "stdout_limit"}
LABEL = "pixiu.p5_02=benchmark"


def _safe_detail(value):
    allowed = {"bounded_json_created", "adversarial_csv_treated_as_data", "adversarial_fixture_validation_failed", "socket_creation_blocked", "socket_creation_allowed", "host_canary_inaccessible", "host_canary_visible", "input_write_blocked", "input_write_allowed", "root_write_blocked", "root_write_allowed", "subprocess_blocked"}
    if value in allowed or str(value).startswith("subprocess_allowed_"):
        return str(value)
    return "bounded_failure"


def _decode_probe(stdout):
    try:
        payload = json.loads(stdout.strip().splitlines()[-1])
        return {"status": payload.get("status", "failed"), "detail": _safe_detail(payload.get("detail"))}
    except (ValueError, IndexError, AttributeError):
        return {"status": "failed", "detail": "invalid_probe_output"}


def _command_version(command, args):
    try:
        completed = subprocess.run([command, *args], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _docker_cleanup():
    try:
        check = subprocess.run(["docker", "ps", "-aq", "--filter", f"label={LABEL}"], capture_output=True, text=True, timeout=15, check=False)
        ids = [line for line in check.stdout.splitlines() if line.strip()]
        if ids:
            subprocess.run(["docker", "rm", "-f", *ids], capture_output=True, timeout=30, check=False)
        verify = subprocess.run(["docker", "ps", "-aq", "--filter", f"label={LABEL}"], capture_output=True, text=True, timeout=15, check=False)
        residual = [line for line in verify.stdout.splitlines() if line.strip()]
        return {"status": "passed" if verify.returncode == 0 and not residual else "failed", "residualCount": len(residual)}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "failed", "residualCount": -1}


def existing_image_id(image):
    return _command_version("docker", ["image", "inspect", image, "--format", "{{.Id}}"])


def run_docker_candidate(directory, input_file):
    version = _command_version("docker", ["version", "--format", "{{.Server.Version}}"])
    if not version:
        return {"name": "docker", "runtime": "docker", "available": False, "reasonCode": "docker_unavailable", "probes": {}, "cleanup": {"status": "not_run", "residualCount": 0}}, {}
    image = "pixiu-code-sandbox-benchmark:p5-02"
    digest = existing_image_id(image)
    if not digest:
        try:
            build = subprocess.run(["docker", "build", "--pull=false", "-t", image, str(directory)], capture_output=True, text=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired):
            build = None
        if build is None or build.returncode != 0:
            return {"name": "docker", "runtime": "docker", "available": False, "reasonCode": "image_build_failed", "probes": {}, "cleanup": _docker_cleanup()}, {"dockerEngine": version}
        digest = existing_image_id(image)
    probes = {}
    seccomp = directory / "seccomp.json"
    for name in PROBE_NAMES:
        started = time.perf_counter()
        command = [
            "docker", "run", "--rm", "--label", LABEL, "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
            "--security-opt", f"seccomp={seccomp}", "--memory", "128m", "--memory-swap", "128m",
            "--cpus", "1", "--pids-limit", "32", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--tmpfs", "/output:rw,noexec,nosuid,size=16m", "--mount", f"type=bind,src={input_file},dst=/input/normal.csv,readonly",
            "--mount", f"type=bind,src={directory / 'fixtures'},dst=/fixtures,readonly",
            image, name,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=LIMITS["wallClockSeconds"], check=False)
            if name in RESOURCE_PROBES:
                status, detail = ("passed", "resource_limit_enforced") if completed.returncode != 0 or len(completed.stdout.encode("utf-8", "ignore")) >= LIMITS["stdoutBytes"] else ("failed", "resource_limit_not_observed")
            else:
                decoded = _decode_probe(completed.stdout)
                status, detail = decoded["status"], decoded["detail"]
        except subprocess.TimeoutExpired:
            status, detail = ("passed", "wall_clock_limit_enforced") if name in RESOURCE_PROBES else ("failed", "probe_timeout")
        probes[name] = {"status": status, "durationMs": round((time.perf_counter() - started) * 1000), "detail": detail}
    cleanup = _docker_cleanup()
    probes["cleanup"] = {"status": cleanup["status"], "durationMs": 0, "detail": "no_residual_containers" if cleanup["status"] == "passed" else "residual_containers"}
    return {"name": "docker", "runtime": "docker", "available": True, "reasonCode": "measured", "probes": probes, "cleanup": cleanup}, {"dockerEngine": version, "imageDigest": digest}


class _JobLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32), ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _JobLimits), ("IoInfo", _IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _assign_job(process):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    job = kernel32.CreateJobObjectW(None, None)
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x00002000 | 0x00000100 | 0x00000008
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.ProcessMemoryLimit = LIMITS["memoryBytes"]
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel32.CloseHandle(job)
        raise OSError("job_limit_configuration_failed")
    if not kernel32.AssignProcessToJobObject(job, int(process._handle)):
        kernel32.CloseHandle(job)
        raise OSError("job_assignment_failed")
    return kernel32, job


def terminate_job_process(process, kernel32, job):
    """Terminate a timed-out job without draining an unbounded stdout pipe."""
    kernel32.TerminateJobObject(job, 1)
    process.kill()
    for pipe in (process.stdout, process.stderr):
        if pipe is not None:
            pipe.close()
    process.wait(timeout=2)


def copy_windows_input(source, target_directory):
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / "normal.csv"
    shutil.copyfile(source, target)
    return target


def run_windows_candidate(directory, input_file):
    if os.name != "nt":
        return {"name": "windows_job_object", "runtime": "windows_job_object", "available": False, "reasonCode": "windows_only", "probes": {}, "cleanup": {"status": "not_run", "residualCount": 0}}
    probes = {}
    with tempfile.TemporaryDirectory(prefix="pixiu-p5-02-") as temp:
        temp_path = Path(temp)
        job_input = copy_windows_input(input_file, temp_path / "input")
        output = temp_path / "output"
        output.mkdir()
        canary = temp_path / "p5-canary.txt"
        canary.write_text(hashlib.sha256(b"pixiu-p5-02").hexdigest(), encoding="utf-8")
        env = {**os.environ, "PIXIU_BENCH_INPUT": str(job_input), "PIXIU_BENCH_OUTPUT": str(output), "PIXIU_BENCH_CANARY": str(canary), "PIXIU_BENCH_FIXTURES": str(directory / "fixtures")}
        for name in PROBE_NAMES:
            started = time.perf_counter()
            process = subprocess.Popen([sys.executable, str(directory / "probe.py"), name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            try:
                kernel32, job = _assign_job(process)
                try:
                    stdout, _ = process.communicate(timeout=LIMITS["wallClockSeconds"])
                    if name in RESOURCE_PROBES:
                        status, detail = ("passed", "resource_limit_enforced") if process.returncode != 0 or len(stdout.encode("utf-8", "ignore")) >= LIMITS["stdoutBytes"] else ("failed", "resource_limit_not_observed")
                    else:
                        decoded = _decode_probe(stdout)
                        status, detail = decoded["status"], decoded["detail"]
                except subprocess.TimeoutExpired:
                    terminate_job_process(process, kernel32, job)
                    status, detail = (("passed", "wall_clock_limit_enforced") if name in RESOURCE_PROBES else ("failed", "probe_timeout"))
                finally:
                    kernel32.CloseHandle(job)
            except OSError:
                process.kill()
                process.communicate()
                status, detail = "failed", "job_object_error"
            probes[name] = {"status": status, "durationMs": round((time.perf_counter() - started) * 1000), "detail": detail}
    cleanup = {"status": "passed", "residualCount": 0}
    probes["cleanup"] = {"status": "passed", "durationMs": 0, "detail": "temporary_directory_removed"}
    return {"name": "windows_job_object", "runtime": "windows_job_object", "available": True, "reasonCode": "measured", "probes": probes, "cleanup": cleanup}


def run_live_candidates(directory):
    input_file = directory / "fixtures" / "normal.csv"
    docker, environment = run_docker_candidate(directory, input_file)
    windows = run_windows_candidate(directory, input_file)
    return [docker, windows], environment
