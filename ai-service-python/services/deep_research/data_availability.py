"""Structural data-availability gate for deep-research claims.

Validates that a verdict's ``dataAvailability`` block is structurally
consistent with the claim's execution spec and the visible evidence.

This is a *bound audit of data capacity only*.  It never asserts or proves
semantic correctness; the caller's semantic model must separately verify
count/name units and exact dataset/subset identity.
"""
from __future__ import annotations

from typing import Any, List, Optional

__all__ = ["validate_data_availability"]

_ENGLISH_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}

_APPLICABLE_KINDS = frozenset({"proposal", "suggestion", "hypothesis"})


def _is_applicable(claim: Any) -> bool:
    if not isinstance(claim, dict):
        return False
    if not isinstance(claim.get("kind"), str) or claim.get("kind") not in _APPLICABLE_KINDS:
        return False
    if claim.get("designRole") != "data":
        return False
    if claim.get("designContractVersion") != 2:
        return False
    return True


def _parse_count_token(stripped: str) -> Optional[int]:
    """Parse a stripped token into a positive int, or None if unsupported."""
    if not stripped:
        return None
    if stripped.isascii() and stripped.isdigit():
        try:
            val = int(stripped)
        except ValueError:
            return None
        return val if val > 0 else None
    return _ENGLISH_NUMBERS.get(stripped.lower())


def _digit_boundary_ok(text: str, start: int, end: int) -> bool:
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] in '_.,+-'):
        return False
    if end < len(text) and (text[end].isalnum() or text[end] in '_%'):
        return False
    if end + 1 < len(text) and text[end] in '.,' and text[end + 1].isdigit():
        return False
    return True


def _word_boundary_ok(text: str, start: int, end: int) -> bool:
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] == '_'):
        return False
    if end < len(text) and (text[end].isalnum() or text[end] == '_'):
        return False
    return True


def _unicode_word_boundary_ok(text: str, start: int, end: int) -> bool:
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        return False
    if end < len(text) and (text[end].isalnum() or text[end] == "_"):
        return False
    return True


def _token_in_quote_with_boundary(quote: str, token: str) -> bool:
    """Check *token* appears in *quote* with appropriate token boundaries."""
    is_digit = token.isascii() and token.isdigit()
    pos = 0
    while True:
        idx = quote.find(token, pos)
        if idx == -1:
            return False
        end = idx + len(token)
        if is_digit:
            if _digit_boundary_ok(quote, idx, end):
                return True
        else:
            if _word_boundary_ok(quote, idx, end):
                return True
        pos = idx + 1


def _name_in_quote_with_boundary(quote: str, name: str) -> bool:
    """Case-sensitive search with Unicode word boundaries."""
    pos = 0
    while True:
        idx = quote.find(name, pos)
        if idx == -1:
            return False
        end = idx + len(name)
        if _unicode_word_boundary_ok(quote, idx, end):
            return True
        pos = idx + 1


def _check_sorted_first(
    da: dict, scenes: dict, da_quote: str, scope_quote: str
) -> List[str]:
    errors: List[str] = []

    available_count = da.get("availableCount")
    if (
        not isinstance(available_count, int)
        or isinstance(available_count, bool)
        or available_count < 1
    ):
        return ["DA_AVAILABLE_COUNT_INVALID"]

    count_quote = da.get("countQuote")
    if not isinstance(count_quote, str):
        return ["DA_COUNTQUOTE_MISSING"]
    stripped_cq = count_quote.strip()
    if not stripped_cq:
        return ["DA_COUNTQUOTE_EMPTY"]

    parsed = _parse_count_token(stripped_cq)
    if parsed is None:
        return ["DA_COUNTQUOTE_UNPARSEABLE"]

    if count_quote not in da_quote:
        return ["DA_COUNTQUOTE_NOT_IN_QUOTE"]

    if not _token_in_quote_with_boundary(da_quote, stripped_cq):
        return ["DA_COUNTQUOTE_NO_BOUNDARY"]

    if parsed != available_count:
        errors.append("DA_COUNT_MISMATCH")

    if scope_quote.strip() == stripped_cq:
        errors.append("DA_SCOPE_IS_COUNTQUOTE")

    req_count = scenes.get("count")
    if scenes.get('mode') == 'all' and req_count != available_count:
        errors.append('DA_COMPLETE_COUNT_MISMATCH')
    if (
        isinstance(req_count, int)
        and not isinstance(req_count, bool)
        and req_count > available_count
    ):
        errors.append("DA_INSUFFICIENT_COUNT")

    return errors


