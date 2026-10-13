"""A bounded final-answer audit, distinct from retrieval and factual verification."""
import json

from services.deep_research.contracts import BudgetExhaustedError


def coverage_prompt_byte_limit(budget):
    """Fit to currently available finalization capacity; admission stays atomic."""
    if not budget or 'maxTokens' not in budget:
        return 24000
    keys = ('maxTokens', 'tokens', 'reserveTokens', 'normalTokens',
            'maxModelCalls', 'modelCalls', 'reserveModelCalls', 'reservedModelCalls')
    if any(type(budget.get(k, 0)) is not int or budget.get(k, 0) < 0 for k in keys):
        return 0
    maximum, used, reserve, normal, calls, ordinary, reserved, final = [budget.get(k, 0) for k in keys]
    if reserve > maximum or reserved > calls or ordinary + final >= calls:
        return 0
    remaining = maximum - used
    if final >= reserved:
        if ordinary >= calls - reserved:
            return 0
        remaining = min(remaining, maximum - reserve - normal)
    return max(0, min(24000, remaining - 3500 - 1024))


def audit_final_answer(run_id, question, plan, claims, evidence, invoke, parse, *, budget=None):
    from services.deep_research.answer_coverage import answer_coverage_gaps
    from services.deep_research.selection import balanced_sample, surrounding_context

    # A plan can itself omit part of the request. Audit the original question as
    # well as each planned obligation, without changing the stored research plan.
    from services.deep_research.obligation_purpose import normalize_obligation_purposes, nonblocking_research_obligations
    audit_plan = normalize_obligation_purposes(plan, question)
    identity = None
    if plan and question:
        known = {o['obligationId'] for p in plan for o in p.get('obligations', [])}
        identity = 'answer_scope'
        while identity in known:
            identity += '_'
        audit_plan.append({'obligations': [{'obligationId': identity, 'question': question}]})
    verdicts = []
    status = 'not_checked'
    invalid_aspects = []
    nonblocking = []
    budget_limit = None
    if claims and plan and invoke:
        selected = balanced_sample(evidence,
            lambda e: (e.get('sourceWorkId'), tuple(e.get('obligationIds', []))), 20)
        from uuid import uuid4
        from services.deep_research.prompt_budget import fit_evidence_prompt
        evidence_marker = uuid4().hex
        rows = [{
            'evidenceId': e['evidenceId'], 'quote': e.get('quote', ''),
            'sourceContext': surrounding_context(e), 'source': e.get('sourceWorkId'),
            'conditions': e.get('conditions', {}),
            'accessLevel': e.get('accessLevel'),
        } for e in selected]
        prompt = f'''Audit whether the FINAL ACCEPTED ANSWER fully answers the user's question.
Question: {question}
Research and answer obligations (including the original question): {json.dumps([o for p in audit_plan for o in p.get('obligations', [])], ensure_ascii=False)}
Accepted final claims: {json.dumps(claims, ensure_ascii=False, sort_keys=True)}
Available evidence for detecting omitted conditions: {evidence_marker}

Factual support has been checked separately. Do NOT mistake a true sentence, a relevant
retrieval, a claim's obligationIds, or the existence of a citation for a complete answer.
Judge the actual accepted text and its conditions. An accurate high-level summary is
partial if it omits parameters, activation rules, assumptions or comparisons needed to
answer this particular question. Preserve the requested brevity: do not demand every
paper detail, implementation detail, extra experiment or background the user did not ask for.
For a mechanism question, check the requested entities, their relationships, the relevant
conditioning inputs, and when the mechanism applies, using the supplied passages.
For a comparison, check every requested dimension and each paper's contribution, not
just one paper's results. A source-specific, clearly stated evidence limitation can
answer an uncertainty question; do not demand proof of a universal guarantee.
An unexecuted experiment may be complete as a proposal; do not demand measured results.
An obligation marked supporting_research is an auxiliary investigation, not automatically
something the final answer must narrate. Independently check its relevance to the user's
actual deliverable. If it is genuinely unnecessary to the accepted answer, use status
not_required with reason (specific explanation, at least 12 characters), requestExcerpt
(at least 8 characters copied exactly from the user's original question), and bindings
quoting the accepted answer that makes this narrower research scope sufficient.
Never use not_required for the original question or an answer_requirement. A planning
label is not permission to ignore requested facts, dependencies needed by a claim,
missing interventions/assumptions, or evidence required by the user's requested scope.
If a supporting question is necessary and unanswered, mark partial or missing. Only
covered means actually answered; not_required does not mean the source fact was checked.
Judge proposed protocol completeness separately from narrating the paper's benchmarks.
Do not rewrite the answer, add claims, change factual verdicts, or judge rejected claims.
Before deciding covered, enumerate the minimal essential aspects separately:
entities and their relationships, conditioning inputs, activation/applicability
rules, requested comparisons and guarantee boundaries, as applicable. Identify
these from the question AND the supplied source passages, not from what the
answer happened to mention. Do not merge distinct conditioning inputs into one
vague aspect. A missing aspect remains missing even if every stated sentence is true.
For each aspect identify its basis and the accepted answer that covers it.
Prefer field references to copying PDF text: a source basis is
{{"kind":"source","evidenceId":"supplied ID","field":"quote"}}.
Use field "sourceContext.before" or "sourceContext.after" only when that exact
supplied context field contains the required basis. The server binds the complete
unchanged field. Do not supply excerpt together with field, and do not infer omitted
context. For a final-answer binding use {{"claimId":"accepted ID","field":"text"}}
or field "conditions" for that claim's serialized conditions. Select it only if
its actual content covers the specific aspect, not merely because it is related.
Legacy literal excerpt bindings remain valid; never insert ellipses, normalize
PDF spelling or punctuation, or combine noncontiguous excerpts into one string.
When checking factual claims with available evidence, include source-grounded
essential aspects; quoting only the broad user question is insufficient.
For an access-level requirement ONLY (what the system actually obtained), use
basis {{"kind":"source_metadata","evidenceId":"ID cited by the bound claim",
"field":"accessLevel","value":"fulltext|abstract|user_note",
"requestExcerpt":"exact relevant question substring, at least 8 characters"}}.
Copy value from the supplied evidence metadata; never infer it from page numbers.
This proves acquisition scope only, never a method, result or scientific claim.
Every aspect of a metadata-only obligation must use that metadata basis; mixed
content obligations still require source-quoted aspects for their paper content.
Keep exact final-answer bindings for metadata aspects too. A downloaded fulltext
does not prove that the answer uses it unless the bound claim cites that evidence.
Check the subject of contrasts and pronouns against preceding sentences: a
baseline's limitation cannot be assigned to the proposed method.
Return only a JSON array, exactly one entry for each of these obligationIds,
including the original-question scope: {json.dumps([o['obligationId'] for p in audit_plan for o in p.get('obligations', [])])}
[{{"obligationId":"ID","status":"covered|partial|missing|not_required",
   "bindings":[{{"claimId":"an accepted ID","field":"text"}}],
   "aspects":[{{"aspectId":"unique within this obligation","requirement":"one necessary aspect",
     "basis":{{"kind":"source","evidenceId":"supplied evidence ID","field":"quote"}},
     "status":"covered|partial|missing",
     "bindings":[{{"claimId":"accepted ID","field":"text"}}]}}]}}]
For a request basis use {{"kind":"request","excerpt":"exact question substring"}}.
Covered requires every essential aspect to be covered with its own binding.
Do not fabricate a binding for a missing aspect; use an empty bindings array.
Only mark covered if ALL requested aspects of that obligation are answered in the
accepted claims. Bindings must quote the final answer, never the source passages.'''
        template = prompt
        try:
            limit = coverage_prompt_byte_limit(budget)
            render = lambda selected_rows: template.replace(evidence_marker, json.dumps(selected_rows, ensure_ascii=False), 1)
            fixed_bytes = len(render([]).encode('utf-8'))
            if limit <= 0 or fixed_bytes > limit:
                raise BudgetExhaustedError('coveragePromptBytes', limit, fixed_bytes)
            prompt, rows = fit_evidence_prompt(rows, render, max_bytes=limit)
            result = invoke(run_id, 'verify_answer_coverage', prompt,
                            {'max_tokens': 3500, 'temperature': 0.0}, use_reserve=True)
            content = result.get('content', '') if isinstance(result, dict) else getattr(result, 'content', '')
            finish = result.get('finishReason', result.get('finish_reason')) if isinstance(result, dict) else getattr(result, 'finish_reason', None)
            try:
                verdicts = parse(content) if finish != 'length' else None
            except (ValueError, TypeError):
                verdicts = None
            status = 'checked' if isinstance(verdicts, list) else 'invalid_response'
            if isinstance(verdicts, list):
                from services.deep_research.coverage_references import resolve_coverage_references
                verdicts = resolve_coverage_references(verdicts, claims, rows)
                # Explicitly reported missing subrequirements override an
                # inconsistent overall "covered", and remain repairable gaps.
                verdicts = [{**v, 'status': 'partial'} if isinstance(v, dict)
                    and v.get('status') == 'covered' and isinstance(v.get('aspects'), list)
                    and any(isinstance(a, dict) and a.get('status') in {'partial', 'missing'}
                            for a in v['aspects']) else v for v in verdicts]
                from services.deep_research.coverage_aspects import invalid_coverage_aspects
                invalid_aspects = invalid_coverage_aspects(verdicts, claims, rows,
                    [question, *[o.get('question', '') for p in audit_plan for o in p.get('obligations', [])]],
                    request_only_obligations=[identity] if identity else [])
                if invalid_aspects:
                    verdicts = [{**v, 'status': 'partial'} if isinstance(v, dict)
                        and v.get('obligationId') in invalid_aspects else v for v in verdicts]
                    status = 'invalid_response'
        except BudgetExhaustedError as exc:
            # Publish only supported text with an explicit coverage gap. Never
            # promote budget exhaustion to a complete answer or add a retry.
            status = 'budget_exhausted'
            budget_limit = exc.details
    if status == 'checked' and identity:
        nonblocking = nonblocking_research_obligations(plan, question, claims, verdicts,
                                                     identity, invalid_aspects)
    excluded = {row['obligationId'] for row in nonblocking}
    effective_plan = [{**item, 'obligations': [o for o in item.get('obligations', [])
                      if o.get('obligationId') not in excluded]} for item in audit_plan]
    gaps = answer_coverage_gaps(effective_plan, claims, verdicts)
    for gap in gaps:
        matching = [v for v in verdicts if isinstance(v, dict)
                    and v.get('obligationId') == gap.get('obligationId')] if isinstance(verdicts, list) else []
        if len(matching) == 1 and isinstance(matching[0].get('aspects'), list):
            gap['missingAspects'] = list(dict.fromkeys(a['requirement'].strip()
                for a in matching[0]['aspects'] if isinstance(a, dict)
                and a.get('status') in {'partial', 'missing'}
                and isinstance(a.get('requirement'), str) and a['requirement'].strip()))
            gap['aspectEvidenceRefs'] = list(dict.fromkeys(a['basis']['evidenceId']
                for a in matching[0]['aspects'] if isinstance(a, dict)
                and a.get('status') in {'partial', 'missing'}
                and isinstance(a.get('basis'), dict) and a['basis'].get('kind') == 'source'
                and isinstance(a['basis'].get('evidenceId'), str)))
        if status in {'budget_exhausted', 'invalid_response'}:
            gap['missingEvidence'] = '回答完整性尚未核验'
            gap['auditStatus'] = status
        if identity and gap.get('obligationId') == identity:
            gap['wholeQuestion'] = True
    return {'status': status, 'verdicts': verdicts if isinstance(verdicts, list) else [],
            'gaps': gaps, 'invalidAspectObligations': invalid_aspects,
            'wholeQuestionId': identity, 'nonblockingResearch': nonblocking,
            'budgetLimit': budget_limit}


