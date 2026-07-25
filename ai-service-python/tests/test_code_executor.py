"""
Tests for the code_executor module.

Covers:
- validate_code_safety: allowed imports, forbidden imports, forbidden builtins,
  injection attempts, empty code, excessively long code, syntax errors.
- execute_python_sandbox: normal execution, timeout, forbidden imports,
  Docker error handling (when Docker is available).

Integration tests that require Docker are skipped automatically when
the Docker daemon is not reachable.
"""

import subprocess
import unittest

from services.code_executor import (
    ALLOWED_MODULES,
    MAX_CODE_LENGTH,
    execute_python_sandbox,
    validate_code_safety,
)


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=3, check=False
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


_DOCKER = _docker_available()


# ── validate_code_safety unit tests (no Docker needed) ───────────────────────

class CodeSafetyValidationTests(unittest.TestCase):

    def test_accepts_normal_code(self):
        validate_code_safety("print('hello')")

    def test_accepts_allowed_import(self):
        validate_code_safety("import math\nprint(math.pi)")

    def test_accepts_allowed_from_import(self):
        validate_code_safety("from collections import Counter\nc = Counter([1, 2])")

    def test_accepts_all_allowed_modules(self):
        for module in sorted(ALLOWED_MODULES):
            with self.subTest(module=module):
                validate_code_safety(f"import {module}")

    def test_rejects_empty_code(self):
        with self.assertRaisesRegex(ValueError, "Code cannot be empty"):
            validate_code_safety("")

    def test_rejects_whitespace_only(self):
        with self.assertRaisesRegex(ValueError, "Code cannot be empty"):
            validate_code_safety("   \n  \t  ")

    def test_rejects_excessively_long_code(self):
        long_code = "x = 1\n" * (MAX_CODE_LENGTH // 6 + 1)
        with self.assertRaisesRegex(ValueError, "exceeds maximum"):
            validate_code_safety(long_code)

    def test_rejects_os_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: os"):
            validate_code_safety("import os\nos.getcwd()")

    def test_rejects_sys_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: sys"):
            validate_code_safety("import sys\nsys.exit()")

    def test_rejects_subprocess_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: subprocess"):
            validate_code_safety("import subprocess\nsubprocess.run(['ls'])")

    def test_rejects_socket_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: socket"):
            validate_code_safety("import socket")

    def test_rejects_ctypes_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: ctypes"):
            validate_code_safety("import ctypes")

    def test_rejects_threading_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: threading"):
            validate_code_safety("import threading")

    def test_rejects_multiprocessing_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: multiprocessing"):
            validate_code_safety("import multiprocessing")

    def test_rejects_pickle_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: pickle"):
            validate_code_safety("import pickle")

    def test_rejects_builtins_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: builtins"):
            validate_code_safety("import builtins")

    def test_rejects_importlib_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: importlib"):
            validate_code_safety("import importlib\nimportlib.import_module('os')")

    def test_rejects_code_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: code"):
            validate_code_safety("import code\ncode.interact()")

    def test_rejects_signal_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: signal"):
            validate_code_safety("import signal")

    def test_rejects_shutil_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: shutil"):
            validate_code_safety("import shutil")

    def test_rejects_pathlib_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: pathlib"):
            validate_code_safety("from pathlib import Path")

    def test_rejects_urllib_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: urllib"):
            validate_code_safety("import urllib.request")

    def test_rejects_http_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: http"):
            validate_code_safety("import http.client")

    def test_rejects_requests_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: requests"):
            validate_code_safety("import requests")

    def test_rejects_unlisted_import(self):
        with self.assertRaisesRegex(ValueError, "Import not allowed: numpy"):
            validate_code_safety("import numpy as np")

    def test_rejects_eval_call(self):
        with self.assertRaisesRegex(ValueError, "Forbidden built-in call: eval"):
            validate_code_safety("eval('1+1')")

    def test_rejects_exec_call(self):
        with self.assertRaisesRegex(ValueError, "Forbidden built-in call: exec"):
            validate_code_safety("exec('x=1')")

    def test_rejects_compile_call(self):
        with self.assertRaisesRegex(ValueError, "Forbidden built-in call: compile"):
            validate_code_safety("compile('x=1', '', 'exec')")

    def test_rejects_open_call(self):
        with self.assertRaisesRegex(ValueError, "Forbidden built-in call: open"):
            validate_code_safety("open('/etc/passwd')")

    def test_rejects_dunder_import_call(self):
        with self.assertRaisesRegex(ValueError, "Forbidden built-in call: __import__"):
            validate_code_safety("__import__('os')")

    def test_rejects_dunder_attribute_access(self):
        with self.assertRaisesRegex(ValueError, "Forbidden dunder attribute"):
            validate_code_safety("class X: pass\nX().__subclasses__()")

    def test_rejects_input_call(self):
        with self.assertRaisesRegex(ValueError, "Forbidden built-in call: input"):
            validate_code_safety("input('> ')")

    def test_rejects_breakpoint_call(self):
        with self.assertRaisesRegex(ValueError, "Forbidden built-in call: breakpoint"):
            validate_code_safety("breakpoint()")

    def test_rejects_syntax_error(self):
        with self.assertRaisesRegex(ValueError, "Syntax error"):
            validate_code_safety("def broken(")


# ── execute_python_sandbox integration tests (Docker required) ────────────────

@unittest.skipUnless(_DOCKER, "Docker daemon is not available")
class CodeExecutorDockerIntegrationTests(unittest.TestCase):

    def test_simple_print(self):
        result = execute_python_sandbox("print('hello world')")
        self.assertEqual(result["status"], "success")
        self.assertIn("hello world", result["stdout"])
        self.assertEqual(result["stderr"], "")
        self.assertEqual(result["error"], "")

    def test_math_sqrt(self):
        result = execute_python_sandbox("import math\nprint(math.sqrt(16))")
        self.assertEqual(result["status"], "success")
        self.assertIn("4.0", result["stdout"])

    def test_statistics_mean(self):
        result = execute_python_sandbox(
            "import statistics\nprint(statistics.mean([1, 2, 3, 4, 5]))"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("3", result["stdout"])

    def test_json_dumps(self):
        result = execute_python_sandbox(
            "import json\nd = {'a': 1}\nprint(json.dumps(d))"
        )
        self.assertEqual(result["status"], "success")
        self.assertTrue(
            '{"a": 1}' in result["stdout"] or '{"a":1}' in result["stdout"],
            f"stdout was: {result['stdout']}",
        )

    def test_csv_module(self):
        result = execute_python_sandbox(
            "import csv, io\n"
            "r = csv.reader(io.StringIO('a,b\\n1,2'))\n"
            "print(list(r))"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("['a', 'b']", result["stdout"])

    def test_collections_counter(self):
        result = execute_python_sandbox(
            "from collections import Counter\n"
            "c = Counter('abracadabra')\n"
            "print(c['a'])"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("5", result["stdout"])

    def test_itertools_islice(self):
        result = execute_python_sandbox(
            "from itertools import islice\n"
            "print(list(islice(range(10), 5)))"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("[0, 1, 2, 3, 4]", result["stdout"])

    def test_re_search(self):
        result = execute_python_sandbox(
            "import re\nm = re.search(r'\\d+', 'abc123def')\nprint(m.group())"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("123", result["stdout"])

    def test_datetime_module(self):
        result = execute_python_sandbox(
            "import datetime\nprint(datetime.date(2026, 1, 1).year)"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("2026", result["stdout"])

    def test_complex_expression(self):
        result = execute_python_sandbox(
            "import math, statistics\n"
            "data = [1.5, 2.7, 3.1, 4.2, 5.8]\n"
            "m = statistics.mean(data)\n"
            "sd = statistics.stdev(data) if len(data) >= 2 else 0\n"
            "print(f'mean={m:.2f}, sd={sd:.2f}')"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("mean=", result["stdout"])

    def test_stderr_output(self):
        result = execute_python_sandbox(
            "import sys\nprint('ok', file=sys.stderr)\nprint('out')"
        )
        self.assertEqual(result["status"], "forbidden_import")
        self.assertIn("sys", result["error"])

    def test_list_comprehension(self):
        result = execute_python_sandbox(
            "squares = [x*x for x in range(5)]\nprint(sum(squares))"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("30", result["stdout"])

    def test_timeout_enforced(self):
        result = execute_python_sandbox("while True: pass", timeout=3)
        self.assertEqual(result["status"], "timeout")
        self.assertIn("timed out", result["error"])

    def test_forbidden_import_at_validation(self):
        result = execute_python_sandbox("import os\nprint(os.name)")
        self.assertEqual(result["status"], "forbidden_import")
        self.assertIn("Import not allowed", result["error"])

    def test_eval_injection_rejected(self):
        result = execute_python_sandbox("eval('1+1')")
        self.assertEqual(result["status"], "forbidden_import")
        self.assertIn("Forbidden built-in", result["error"])

    def test_no_network_access(self):
        result = execute_python_sandbox(
            "import http.client\nprint('should not reach')"
        )
        self.assertEqual(result["status"], "forbidden_import")

    def test_empty_code_via_sandbox(self):
        result = execute_python_sandbox("")
        self.assertEqual(result["status"], "forbidden_import")
        self.assertIn("empty", result["error"])

    def test_timeout_clamped_to_max(self):
        result = execute_python_sandbox("print('ok')", timeout=999)
        self.assertEqual(result["status"], "success")
        self.assertIn("ok", result["stdout"])

    def test_negative_timeout_clamped_to_1(self):
        result = execute_python_sandbox("print('ok')", timeout=-5)
        self.assertEqual(result["status"], "success")
        self.assertIn("ok", result["stdout"])

    def test_custom_timeout_within_range(self):
        result = execute_python_sandbox("print('ok')", timeout=10)
        self.assertEqual(result["status"], "success")
        self.assertIn("ok", result["stdout"])


# ── execute_python_sandbox tests that do NOT need Docker ──────────────────────

class CodeExecutorValidationOnlyTests(unittest.TestCase):
    """Tests for execute_python_sandbox that validate the pre-execution checks
    and do not require Docker."""

    def test_returns_forbidden_import_on_bad_code(self):
        result = execute_python_sandbox("import os")
        self.assertEqual(result["status"], "forbidden_import")

    def test_returns_forbidden_import_on_eval(self):
        result = execute_python_sandbox("eval('x')")
        self.assertEqual(result["status"], "forbidden_import")

    def test_returns_forbidden_import_on_empty(self):
        result = execute_python_sandbox("")
        self.assertEqual(result["status"], "forbidden_import")
        self.assertIn("empty", result["error"])

    def test_returns_forbidden_import_on_dunder(self):
        result = execute_python_sandbox("__import__('os')")
        self.assertEqual(result["status"], "forbidden_import")

    def test_code_length_limit_before_docker(self):
        long_code = "x = 1\n" * (MAX_CODE_LENGTH // 6 + 1)
        result = execute_python_sandbox(long_code)
        self.assertEqual(result["status"], "forbidden_import")
        self.assertIn("exceeds maximum", result["error"])
