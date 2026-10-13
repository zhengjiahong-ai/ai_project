"""Metric-scope grounding for deep-research briefs.

Structural validation only: each requested metric domain must be
accompanied by an *exact* excerpt drawn from the user question.  This
does **not** assess semantic relevance; a downstream whole-question
completeness audit remains required.
"""

from __future__ import annotations

from typing import Any, Dict, List

_CANONICAL_ORDER: tuple = ("quality", "speed", "storage")

_PROTOCOL_REQUIREMENTS: Dict[str, str] = {
    "quality": (
        "For each quality metric, state its direction (higher-is-better or "
        "lower-is-better) and specify the image/view aggregation level; do "
        "not average metrics that are incompatible in scale or meaning."
    ),
    "speed": (
        "Report the device, resolution, warmup procedure, synchronization "
        "method, timed region, and number of repetitions for every speed "
        "measurement."
    ),
    "storage": (
        "List the included files or model representation, and state the "
        "accounting boundaries and units used for the storage measurement."
    ),
}


def _all_domains() -> List[str]:
    """Return every allowed domain in canonical order (fresh list)."""
    return list(_CANONICAL_ORDER)


def grounded_metric_domains(raw: Any, question: Any) -> List[str]:
    """Validate *raw* against *question* and return domains in canonical order.

    Returns all three domains whenever any entry is malformed, the domain
    is unknown or duplicated, or the excerpt is not an exact substring of
    *question*.  Inputs are never mutated.
    """
    # question must be a non-empty string
    if not isinstance(question, str) or not question:
        return _all_domains()

    # raw must be a non-empty list
    if not isinstance(raw, list) or len(raw) == 0:
        return _all_domains()

    seen: set = set()

    for entry in raw:
        if not isinstance(entry, dict):
            return _all_domains()

        domain = entry.get("domain")
        excerpt = entry.get("requestExcerpt")

        # domain must be a known allowed string
        if not isinstance(domain, str) or domain not in _CANONICAL_ORDER:
            return _all_domains()

        # duplicate domain → fallback
        if domain in seen:
            return _all_domains()

        # excerpt must be a non-blank string
        if not isinstance(excerpt, str) or not excerpt.strip():
            return _all_domains()

        # exact (case-sensitive, no normalisation) substring check
        if excerpt not in question:
            return _all_domains()

        seen.add(domain)

    return [d for d in _CANONICAL_ORDER if d in seen]


def metric_protocol_requirements(domains: Any = None) -> Dict[str, str]:
    """Map each selected domain to its English protocol requirement.

    *domains* must be a list of known, unique domain strings to select a
    subset (returned in canonical order).  ``None``, an empty list, or any
    malformed value falls back to all three domains.
    """
    if domains is None or not isinstance(domains, list) or len(domains) == 0:
        selected = list(_CANONICAL_ORDER)
    else:
        seen: set = set()
        valid = True
        for d in domains:
            if not isinstance(d, str) or d not in _CANONICAL_ORDER or d in seen:
                valid = False
                break
            seen.add(d)
        if not valid or not seen:
            selected = list(_CANONICAL_ORDER)
        else:
            selected = [d for d in _CANONICAL_ORDER if d in seen]

    return {d: _PROTOCOL_REQUIREMENTS[d] for d in selected}
