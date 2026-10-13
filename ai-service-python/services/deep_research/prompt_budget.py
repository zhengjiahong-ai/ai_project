"""Byte-budget fitting for deep-research evidence prompts.

Provides :func:`fit_evidence_prompt` which selects a subset of evidence rows
whose rendered prompt stays within a UTF-8 byte budget.  The *render* callback
is trusted, pure, and controls all instruction text; this module never
truncates quotes or mutates caller-supplied inputs.
"""

from __future__ import annotations

from typing import Callable

__all__ = ["fit_evidence_prompt"]


def fit_evidence_prompt(
    rows: list[dict],
    render: Callable[[list[dict]], str],
    max_bytes: int = 24000,
) -> tuple[str, list[dict]]:
    """Fit evidence rows into a rendered prompt within *max_bytes*.

    Parameters
    ----------
    rows:
        Evidence row dicts (must not be mutated by this function).
    render:
        Pure callback mapping a list of selected rows to the complete prompt
        string (including all instruction/question text).
    max_bytes:
        Maximum allowed UTF-8 byte length of the rendered prompt.

    Returns
    -------
    tuple[str, list[dict]]
        The fitting prompt and the selected row dicts used to produce it.

    Raises
    ------
    ValueError
        For invalid inputs or when fixed instruction content alone exceeds
        the budget (``'prompt_fixed_content_too_large'``).
    """

    # ---- input validation ------------------------------------------------
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise ValueError("max_bytes must be a positive integer")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    if not callable(render):
        raise ValueError("render must be callable")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list of dicts")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("rows must be a list of dicts")

    # ---- helpers ----------------------------------------------------------
    def _render(selected: list[dict]) -> str:
        prompt = render(selected)
        if not isinstance(prompt, str):
            raise ValueError("render must return a string")
        return prompt

    def _byte_len(text: str) -> int:
        return len(text.encode("utf-8"))

    # ---- fixed-content guard ----------------------------------------------
    empty_prompt = _render([])
    if _byte_len(empty_prompt) > max_bytes:
        raise ValueError("prompt_fixed_content_too_large")

    # ---- attempt 1: all original rows ------------------------------------
    full_prompt = _render(rows)
    if _byte_len(full_prompt) <= max_bytes:
        return full_prompt, [dict(r) for r in rows]

    # ---- attempt 2: strip optional non-empty sourceContext ----------------
    compact_rows: list[dict] = []
    for row in rows:
        compact = dict(row)
        ctx = row.get("sourceContext")
        if ctx is not None and ctx:
            compact["sourceContext"] = {}
            compact["contextOmitted"] = True
        compact_rows.append(compact)

    # Greedily accumulate in original balanced order; skip oversized rows.
    selected: list[dict] = []
    kept_original_indices: list[int] = []
    for i, crow in enumerate(compact_rows):
        candidate = selected + [crow]
        if _byte_len(_render(candidate)) <= max_bytes:
            selected.append(crow)
            kept_original_indices.append(i)

    # ---- restoration pass -------------------------------------------------
    # Re-instate each kept row's exact original sourceContext in input order,
    # accepting the restoration only when the full prompt still fits.
    result_rows: list[dict] = [dict(r) for r in selected]
    for pos, orig_idx in enumerate(kept_original_indices):
        orig_ctx = rows[orig_idx].get("sourceContext")
        if orig_ctx is not None and orig_ctx:
            trial = [dict(r) for r in result_rows]
            trial[pos] = dict(rows[orig_idx])
            if _byte_len(_render(trial)) <= max_bytes:
                result_rows = trial

    final_prompt = _render(result_rows)
    return final_prompt, result_rows
