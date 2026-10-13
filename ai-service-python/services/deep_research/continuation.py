"""Reuse frozen local material versions without confusing file and chunk hashes."""
import hashlib


def reusable_local_source(source, material, parent_material):
    if not material or source.get('workId') != material.get('materialId'):
        return False
    digest = material.get('contentHash')
    if not digest or (parent_material and parent_material.get('contentHash') != digest):
        return False
    if source.get('materialContentHash'):
        return source['materialContentHash'] == digest
    # Full-PDF fallback sources already carry the file hash.
    if source.get('contentHash') == digest:
        return True
    # Earlier indexed sources carry an exact passage hash. Require both the
    # unchanged frozen file version and intact passage bytes before reuse.
    version = material.get('versionId')
    text = source.get('text')
    return bool(parent_material and version and version == parent_material.get('versionId') == source.get('versionId')
                and isinstance(text, str) and text
                and hashlib.sha256(text.encode()).hexdigest() == source.get('contentHash'))


def rebind_inherited_state(state, plan):
    """Propose new obligation links; relevance must be checked again."""
    def obligations(work_id):
        return [o['obligationId'] for item in plan for o in item.get('obligations', [])
                if work_id in o.get('requiredSources', [])]
    sources = [{**s, 'obligationIds': obligations(s.get('workId'))} for s in state.get('sources', [])]
    evidence = [{**e, 'obligationIds': obligations(e.get('sourceWorkId')),
                 'verification': {**e.get('verification', {}), 'semantic': 'unchecked'}}
                for e in state.get('evidence', [])]
    return {**state, 'sources': sources, 'evidence': evidence, 'plan': plan}
