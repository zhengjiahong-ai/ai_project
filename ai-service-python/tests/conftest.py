"""Shared pytest fixtures and configuration for the Pixiu AI service test suite.

Usage: fixtures in this module are auto-discovered by pytest — no explicit
import needed in individual test files.
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so that "from services.xxx import ..."
# resolves correctly regardless of the working directory.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture(autouse=True)
def reset_tool_registry_after_test():
    """Reset the global tool registry so each test starts with a clean state."""
    yield
    from services.tool_registry import reset_tool_registry

    try:
        reset_tool_registry()
    except Exception:
        pass
