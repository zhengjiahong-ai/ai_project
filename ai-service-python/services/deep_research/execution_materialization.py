"""Expose generated execution choices before any semantic verification."""
from copy import deepcopy

from services.deep_research.protocol_text import render_execution_spec


def normalize_execution_spec(role, spec):
    """Normalize observed unambiguous syntax, never choose between conflicting values."""
    result = deepcopy(spec)
    if role not in ('data', 'analysis') or not isinstance(result, dict):
        return result
    if set(result) == {role} and isinstance(result[role], dict):
        result = result[role]
    if role == 'data' and isinstance(result.get('replication'), str):
        if result['replication'] in ('fixed_checkpoint', 'retrained_per_seed'):
            result['replication'] = {'mode': result['replication']}
    if role == 'data' and isinstance(result.get('split'), dict):
        split = result['split']
        alias = 'zero-based offset'
        if alias in split and ('offset' not in split or
                (type(split['offset']) is type(split[alias]) and split['offset'] == split[alias])):
            split['offset'] = split.pop(alias)
    return result


def materialize_execution_claim(claim):
    result = deepcopy(claim)
    if (not isinstance(result, dict) or result.get('designContractVersion') != 2
            or result.get('kind') not in {'proposal', 'suggestion', 'hypothesis'}
            or not isinstance(result.get('text'), str)):
        return result
    if 'executionSpec' in result:
        result['executionSpec'] = normalize_execution_spec(result.get('designRole'), result['executionSpec'])
    text = render_execution_spec(result.get('designRole'), result.get('executionSpec'))
    if text:
        suffix = '\n\n' + text
        if not result['text'].endswith(suffix):
            # Preserve original prose. A contradictory narrative is still
            # visible to the verifier, never silently replaced by metadata.
            result['text'] += suffix
    return result


def verification_claim_view(claim):
    """Transmit typed configuration once; retain every original prose choice.

    Only remove the exact application-generated trailing rendering. It is
    deterministically reproducible from executionSpec; changed or contradictory
    prose is never shortened. Stored and published claims remain untouched.
    """
    result = deepcopy(claim)
    if (not isinstance(result, dict) or result.get('designContractVersion') != 2
            or result.get('kind') not in {'proposal', 'suggestion', 'hypothesis'}
            or not isinstance(result.get('text'), str)):
        return result
    rendered = render_execution_spec(result.get('designRole'), result.get('executionSpec'))
    suffix = '\n\n' + rendered if rendered else ''
    if suffix and result['text'].endswith(suffix):
        result['text'] = result['text'][:-len(suffix)]
    return result
