"""Audit whether final-answer claims actually cover planned obligations.

This helper performs identity and literal-support validation only.  It never
judges semantics, fetches evidence, or invokes models.  An obligation gap is
closed exclusively when the audit trail lines up: exactly one verdict for the
obligation, status ``covered``, and every binding citing a unique accepted
claim whose text (or serialized conditions) literally contains the excerpt.
"""

from __future__ import annotations

import json

__all__ = ["answer_coverage_gaps"]

_MISSING_EVIDENCE = "最终回答尚未完整回应这一问题"
_STAGE = "answer"
_MIN_EXCERPT_LENGTH = 8
_COVERED = "covered"


def _serialize_conditions(claim):
    try:
        return json.dumps(claim.get("conditions"), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return None


def _known_claims_by_id(claims):
    """Map claimId -> claim, poisoning identifiers that appear more than once."""
    known = {}
    if not isinstance(claims, list):
        return known
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claimId")
        if not isinstance(claim_id, str) or not claim_id:
            continue
        if claim_id in known:
            known[claim_id] = None
        else:
            known[claim_id] = claim
    return known


def _bindings_supported(bindings, known_claims):
    if not isinstance(bindings, list) or not bindings:
        return False
    for binding in bindings:
        if not isinstance(binding, dict):
            return False
        if 'referenceError' in binding:
            return False
        claim_id = binding.get("claimId")
        if not isinstance(claim_id, str):
            return False
        claim = known_claims.get(claim_id)
        if claim is None:
            return False
        excerpt = binding.get("excerpt")
        if not isinstance(excerpt, str):
            return False
        stripped = excerpt.strip()
        if len(stripped) < _MIN_EXCERPT_LENGTH:
            return False
        haystacks = []
        text = claim.get("text")
        if isinstance(text, str):
            haystacks.append(text)
        serialized = _serialize_conditions(claim)
        if serialized is not None:
            haystacks.append(serialized)
        if not any(stripped in haystack for haystack in haystacks):
            return False
    return True


def _verdict_closes_obligation(verdict, known_claims):
    if not isinstance(verdict, dict):
        return False
    if verdict.get("status") != _COVERED:
        return False
    return _bindings_supported(verdict.get("bindings"), known_claims)


def _plan_obligations(plan):
    obligations = []
    if not isinstance(plan, list):
        return obligations
    for item in plan:
        if not isinstance(item, dict):
            continue
        item_obligations = item.get("obligations")
        if not isinstance(item_obligations, list):
            continue
        for obligation in item_obligations:
            if isinstance(obligation, dict):
                obligations.append(obligation)
    return obligations


def answer_coverage_gaps(plan, claims, verdicts):
    """Return the obligation gaps left by the final answer.

    ``plan`` holds validated items with ``obligations``; ``claims`` are the
    accepted final claims; ``verdicts`` are answer-completeness judgements.
    No input is mutated and nothing here performs retrieval or model calls.
    """
    known_claims = _known_claims_by_id(claims)

    verdicts_by_obligation = {}
    if isinstance(verdicts, list):
        for verdict in verdicts:
            if not isinstance(verdict, dict):
                continue
            obligation_id = verdict.get("obligationId")
            if not isinstance(obligation_id, str) or not obligation_id:
                continue
            verdicts_by_obligation.setdefault(obligation_id, []).append(verdict)

    gaps = []
    for obligation in _plan_obligations(plan):
        obligation_id = obligation.get("obligationId")
        matching = []
        if isinstance(obligation_id, str):
            matching = verdicts_by_obligation.get(obligation_id, [])
        closed = len(matching) == 1 and _verdict_closes_obligation(matching[0], known_claims)
        if not closed:
            gaps.append(
                {
                    "obligationId": obligation_id,
                    "question": obligation.get("question"),
                    "missingEvidence": _MISSING_EVIDENCE,
                    "stage": _STAGE,
                }
            )
    return gaps
