"""One bounded revision within the acquired source versions, followed by verification."""
from __future__ import annotations

import json
from copy import deepcopy

from services.deep_research.answer_constraints import answer_character_count, requested_character_limit, normalize_conditions, resolve_evidence_aliases
from services.deep_research.contracts import BudgetExhaustedError
from services.deep_research.selection import surrounding_context
from services.deep_research.prompt_budget import fit_evidence_prompt
from uuid import uuid4
from services.deep_research.repair_scope import repair_evidence_scope


def repair_rejected(report, verification, evidence, question, invoke, parse, *, max_prompt_bytes=24000, metric_domains=None):
    rejected = {row['claimId']: row for row in verification.get('rejected', [])}
    originals = {row['claimId']: row for row in report.get('claims', []) if row.get('claimId') in rejected}
    if not originals:
        return []
    hinted = {ref for row in rejected.values() for ref in row.get('missingEvidenceRefs', [])
              if isinstance(ref, str)}
    evidence = sorted(evidence, key=lambda e: e.get('evidenceId') not in hinted)
    allowed = repair_evidence_scope(list(originals.values()), evidence)
    refs = {ref for values in allowed.values() for ref in values}
    selected = [e for e in evidence if e['evidenceId'] in refs]
    aliases = {f'E{i + 1}': e['evidenceId'] for i, e in enumerate(selected)}
    short_ids = {full: short for short, full in aliases.items()}
    original_refs = {ref for row in originals.values() for ref in row.get('evidenceRefs', [])}
    rows = [
        {'evidenceId': short_ids[e['evidenceId']], 'quote': e.get('quote', ''),
         'sourceContext': surrounding_context(e), 'location': e.get('location', {}),
         'accessLevel': e.get('accessLevel'), 'conditions': e.get('conditions', {}),
         'tableData': e.get('tableData')}
        for e in sorted(selected, key=lambda e: (e['evidenceId'] not in hinted,
                                                 e['evidenceId'] not in original_refs))
    ]
    evidence_marker, permissions_marker = uuid4().hex, uuid4().hex
    input_claims = resolve_evidence_aliases({'claims': deepcopy(list(originals.values()))}, short_ids)['claims']
    from services.deep_research.execution_materialization import verification_claim_view
    input_claims = [verification_claim_view(row) for row in input_claims]
    from services.deep_research.repair_prompt import factor_repair_questions
    question_dictionary, packed_checks = factor_repair_questions(rejected)
    for check in packed_checks.values():
        if isinstance(check.get('missingEvidenceRefs'), list):
            check['missingEvidenceRefs'] = [short_ids.get(ref, ref) if isinstance(ref, str) else ref
                                            for ref in check['missingEvidenceRefs']]
    revision_shape = {'claimId': 'original ID', 'kind': 'original kind', 'text': 'revised wording',
                      'evidenceRefs': ['E1'], 'conditions': {}, 'detailLevel': 'fulltext'}
    if any(row.get('designContractVersion') == 2 for row in originals.values()):
        revision_shape.update(designRole='canonical role for proposals/hypotheses; omit for facts',
                              executionSpec='complete object for groups/data/analysis; omit for other roles')
    proposal_context = [{key: row[key] for key in ('claimId', 'text', 'kind', 'conditions', 'designRole', 'executionSpec', 'designContractVersion') if key in row}
                        for row in verification.get('accepted', [])
                        if row.get('kind') in {'proposal', 'suggestion', 'hypothesis'}
                        and row.get('claimId') not in originals]
    proposal_context = [verification_claim_view(row) for row in proposal_context]
    prompt = f'''Revise only the targets; narrow unsupported wording or omit it.
answer_incomplete requires filling requested omissions, conditioning inputs and applicability,
not merely shortening. absence_not_established requires bounded positive evidence:
missing passages do not prove paper-wide absence; finite results do not prove universality.
Question: {question}
Accepted experimental definitions (consistency only; do not revise these or treat them as paper evidence):
{json.dumps(proposal_context, ensure_ascii=False, separators=(',', ':'))}
Application-generated protocol suffixes are omitted here; their complete executionSpec remains.
The interface renders those fields. Preserve original prose consistency; do not duplicate that rendering.
Missing-question dictionary (each missingQuestionIds entry refers to the exact question here;
Q identifiers are internal references, never evidence or text to publish):
{json.dumps(question_dictionary, ensure_ascii=False, separators=(',', ':'))}
Rejected claims and checks:
{json.dumps([{'claim': row, 'check': packed_checks[row['claimId']]} for row in input_claims], ensure_ascii=False, separators=(',', ':'))}
Allowed evidence IDs per claim (candidate permissions, not proof of support):
{permissions_marker}
Exact available evidence:
{evidence_marker}
Return a COMPACT JSON array, or [] if no supported revision is possible. Schema:
{json.dumps(revision_shape, ensure_ascii=False)}
Use actual values, not schema descriptions; wording key is "text".
Preserve claimId, kind and valid designRole; no new claims, searches or reported results.
Never disguise a fact as a proposal. Retain necessary conditions and the user's length limit.
Each claim may cite ONLY its own allowed supplied evidence. Same-version permission and
obligation labels do not prove relevance or support. Check every factual clause.
Use E1/E2 aliases in evidenceRefs/tableBindings, never in published text; Q IDs are not evidence.
Table numbers require exact tableData bindings:
{{"evidenceId":"E1","rowNumber":1,"groupIndex":0,"metric":"FPS","value":"200"}}
This is schema, not evidence: copy actual rowNumber, zero-based groupIndex, metric and value
(key "value", never "exactStringValue"). Name dataset/method/metric; omit unsupported numbers.
Abstract evidence permits only explicit abstract-level wording (detailLevel="abstract").
For existing proposals, choose concrete seed/split/level/budget/confidence settings as YOUR UNEXECUTED PROPOSAL,
not paper-attributed values or promises to preregister later. Correct formulas and label
hypotheses/proposals. Source facts still require evidence; proposed choices need not occur
in the paper. Maintain consistency with accepted definitions and complete required details.'''
    if any(row.get('designContractVersion') == 2 for row in originals.values()):
        from services.deep_research.execution_spec import EXECUTION_SPEC_CONTRACT
        from services.deep_research.experimental_reasoning import DESIGN_ROLES, design_requirements
        prompt += '\nEvery v2 proposal/suggestion/hypothesis requires one designRole from: ' + json.dumps(sorted(DESIGN_ROLES))
        prompt += '. For a missing role, assign the appropriate role based on its actual content; ' \
                  'do not omit the role to bypass checks. Preserve existing valid roles. ' \
                  'Groups, data and analysis roles also require their complete executionSpec.'
        prompt += '\n' + EXECUTION_SPEC_CONTRACT
        prompt += '\nExperimental deliverables (apply jointly across the accepted and revised claims):\n' + design_requirements(metric_domains)
        prompt += ('\nA structural rejection is not a content approval. Fix substantive omissions in the same revision, '
                   'including concrete intervention levels, per-group budgets and measurement aggregation. '
                   'Choose explicit unexecuted proposal settings when appropriate; do not wait for paper settings '
                   'to define your own diagnostic. Cover all required roles without changing an existing valid role '
                   'or inventing new claim IDs. Do not claim completeness when the available claims cannot cover them. '
                   'Keep all proposed settings consistent across claims and executionSpec.')
    template = prompt
    def render(selected_rows):
        visible_ids = {row['evidenceId'] for row in selected_rows}
        permissions = {key: [short_ids[ref] for ref in values
                            if ref in short_ids and short_ids[ref] in visible_ids]
                       for key, values in allowed.items()}
        return template.replace(permissions_marker, json.dumps(permissions, ensure_ascii=False), 1).replace(
            evidence_marker, json.dumps(selected_rows, ensure_ascii=False), 1)
    if max_prompt_bytes <= 0:
        raise BudgetExhaustedError('repairPromptBytes', max_prompt_bytes, 1)
    try:
        prompt, rows = fit_evidence_prompt(rows, render, max_bytes=max_prompt_bytes)
    except ValueError as exc:
        if str(exc) != 'prompt_fixed_content_too_large':
            raise
        raise BudgetExhaustedError('repairPromptBytes', max_prompt_bytes,
                                  len(render([]).encode('utf-8'))) from exc
    visible = {aliases[row['evidenceId']] for row in rows}
    allowed = {key: [ref for ref in values if ref in visible] for key, values in allowed.items()}
    try:
        response = invoke(prompt)
    except BudgetExhaustedError:
        return []
    finish = getattr(response, 'finish_reason', None) if not isinstance(response, dict) else response.get('finishReason', response.get('finish_reason'))
    if finish == 'length':
        return []
    content = response.content if hasattr(response, 'content') else response.get('content', '')
    revised = parse(content)
    if not isinstance(revised, list):
        return []
    revised = resolve_evidence_aliases({'claims': revised}, aliases)['claims']
    valid, seen = [], set()
    for row in revised:
        if not isinstance(row, dict):
            continue
        key = row.get('claimId')
        original = originals.get(key)
        if not original or key in seen or row.get('kind') != original.get('kind'):
            continue
        seen.add(key)
        new_refs = row.get('evidenceRefs', [])
        if not isinstance(new_refs, list) or any(ref not in allowed.get(key, []) for ref in new_refs):
            continue
        if original.get('designContractVersion') == 2:
            row['designContractVersion'] = 2
        # The repair cannot reassign the claim to another research obligation.
        if 'obligationIds' in original:
            row['obligationIds'] = deepcopy(original['obligationIds'])
        # One observed provider spelling is unambiguous. Normalize syntax only;
        # the exact same identity, numeric and semantic checks still follow.
        if isinstance(row.get('claim'), str):
            if 'text' in row and row['text'] != row['claim']:
                continue
            row['text'] = row.pop('claim')
        if not isinstance(row.get('text'), str) or not row['text'].strip():
            continue
        if original.get('designRole'):
            if row.get('designRole', original['designRole']) != original['designRole']:
                continue
            row['designRole'] = original['designRole']
        from services.deep_research.execution_materialization import materialize_execution_claim
        normalized = normalize_conditions({'claims': [dict(row)]})['claims'][0]
        valid.append(materialize_execution_claim(normalized))
    candidate = {'claims': [*verification.get('accepted', []), *valid]}
    limit = requested_character_limit(question)
    return [] if limit and answer_character_count(candidate) > limit else valid
