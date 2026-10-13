"""Validate scope audit trails, never infer relevance from a planning label."""
from copy import deepcopy

from services.deep_research.answer_coverage import (
    answer_coverage_gaps, _bindings_supported, _known_claims_by_id,
)


def _obligations(plan):
    if not isinstance(plan, list):
        return None
    rows = []
    for item in plan:
        if not isinstance(item, dict) or not isinstance(item.get('obligations'), list):
            return None
        if any(not isinstance(row, dict) for row in item['obligations']):
            return None
        rows.extend(item['obligations'])
    return rows


def _request_excerpt(value, question):
    return isinstance(value, str) and len(value.strip()) >= 8 and value.strip() in question


def normalize_obligation_purposes(plan, question):
    """Preserve nested plans; legacy or ungrounded purposes remain required."""
    if not isinstance(question, str) or _obligations(plan) is None:
        return []
    result = deepcopy(plan)
    for row in _obligations(result):
        valid_excerpt = _request_excerpt(row.get('requestExcerpt'), question)
        row['purpose'] = ('supporting_research' if row.get('purpose') == 'supporting_research'
                          and valid_excerpt else 'answer_requirement')
        if valid_excerpt:
            row['requestExcerpt'] = row['requestExcerpt'].strip()
        else:
            row.pop('requestExcerpt', None)
    return result


def nonblocking_research_obligations(plan, question, claims, verdicts,
                                    whole_question_id, invalid_aspect_ids=()):
    """Approve only grounded, uniquely bound not_required research decisions.

    Caller must validate covered aspect trails first and supply any invalid IDs.
    Structural checks cannot establish that a model's scope judgment is correct.
    The original source gaps are never changed or reclassified as answered.
    """
    if (not isinstance(question, str) or _obligations(plan) is None
            or not isinstance(claims, list) or not isinstance(verdicts, list)
            or invalid_aspect_ids or not isinstance(whole_question_id, str)
            or not whole_question_id):
        return []
    rows = _obligations(normalize_obligation_purposes(plan, question))
    identities = [row.get('obligationId') for row in rows]
    if (any(not isinstance(key, str) or not key for key in identities)
            or len(identities) != len(set(identities)) or whole_question_id in identities):
        return []
    known = _known_claims_by_id(claims)

    def matches(identity):
        return [v for v in verdicts if isinstance(v, dict) and v.get('obligationId') == identity]

    whole = matches(whole_question_id)
    if (len(whole) != 1 or whole[0].get('status') != 'covered'
            or not _bindings_supported(whole[0].get('bindings'), known)):
        return []
    required = [{'obligations': [row for row in rows if row['purpose'] != 'supporting_research']}]
    if answer_coverage_gaps(required, claims, verdicts):
        return []
    result = []
    for row in rows:
        if row['purpose'] != 'supporting_research':
            continue
        found = matches(row['obligationId'])
        if len(found) != 1 or found[0].get('status') != 'not_required':
            continue
        verdict = found[0]
        reason = verdict.get('reason')
        excerpt = verdict.get('requestExcerpt')
        if (not isinstance(reason, str) or len(reason.strip()) < 12
                or not _request_excerpt(excerpt, question)
                or not _bindings_supported(verdict.get('bindings'), known)):
            continue
        result.append({'obligationId': row['obligationId'], 'reason': reason.strip(),
                       'requestExcerpt': excerpt.strip(), 'bindings': deepcopy(verdict['bindings'])})
    return result
