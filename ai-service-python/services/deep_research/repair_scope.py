"""Repair evidence scope for academic research claims.

Returns a candidate whitelist mapping claimId -> ordered evidenceId list.
This is NOT verification; downstream integration verifies independently.
"""


def repair_evidence_scope(claims, evidence, max_additions=12):
    """Return dict mapping each unique claimId to an ordered allowed evidenceId list.

    Preserves existing unique string evidenceRefs in original order, then appends
    up to *max_additions* candidate evidence rows that satisfy all anchor and
    identity constraints.  Never mutates inputs.
    """
    # --- clamp max_additions ---------------------------------------------------
    if not isinstance(max_additions, int) or isinstance(max_additions, bool):
        max_additions = 12
    max_additions = max(0, min(24, max_additions))

    # --- defensive input coercion ----------------------------------------------
    if not isinstance(claims, list):
        claims = []
    if not isinstance(evidence, list):
        evidence = []

    # --- index evidence rows, detect duplicate evidenceIds ----------------------
    evidence_id_counts = {}
    evidence_by_id = {}
    for row in evidence:
        if not isinstance(row, dict):
            continue
        eid = row.get("evidenceId")
        if not isinstance(eid, str) or not eid:
            continue
        evidence_id_counts[eid] = evidence_id_counts.get(eid, 0) + 1
        if evidence_id_counts[eid] == 1:
            evidence_by_id[eid] = row
    ambiguous_eids = {eid for eid, cnt in evidence_id_counts.items() if cnt > 1}

    # --- detect duplicate claimIds ---------------------------------------------
    claim_id_counts = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cid = claim.get("claimId")
        if not isinstance(cid, str) or not cid:
            continue
        claim_id_counts[cid] = claim_id_counts.get(cid, 0) + 1
    ambiguous_cids = {cid for cid, cnt in claim_id_counts.items() if cnt > 1}

    # --- helper: extract valid anchor pair from an evidence row ----------------
    def _anchor_pair(row):
        verification = row.get("verification")
        if not isinstance(verification, dict):
            return None
        if verification.get("literal") != "passed":
            return None
        if row.get("accessLevel") != "fulltext":
            return None
        swid = row.get("sourceWorkId")
        svid = row.get("sourceVersionId")
        if not isinstance(swid, str) or not swid:
            return None
        if not isinstance(svid, str) or not svid:
            return None
        return (swid, svid)

    # --- build result ----------------------------------------------------------
    result = {}

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cid = claim.get("claimId")
        if not isinstance(cid, str) or not cid:
            continue
        if cid in ambiguous_cids or cid in result:
            continue

        # Preserve existing unique string evidenceRefs in original order
        raw_refs = claim.get("evidenceRefs")
        if not isinstance(raw_refs, list):
            raw_refs = []
        seen_refs = set()
        ordered_refs = []
        for ref in raw_refs:
            if isinstance(ref, str) and ref and ref not in seen_refs:
                seen_refs.add(ref)
                ordered_refs.append(ref)

        # Gather obligation strings for this claim
        raw_obligations = claim.get("obligationIds")
        if not isinstance(raw_obligations, list):
            raw_obligations = []
        obligations = set()
        for ob in raw_obligations:
            if isinstance(ob, str) and ob:
                obligations.add(ob)

        # No obligations -> no expansion
        if not obligations or claim.get('kind') not in {'reported', 'inference'}:
            result[cid] = list(ordered_refs)
            continue

        # Determine anchor (sourceWorkId, sourceVersionId) pairs
        anchor_pairs = set()
        for ref_eid in ordered_refs:
            if ref_eid in ambiguous_eids:
                continue
            row = evidence_by_id.get(ref_eid)
            if row is None:
                continue
            pair = _anchor_pair(row)
            if pair is not None:
                anchor_pairs.add(pair)

        # No trusted original sources -> no expansion
        if not anchor_pairs:
            result[cid] = list(ordered_refs)
            continue

        # Retrieval labels are not exclusive relevance judgements. Balance the
        # same source's acquired passages across labels so later subquestions
        # can supply a condition omitted by the original retrieval.
        from services.deep_research.selection import balanced_sample
        candidates = []
        added = set()
        for row in evidence:
            if not isinstance(row, dict):
                continue
            eid = row.get("evidenceId")
            if not isinstance(eid, str) or not eid:
                continue
            if eid in ambiguous_eids or eid in seen_refs or eid in added:
                continue
            pair = _anchor_pair(row)
            if pair is None or pair not in anchor_pairs:
                continue
            quote = row.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                continue
            row_obligations = row.get("obligationIds")
            if not isinstance(row_obligations, list):
                continue
            if not any(isinstance(ob, str) and ob for ob in row_obligations):
                continue
            candidates.append(row)
            added.add(eid)

        selected = balanced_sample(candidates,
            lambda row: (row['sourceWorkId'], row['sourceVersionId'],
                         tuple(sorted(ob for ob in row['obligationIds'] if isinstance(ob, str) and ob))),
            max_additions) if max_additions else []
        result[cid] = ordered_refs + [row['evidenceId'] for row in selected]

    return result
