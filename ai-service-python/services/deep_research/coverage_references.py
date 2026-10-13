"""Resolve audit field references against only the records shown in this call.

Selecting a field avoids transcribing PDF line breaks or eliding answer text.
It is not a semantic verdict: the existing aspect and answer checks still run.
"""
from copy import deepcopy
import json


def _unique(rows, key):
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = row.get(key)
        if isinstance(identity, str) and identity:
            result[identity] = row if identity not in result else None
    return result


def resolve_coverage_references(verdicts, claims, evidence_rows):
    known = _unique(claims, 'claimId')
    evidence = _unique(evidence_rows, 'evidenceId')
    resolved = deepcopy(verdicts)

    def bind(entries):
        for binding in entries if isinstance(entries, list) else []:
            if not isinstance(binding, dict) or 'field' not in binding:
                continue
            if 'excerpt' in binding:
                binding['referenceError'] = 'field_excerpt_conflict'
                continue
            claim = known.get(binding.get('claimId')) if isinstance(binding.get('claimId'), str) else None
            if claim is None:
                binding['referenceError'] = 'unknown_or_ambiguous_claim'
                continue
            excerpt = ''
            if binding['field'] == 'text' and isinstance(claim.get('text'), str):
                excerpt = claim['text']
            elif binding['field'] == 'conditions' and isinstance(claim.get('conditions'), dict) and claim['conditions']:
                excerpt = json.dumps(claim['conditions'], ensure_ascii=False, sort_keys=True)
            if excerpt:
                binding['excerpt'] = excerpt
            else:
                binding['referenceError'] = 'answer_field_not_supplied'

    for verdict in resolved:
        if not isinstance(verdict, dict):
            continue
        bind(verdict.get('bindings'))
        aspects = verdict.get('aspects')
        for aspect in aspects if isinstance(aspects, list) else []:
            if not isinstance(aspect, dict):
                continue
            bind(aspect.get('bindings'))
            basis = aspect.get('basis')
            if not isinstance(basis, dict) or basis.get('kind') != 'source' or 'field' not in basis:
                continue
            if 'excerpt' in basis:
                basis['referenceError'] = 'field_excerpt_conflict'
                continue
            row = evidence.get(basis.get('evidenceId')) if isinstance(basis.get('evidenceId'), str) else None
            if row is None:
                basis['referenceError'] = 'unknown_or_ambiguous_evidence'
                continue
            excerpt = ''
            context = row.get('sourceContext')
            context = context if isinstance(context, dict) else {}
            values = {'quote': row.get('quote'), 'sourceContext.before': context.get('before'),
                      'sourceContext.after': context.get('after')}
            field = basis['field']
            if isinstance(field, str) and isinstance(values.get(field), str):
                excerpt = values[field]
            if excerpt:
                basis['excerpt'] = excerpt
            else:
                basis['referenceError'] = 'source_field_not_supplied'
    return resolved
