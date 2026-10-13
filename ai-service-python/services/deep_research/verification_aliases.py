"""Request-local evidence aliases; never rewrite quotations or claim identities."""
from copy import deepcopy


def encode_verification_inputs(claims, evidence):
    refs = {ref for claim in claims for ref in claim.get('evidenceRefs', [])}
    selected = [row for row in evidence if row['evidenceId'] in refs]
    identities = [row['evidenceId'] for row in selected]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate evidence identity')
    occupied = refs | {row['evidenceId'] for row in evidence}
    prefix = 'E'
    while any(f'{prefix}{i + 1}' in occupied for i in range(len(selected))):
        prefix += '_'
    aliases = {identity: f'{prefix}{i + 1}' for i, identity in enumerate(identities)}
    reverse = {short: full for full, short in aliases.items()}
    wire_claims = deepcopy(claims)
    for claim in wire_claims:
        claim['evidenceRefs'] = [aliases.get(ref, ref) for ref in claim.get('evidenceRefs', [])]
        bindings = claim.get('tableBindings')
        for binding in bindings if isinstance(bindings, list) else []:
            if isinstance(binding, dict) and isinstance(binding.get('evidenceId'), str):
                binding['evidenceId'] = aliases.get(binding['evidenceId'], binding['evidenceId'])
    wire_evidence = deepcopy(selected)
    for row in wire_evidence:
        row['evidenceId'] = aliases[row['evidenceId']]
    return wire_claims, wire_evidence, reverse


def restore_visible_evidence(rows, reverse):
    restored = deepcopy(rows)
    for row in restored:
        row['evidenceId'] = reverse[row['evidenceId']]
    return restored


def restore_verdict_evidence(verdict, reverse):
    restored = deepcopy(verdict)
    binding = restored.get('dataAvailability')
    if isinstance(binding, dict) and isinstance(binding.get('evidenceId'), str):
        binding['evidenceId'] = reverse.get(binding['evidenceId'], binding['evidenceId'])
    return restored
