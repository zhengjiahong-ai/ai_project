"""Coverage repair helpers for the deep research pipeline.

These functions are pure and never mutate their inputs. They reconcile
factual verification results with audit-detected coverage gaps so callers can
account for incomplete answers without re-labelling factually verified claims
as factual failures. The caller is expected to keep the ORIGINAL verification
available as a fallback; the values returned here only describe the repair
context (which accepted claims are being withheld for follow-up, and why).
"""

import copy


def _claim_id(claim):
    """Return the stable identifier for a claim or rejection row."""
    if not isinstance(claim, dict):
        return None
    value = claim.get('claimId')
    return value if isinstance(value, str) and value else None


def _rejected_row_id(row):
    return _claim_id(row)


def prepare_coverage_repair(report, verification, audit):
    """Withhold accepted claims needed to close audit gaps.

    Returns a new verification-shaped dict whose ``accepted`` list drops the
    targeted claims and whose ``rejected`` list is the union of the original
    rejections plus one coverage row per targeted claim.
    """
    report = report or {}
    verification = verification or {}
    audit = audit or {}

    report_claims = report.get("claims") or []
    report_ids = set()
    for claim in report_claims:
        cid = _claim_id(claim)
        if cid is not None:
            report_ids.add(cid)

    accepted = verification.get("accepted") or []
    rejected = verification.get("rejected") or []
    gaps = [g for g in audit.get("gaps", []) if isinstance(g, dict)]
    verdicts = audit.get("verdicts") or []

    accepted_by_id = {}
    accepted_order = []
    for claim in accepted:
        cid = _claim_id(claim)
        if cid is not None and cid not in accepted_by_id:
            accepted_by_id[cid] = claim
            accepted_order.append(cid)

    has_specific_gap = any(not gap.get("wholeQuestion", False) for gap in gaps)
    if has_specific_gap:
        active_gaps = [gap for gap in gaps if not gap.get("wholeQuestion", False)]
    else:
        active_gaps = list(gaps)

    bindings_by_obligation = {}
    for verdict in verdicts:
        if not isinstance(verdict, dict) or not isinstance(verdict.get('obligationId'), str):
            continue
        obligation_id = verdict.get("obligationId")
        bindings = verdict.get('bindings')
        for binding in bindings if isinstance(bindings, list) else []:
            if not isinstance(binding, dict) or not isinstance(binding.get('claimId'), str):
                continue
            bindings_by_obligation.setdefault(obligation_id, []).append(
                binding.get("claimId")
            )

    accepted_report_ids = [cid for cid in accepted_order if cid in report_ids]
    original_rejected_ids = {_claim_id(row) for row in rejected}

    # Map each targeted accepted claim id to the ordered, unique list of gap
    # questions that implicated it.
    targets = {}
    for gap in active_gaps:
        obligation_id = gap.get("obligationId")
        question = gap.get("question")
        details = gap.get('missingAspects')
        questions = [question, *[value for value in details if isinstance(value, str) and value.strip()]] \
            if isinstance(details, list) else [question]
        gap_targets = set()

        for cid in bindings_by_obligation.get(obligation_id, []):
            if cid in accepted_by_id and cid in report_ids:
                gap_targets.add(cid)

        for cid in accepted_order:
            if cid not in report_ids:
                continue
            claim = accepted_by_id[cid]
            if obligation_id in (claim.get("obligationIds") or []):
                gap_targets.add(cid)

        # A missing obligation may already have a rejected draft claim. Revise
        # that claim instead of making an unrelated accepted fact answer it.
        rejected_candidates = set()
        for claim in report_claims:
            cid = _claim_id(claim)
            if cid in original_rejected_ids and isinstance(claim, dict) and obligation_id in (claim.get('obligationIds') or []):
                rejected_candidates.add(cid)
        if rejected_candidates:
            # First repair already-failed statements for this obligation instead
            # of rewriting every accepted statement sharing its retrieval label.
            # This is scheduling, not coverage approval: the merged answer must
            # still pass the independent full-question coverage audit afterwards.
            gap_targets = rejected_candidates

        if not gap_targets:
            # Conservative fallback: an unmapped specific requirement withholds
            # every accepted claim already present in the report.
            gap_targets = set(accepted_report_ids)

        for cid in gap_targets:
            bucket = targets.setdefault(cid, [])
            for missing_question in questions:
                if missing_question not in bucket:
                    bucket.append(missing_question)

    targeted_ids = set(targets.keys())

    out_accepted = []
    for claim in accepted:
        if _claim_id(claim) in targeted_ids:
            continue
        out_accepted.append(copy.deepcopy(claim))

    out_rejected = [copy.deepcopy(row) for row in rejected]
    existing_rejected_ids = set()
    for row in out_rejected:
        rid = _rejected_row_id(row)
        if rid is not None:
            existing_rejected_ids.add(rid)

    # Merge coverage detail into any pre-existing rejection for the same id,
    # preserving the original factual reason.
    for cid, questions in targets.items():
        if cid not in existing_rejected_ids:
            continue
        for row in out_rejected:
            if _rejected_row_id(row) == cid:
                missing = row.setdefault("missingQuestions", [])
                for question in questions:
                    if question not in missing:
                        missing.append(question)
                row.setdefault("reason", "answer_incomplete")
                break

    order_index = {cid: idx for idx, cid in enumerate(accepted_order)}
    new_target_ids = sorted(
        (cid for cid in targets if cid not in existing_rejected_ids),
        key=lambda cid: order_index.get(cid, float("inf")),
    )
    for cid in new_target_ids:
        out_rejected.append(
            {
                "claimId": cid,
                "reason": "answer_incomplete",
                "missingQuestions": list(targets[cid]),
            }
        )

    # Hints select prompt candidates only; repair independently enforces the
    # original source/version whitelist before exposing or accepting a citation.
    for row in out_rejected:
        claim = next((c for c in report_claims if _claim_id(c) == _rejected_row_id(row)), {})
        hints = []
        for gap in active_gaps:
            if gap.get('obligationId') in (claim.get('obligationIds') or []):
                refs = gap.get('aspectEvidenceRefs')
                if isinstance(refs, list):
                    hints.extend(ref for ref in refs if isinstance(ref, str) and ref not in hints)
        if hints:
            row['missingEvidenceRefs'] = hints
    return {"accepted": out_accepted, "rejected": out_rejected}


