"""Advisory pool-selection helper for deep-research finalization nodes.

``select_reservation_pool`` is a PURE, read-only helper invoked inside an
open database transaction *before* the authoritative budget-validation path.
It never mutates budgets, never increases limits, never consumes capacity,
and never bypasses status/time/unknown-call guards.  Its sole purpose is to
let eligible finalization nodes fall back from the protected reserve pool to
the normal pool when the reserve is exhausted but unconsumed normal capacity
remains.

Return value semantics:
  * ``True``  – caller should attempt the protected reserve pool.
  * ``False`` – caller should attempt the normal pool.

The returned bool does **not** prove call admission; the repository still
performs full authoritative checks and records the actual pool used.
"""

from __future__ import annotations

from typing import Any

__all__ = ["select_reservation_pool"]

_FINALIZATION_NODES: frozenset[str] = frozenset(
    {
        "synthesize",
        "verify",
        "verify_repair",
        "verify_design_config",
        "verify_design_science",
        "verify_repair_design_science",
        "verify_answer_coverage",
    }
)

_LIMIT_FIELDS = ("maxModelCalls", "reserveModelCalls", "maxTokens", "reserveTokens")
_USED_FIELDS = ("modelCalls", "reservedModelCalls", "normalTokens", "tokens")


def _valid_nonneg_int(value: Any) -> bool:
    """Return True when *value* is an int >= 0 and NOT a bool."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def select_reservation_pool(
    budget: Any,
    delta: Any,
    requested_reserve: bool,
    node: Any,
) -> bool:
    """Advisory pool selector – never mutates *budget* or *delta*.

    Returns *requested_reserve* unchanged in every case **except** when all
    fallback conditions are satisfied for an authorised finalization node,
    in which case it returns ``False`` (use normal pool).
    """

    # --- fast-path: nothing to do unless caller asked for the reserve pool.
    if requested_reserve is not True:
        return requested_reserve

    # --- node must be an authorised finalization node.
    try:
        if node not in _FINALIZATION_NODES:
            return requested_reserve
    except TypeError:
        # Unhashable node (e.g. list/dict) – cannot match.
        return requested_reserve

    # --- both arguments must be plain dicts.
    if not isinstance(budget, dict) or not isinstance(delta, dict):
        return requested_reserve

    # --- delta.modelCalls must be a positive int (bool excluded).
    delta_model_calls: Any = delta.get("modelCalls")
    if not isinstance(delta_model_calls, int) or isinstance(delta_model_calls, bool):
        return requested_reserve
    if delta_model_calls <= 0:
        return requested_reserve

    # --- delta.tokens defaults to 0 when absent; must be nonneg int.
    delta_tokens: Any = delta.get("tokens", 0)
    if not _valid_nonneg_int(delta_tokens):
        return requested_reserve

    # --- LIMIT fields must exist and be valid nonneg ints.
    for field in _LIMIT_FIELDS:
        if field not in budget:
            return requested_reserve
        if not _valid_nonneg_int(budget[field]):
            return requested_reserve

    max_model_calls: int = budget["maxModelCalls"]
    reserve_model_calls: int = budget["reserveModelCalls"]
    max_tokens: int = budget["maxTokens"]
    reserve_tokens: int = budget["reserveTokens"]

    # --- maxModelCalls / maxTokens strictly positive.
    if max_model_calls <= 0 or max_tokens <= 0:
        return requested_reserve

    # --- reserves must not exceed totals.
    if reserve_model_calls > max_model_calls or reserve_tokens > max_tokens:
        return requested_reserve

    # --- USED counters (default 0 when key missing).
    used: dict[str, int] = {}
    for field in _USED_FIELDS:
        val: Any = budget.get(field, 0)
        if not _valid_nonneg_int(val):
            return requested_reserve
        used[field] = val

    model_calls = used["modelCalls"]
    reserved_model_calls = used["reservedModelCalls"]
    normal_tokens = used["normalTokens"]
    tokens = used["tokens"]

    # --- Condition 1: reserve must actually be exhausted for this request.
    if reserved_model_calls + delta_model_calls <= reserve_model_calls:
        return requested_reserve

    # --- Condition 2: normal model-call capacity sufficient.
    if model_calls + delta_model_calls > max_model_calls - reserve_model_calls:
        return requested_reserve

    # --- Condition 3: combined normal + reserved + new within total.
    if model_calls + reserved_model_calls + delta_model_calls > max_model_calls:
        return requested_reserve

    # --- Condition 4: normal token capacity sufficient.
    if normal_tokens + delta_tokens > max_tokens - reserve_tokens:
        return requested_reserve

    # --- Condition 5: total token capacity sufficient.
    if tokens + delta_tokens > max_tokens:
        return requested_reserve

    # All conditions satisfied – advise normal pool.
    return False
