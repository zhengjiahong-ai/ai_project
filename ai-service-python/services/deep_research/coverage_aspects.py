"""Validate the audit trail for individual answer requirements, not semantics."""
from services.deep_research.answer_coverage import _bindings_supported, _known_claims_by_id


def invalid_coverage_aspects(verdicts, claims, evidence_rows, questions, *, request_only_obligations=()):
    """A covered verdict requires explicit, grounded, individually covered aspects.

    This cannot prove that the model found every essential aspect. It prevents
    a bare overall verdict, invented source text or missing subcheck from
    silently becoming a completed answer.
    """
    known = _known_claims_by_id(claims)
    evidence = {}
    for row in evidence_rows:
        if not isinstance(row, dict):
            continue
        eid = row.get('evidenceId')
        if not isinstance(eid, str) or not eid:
            continue
        evidence[eid] = row if eid not in evidence else None
    invalid = []
    for verdict in verdicts:
        if not isinstance(verdict, dict) or verdict.get('status') != 'covered':
            continue
        aspects = verdict.get('aspects')
        valid = isinstance(aspects, list) and bool(aspects)
        seen = set()
        source_based = False
        metadata_only = bool(aspects)
        for aspect in aspects if isinstance(aspects, list) else []:
            if not isinstance(aspect, dict):
                valid = False
                continue
            identity = aspect.get('aspectId')
            if not isinstance(identity, str) or not identity or identity in seen:
                valid = False
            else:
                seen.add(identity)
            if not isinstance(aspect.get('requirement'), str) or not aspect['requirement'].strip():
                valid = False
            if aspect.get('status') != 'covered' or not _bindings_supported(aspect.get('bindings'), known):
                valid = False
            basis = aspect.get('basis')
            if not isinstance(basis, dict) or 'referenceError' in basis:
                valid = False
                metadata_only = False
                continue
            if basis.get('kind') == 'source_metadata':
                row = evidence.get(basis.get('evidenceId')) if isinstance(basis.get('evidenceId'), str) else None
                request_excerpt = basis.get('requestExcerpt')
                supported = (row is not None and basis.get('field') == 'accessLevel'
                    and basis.get('value') in ('fulltext', 'abstract', 'user_note')
                    and row.get('accessLevel') == basis.get('value')
                    and isinstance(request_excerpt, str) and len(request_excerpt.strip()) >= 8
                    and any(request_excerpt in q for q in questions if isinstance(q, str)))
                # Metadata belongs to evidence cited by the bound answer, not an
                # unrelated downloaded paper. Mixed content still needs prose.
                bindings = aspect.get('bindings')
                supported = supported and isinstance(bindings, list) and bool(bindings) and all(
                    isinstance(b, dict) and isinstance(b.get('claimId'), str)
                    and isinstance(known.get(b['claimId']), dict)
                    and basis.get('evidenceId') in known[b['claimId']].get('evidenceRefs', [])
                    for b in bindings)
                valid = valid and supported
                continue
            metadata_only = False
            excerpt = basis.get('excerpt')
            if not isinstance(excerpt, str) or not excerpt.strip():
                valid = False
                continue
            if basis.get('kind') == 'request':
                valid = valid and any(excerpt in q for q in questions if isinstance(q, str))
            elif basis.get('kind') == 'source':
                eid = basis.get('evidenceId')
                row = evidence.get(eid) if isinstance(eid, str) else None
                if not row or len(excerpt.strip()) < 8:
                    valid = False
                    continue
                context = row.get('sourceContext') or {}
                text = context.get('before', '') + row.get('quote', '') + context.get('after', '')
                valid = valid and excerpt in text
                source_based = source_based or excerpt in text
            else:
                valid = False
        bindings = verdict.get('bindings')
        factual = any(isinstance(b, dict) and isinstance(b.get('claimId'), str)
            and isinstance(known.get(b['claimId']), dict)
            and known[b['claimId']].get('kind') in {'reported', 'inference'}
            for b in bindings) if isinstance(bindings, list) else False
        if (evidence_rows and factual and not source_based and not metadata_only
                and verdict.get('obligationId') not in request_only_obligations):
            valid = False
        if not valid:
            invalid.append(verdict.get('obligationId'))
    return invalid
