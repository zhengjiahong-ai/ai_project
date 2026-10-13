"""Evidence-only gate: reject missing or unsupported design-audit quotes."""

import json

REQUIRED = {
    "groups": ("group_construction", "intervention_levels"),
    "data": ("scenes", "split", "seeds", "sampling_unit"),
    "metrics": ("quality_protocol", "speed_protocol", "storage_protocol"),
    "budget": ("per_group_steps",),
    "steps": ("baseline_acquisition", "group_pairing", "saved_artifacts"),
    "analysis": ("effects", "uncertainty", "decision_rule"),
}

_ALLOWED_REFERENCE_KINDS = ("proposal", "suggestion", "hypothesis")


def required_design_slots(metric_domains=None):
    from services.deep_research.metric_scope import metric_protocol_requirements
    return {**REQUIRED, 'metrics': tuple(f'{domain}_protocol'
            for domain in metric_protocol_requirements(metric_domains))}


def validate_design_audit(claim, verdict, context, metric_domains=None):
    role = claim.get("designRole") if isinstance(claim, dict) else None
    if not isinstance(role, str):
        return []
    slots = required_design_slots(metric_domains).get(role)
    if slots is None:
        return []

    audit = verdict.get("designAudit") if isinstance(verdict, dict) else None
    # Accept the observed unambiguous role wrapper without weakening slot checks.
    if isinstance(audit, dict) and set(audit) == {role} and isinstance(audit[role], dict):
        audit = audit[role]
    if not isinstance(audit, dict):
        return list(slots)

    failed = []
    for slot in slots:
        if not _slot_supported(audit.get(slot), claim, context, slot):
            failed.append(slot)
    return failed


def _slot_supported(entry, claim, context, slot=None):
    if not isinstance(entry, dict):
        return False
    if 'fields' in entry:
        fields = entry['fields']
        if set(entry) != {'fields'} or not isinstance(fields, list) or not 1 <= len(fields) <= 32:
            return False
        return all(_field_supported(field, claim, context, slot) for field in fields)
    if 'quotes' in entry:
        # Non-contiguous choices retain their own source identities. Never
        # split or normalize a fabricated combined quotation on the caller's behalf.
        segments = entry['quotes']
        if set(entry) != {'quotes'} or not isinstance(segments, list) or not 1 <= len(segments) <= 32:
            return False
        return all(isinstance(segment, dict) and not {'quotes', 'fields'} & set(segment)
                   and _slot_supported(segment, claim, context, slot) for segment in segments)
    claim_id = entry.get("claimId")
    quote = entry.get("quote")
    if not isinstance(claim_id, str) or not isinstance(quote, str) or not quote.strip():
        return False
    reference = _resolve_reference(claim, context, claim_id)
    if reference is None:
        return False
    return any(quote in text for text in _reference_texts(reference))


_FIELD_ROOTS = {
    'intervention_levels': ('groups', {'factors'}),
    'scenes': ('data', {'dataset', 'scenes'}),
    'split': ('data', {'split'}),
    'seeds': ('data', {'seeds'}),
    'sampling_unit': ('data', {'independentUnit'}),
    'effects': ('analysis', {'effects'}),
    'uncertainty': ('analysis', {'uncertainty'}),
    'decision_rule': ('analysis', {'decision'}),
}


def _field_supported(field, claim, context, slot):
    """Bind an exact typed value, not a generated paraphrase or a truth verdict."""
    if not isinstance(field, dict) or set(field) != {'claimId', 'path', 'value'}:
        return False
    path = field['path']
    if (not isinstance(field['claimId'], str) or not isinstance(path, list)
            or not 2 <= len(path) <= 12 or path[0] != 'executionSpec'):
        return False
    reference = _resolve_reference(claim, context, field['claimId'])
    allowed = _FIELD_ROOTS.get(slot)
    if (reference is None or allowed is None or reference.get('designRole') != allowed[0]
            or not isinstance(path[1], str) or path[1] not in allowed[1]):
        return False
    from services.deep_research.execution_spec import execution_spec_errors
    if execution_spec_errors(reference.get('designRole'), reference.get('executionSpec')):
        return False
    value = reference
    for key in path:
        if isinstance(value, dict) and isinstance(key, str) and key in value:
            value = value[key]
        elif isinstance(value, list) and type(key) is int and 0 <= key < len(value):
            value = value[key]
        else:
            return False
    if value is None or value == '' or value == [] or value == {}:
        return False
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False) == json.dumps(
            field['value'], sort_keys=True, allow_nan=False)
    except (ValueError, TypeError):
        return False


def _resolve_reference(claim, context, claim_id):
    if (isinstance(claim, dict) and claim.get("claimId") == claim_id
            and claim.get("kind") in _ALLOWED_REFERENCE_KINDS):
        return claim
    if isinstance(context, list):
        for entry in context:
            if not isinstance(entry, dict):
                continue
            if entry.get("claimId") != claim_id:
                continue
            if entry.get("kind") in _ALLOWED_REFERENCE_KINDS:
                return entry
            return None
    return None


def _reference_texts(entry):
    texts = []
    text = entry.get("text")
    if isinstance(text, str):
        texts.append(text)
    conditions = entry.get("conditions")
    if conditions is not None:
        try:
            texts.append(json.dumps(conditions, ensure_ascii=False))
        except (TypeError, ValueError):
            pass
    return texts