def _check_named(da: dict, scenes: dict, da_quote: str) -> List[str]:
    errors: List[str] = []

    available_names = da.get("availableNames")
    if not isinstance(available_names, list) or len(available_names) == 0:
        return ["DA_NAMES_EMPTY"]

    seen: set = set()
    for name in available_names:
        if not isinstance(name, str) or not name.strip():
            return ["DA_NAMES_MALFORMED"]
        if name in seen:
            return ["DA_NAMES_NOT_UNIQUE"]
        seen.add(name)

    for name in available_names:
        if not _name_in_quote_with_boundary(da_quote, name):
            return ["DA_NAME_NOT_IN_QUOTE"]

    req_names = scenes.get("names")
    if isinstance(req_names, list):
        for rn in req_names:
            if rn not in available_names:
                return ["DA_NAME_NOT_AVAILABLE"]

    return errors


def validate_data_availability(
    claim: Any, verdict: Any, visible_evidence: Any
) -> List[str]:
    """Validate structural data-availability constraints.

    Returns a list of deterministic error-code strings.  An empty list means
    the structural gate passed.  This gate never proves semantic correctness.
    """
    if not _is_applicable(claim):
        return []

    exec_spec = claim.get("executionSpec")
    if not isinstance(exec_spec, dict):
        return ["DA_MALFORMED_EXECUTION_SPEC"]

    scenes = exec_spec.get("scenes")
    if not isinstance(scenes, dict):
        return ["DA_MALFORMED_SCENES"]

    mode = scenes.get("mode")
    if mode in ('sorted_first', 'all'):
        if mode == 'all' and set(scenes) != {'mode', 'count'}:
            return ['DA_CONFLICTING_COMPLETE_SELECTION']
        req_count = scenes.get("count")
        if (
            not isinstance(req_count, int)
            or isinstance(req_count, bool)
            or req_count < 1
        ):
            return ["DA_MALFORMED_REQUESTED_COUNT"]
    elif mode == "named":
        req_names = scenes.get("names")
        if not isinstance(req_names, list) or len(req_names) == 0:
            return ["DA_MALFORMED_REQUESTED_NAMES"]
        for n in req_names:
            if not isinstance(n, str) or not n.strip():
                return ["DA_MALFORMED_REQUESTED_NAMES"]
    else:
        return ["DA_MODE_UNKNOWN"]

    if not isinstance(verdict, dict):
        return ["DA_MALFORMED_VERDICT"]

    da = verdict.get("dataAvailability")
    if da is None:
        return ["DA_MISSING"]
    if not isinstance(da, dict):
        return ["DA_MALFORMED_DATA_AVAILABILITY"]

    evidence_id = da.get("evidenceId")
    if not isinstance(evidence_id, str) or not evidence_id:
        return ["DA_EVIDENCE_ID_INVALID"]

    if not isinstance(visible_evidence, list):
        return ["DA_EVIDENCE_LIST_INVALID"]

    seen_ids: set = set()
    matched: Optional[dict] = None
    for ev in visible_evidence:
        if not isinstance(ev, dict):
            continue
        eid = ev.get("evidenceId")
        if not isinstance(eid, str):
            continue
        if eid in seen_ids:
            return ["DA_DUPLICATE_IDENTITY"]
        seen_ids.add(eid)
        if eid == evidence_id:
            matched = ev

    if matched is None:
        return ["DA_EVIDENCE_NOT_FOUND"]

    if matched.get("accessLevel") != "fulltext":
        return ["DA_NOT_FULLTEXT"]

    evidence_refs = claim.get("evidenceRefs")
    if not isinstance(evidence_refs, list):
        return ["DA_MALFORMED_EVIDENCE_REFS"]
    if evidence_id not in evidence_refs:
        return ["DA_NOT_IN_EVIDENCE_REFS"]

    ev_quote = matched.get("quote")
    if not isinstance(ev_quote, str):
        return ["DA_EVIDENCE_QUOTE_INVALID"]

    da_quote = da.get("quote")
    if not isinstance(da_quote, str) or not da_quote.strip():
        return ["DA_QUOTE_BLANK"]
    if da_quote not in ev_quote:
        return ["DA_QUOTE_NOT_IN_SOURCE"]

    scope_quote = da.get("scopeQuote")
    if not isinstance(scope_quote, str) or not scope_quote.strip():
        return ["DA_SCOPE_BLANK"]
    if scope_quote not in da_quote:
        return ["DA_SCOPE_NOT_IN_QUOTE"]

    if mode in ('sorted_first', 'all'):
        count_quote = da.get('countQuote')
        if (isinstance(count_quote, str) and count_quote.strip()
                and not _token_in_quote_with_boundary(ev_quote, count_quote.strip())):
            return ['DA_COUNTQUOTE_NO_BOUNDARY']
        return _check_sorted_first(da, scenes, da_quote, scope_quote)
    names = da.get('availableNames')
    if isinstance(names, list) and any(isinstance(name, str) and name.strip()
            and not _name_in_quote_with_boundary(ev_quote, name) for name in names):
        return ['DA_NAME_NOT_IN_QUOTE']
    return _check_named(da, scenes, da_quote)
