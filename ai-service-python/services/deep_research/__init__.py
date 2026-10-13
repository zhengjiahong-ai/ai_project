"""Deep Research package.

Public symbols are imported lazily so test modules that only need the
repository do not pull in graph or facade dependencies.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "contracts",
    "repository",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - lazy import shim
    if name == "contracts":
        from services.deep_research import contracts as _contracts

        return _contracts
    if name == "repository":
        from services.deep_research import repository as _repository

        return _repository
    raise AttributeError(name)