def merge_verified_revisions(initial, checked):
    """Merge a checked revision back into the initial verification.

    Only identifiers already known to ``initial`` can be merged. Valid,
    uniquely presented checked claims replace accepted originals or rescue
    rejected rows; anything unknown, duplicated, or unrepaired leaves the
    initial rows untouched.
    """
    initial = initial or {}
    checked = checked or {}

    init_accepted = initial.get("accepted") or []
    init_rejected = initial.get("rejected") or []
    checked_accepted = checked.get("accepted") or []
    initial_conflicts = ({_claim_id(c) for c in init_accepted} &
                         {_claim_id(c) for c in init_rejected}) - {None}
    checked_conflicts = ({_claim_id(c) for c in checked_accepted} &
                         {_claim_id(c) for c in (checked.get('rejected') or [])}) - {None}

    known_ids = set()
    for claim in init_accepted:
        cid = _claim_id(claim)
        if cid is not None:
            known_ids.add(cid)
    for row in init_rejected:
        rid = _rejected_row_id(row)
        if rid is not None:
            known_ids.add(rid)

    counts = {}
    for claim in checked_accepted:
        cid = _claim_id(claim)
        if cid is not None:
            counts[cid] = counts.get(cid, 0) + 1
    duplicated_ids = {cid for cid, count in counts.items() if count > 1} | initial_conflicts | checked_conflicts

    checked_valid = {}
    for claim in checked_accepted:
        cid = _claim_id(claim)
        if cid is None or cid in duplicated_ids or cid not in known_ids:
            continue
        checked_valid[cid] = claim

    initial_rejected_ids = set()
    for row in init_rejected:
        rid = _rejected_row_id(row)
        if rid is not None:
            initial_rejected_ids.add(rid)

    result_accepted = []
    seen = set()
    for claim in init_accepted:
        cid = _claim_id(claim)
        if cid in initial_conflicts:
            continue
        entry = copy.deepcopy(checked_valid[cid]) if cid in checked_valid else copy.deepcopy(claim)
        if cid not in seen:
            result_accepted.append(entry)
            if cid is not None:
                seen.add(cid)

    for claim in checked_accepted:
        cid = _claim_id(claim)
        if cid is None or cid in duplicated_ids or cid not in known_ids:
            continue
        if cid in initial_rejected_ids and cid not in seen:
            result_accepted.append(copy.deepcopy(claim))
            seen.add(cid)

    result_rejected = []
    rejected_seen = set()
    for row in init_rejected:
        rid = _rejected_row_id(row)
        if rid is not None and rid in checked_valid:
            continue
        if rid in rejected_seen:
            continue
        rejected_seen.add(rid)
        result_rejected.append(copy.deepcopy(row))

    return {"accepted": result_accepted, "rejected": result_rejected}