def remaining_retrieval_gaps(gaps, audit, claims, evidence, *, plan=None, question=""):
    """Return source gaps that still block the actual answer.

    Required research keeps the source-specific closure rule: a bounded factual
    answer may close it, never another paper's answer or an unchecked proposal.
    Separately audited unnecessary support questions are nonblocking, not solved;
    callers retain the untouched original gap list in the run's research history.
    """
    if audit.get('status') != 'checked':
        return list(gaps)
    # Revalidate against current accepted claims; a stored exemption list alone
    # is never enough, and the original source gaps remain in run history.
    from services.deep_research.obligation_purpose import nonblocking_research_obligations
    optional = nonblocking_research_obligations(plan, question, claims,
        audit.get('verdicts'), audit.get('wholeQuestionId'), audit.get('invalidAspectObligations', []))
    optional_ids = {row['obligationId'] for row in optional}
    gaps = [gap for gap in gaps if not isinstance(gap, dict) or gap.get('obligationId') not in optional_ids]
    missing = {g.get('obligationId') for g in audit.get('gaps', [])}
    from services.deep_research.answer_coverage import answer_coverage_gaps
    check_plan = [{'obligations': [g for g in gaps if isinstance(g, dict) and g.get('obligationId')]}]
    missing.update(g.get('obligationId') for g in answer_coverage_gaps(check_plan, claims, audit.get('verdicts')))
    accepted = {c.get('claimId'): c for c in claims
                if c.get('verification') == 'semantic_passed' and c.get('kind') in {'reported', 'inference'}}
    origins = {e.get('evidenceId'): e.get('sourceWorkId') for e in evidence
               if e.get('verification', {}).get('literal') == 'passed'}
    covered = {}
    for verdict in audit.get('verdicts', []):
        oid = verdict.get('obligationId')
        if verdict.get('status') != 'covered' or oid in missing:
            continue
        works = set()
        for binding in verdict.get('bindings', []):
            claim = accepted.get(binding.get('claimId'), {})
            works.update(origins[ref] for ref in claim.get('evidenceRefs', []) if origins.get(ref))
        covered[oid] = works
    return [gap for gap in gaps if not isinstance(gap, dict)
            or gap.get('sourceWorkId') not in covered.get(gap.get('obligationId'), set())]
