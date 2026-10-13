import json
from copy import deepcopy

from services.deep_research.experimental_reasoning import DESIGN_ROLES
from services.deep_research.graph import make_publish_node
from services.deep_research.reporting import build_sections
from services.deep_research.tools import BudgetedSemanticChecker
from services.deep_research.verification import verify_claims


def publish(claims):
    record = {'state': {'outputKind': 'experiment_design', 'evidence': [{'evidenceId': 'e'}],
        'verifiedReport': {'verifiedClaims': claims, 'rejectedClaims': [],
            'sections': [{'title': title, 'claimIds': [claims[0]['claimId']]}
                         for title in dict.fromkeys(title for title, _ in DESIGN_ROLES.values())]}}}
    saved = {}
    def update(run, mutate, **kwargs):
        nonlocal record
        record = mutate(record)
        return record
    def save(**kwargs):
        saved.update(kwargs)
        return {'publicationId': 'p'}, True
    make_publish_node(save, update)({'run_id': 'r'})
    return saved


def design_claims():
    return [{'claimId': role, 'kind': 'proposal', 'designRole': role,
             'text': requirement, 'evidenceRefs': [], 'verification': 'proposal'}
            for role, (_, requirement) in DESIGN_ROLES.items()]


def test_all_headings_and_vague_proposal_do_not_prove_complete_experiment():
    result = publish([{'claimId': 'c', 'text': '保持其他条件不变并比较结果。',
                       'kind': 'proposal', 'verification': 'proposal', 'evidenceRefs': []}])
    assert result['outcome'] == 'partial'
    missing = {g.get('designRole') for g in result['payload']['gaps']}
    assert {'budget', 'data', 'analysis', 'steps'} <= missing


def test_verified_roles_organize_report_and_missing_budget_cannot_be_hidden():
    claims = design_claims()
    before = deepcopy(claims)
    result = publish(claims)
    assert result['outcome'] == 'complete'
    assert claims == before
    fixed = next(s for s in result['payload']['sections'] if s['title'] == '固定条件')
    assert set(fixed['claimIds']) == {'controls', 'data', 'budget'}
    result = publish([c for c in claims if c['designRole'] != 'budget'])
    assert result['outcome'] == 'partial'
    assert any(g.get('designRole') == 'budget' for g in result['payload']['gaps'])
    assert '训练与恢复预算' in result['report_text']


def test_joint_design_check_keeps_all_definitions_but_separates_factual_evidence():
    batches = []
    def invoke(**kwargs):
        from services.deep_research.design_audit import REQUIRED
        prompt = kwargs['prompt']
        targets = json.loads(prompt.split('Claims:\n', 1)[1].split('\n\nEvidence:', 1)[0])
        batches.append(targets)
        if any(c.get('designRole') for c in targets):
            # All definitions remain visible, but only one class of claims is
            # judged in this call. Facts from other claims never become evidence.
            assert all(requirement in prompt for _, requirement in DESIGN_ROLES.values())
            assert 'UNRELATED_PAPER_QUOTE' not in prompt
            assert 'fulfillment of its entire' in prompt
            assert 'needs NO quotation' in prompt
            assert 'Be strict: evidence must directly support EVERY clause' not in prompt
            roles = {c.get('designRole') for c in targets}
            if kwargs['node'] == 'verify_design_config':
                assert roles == {'groups', 'controls', 'data', 'budget', 'steps', 'metrics'}
            else:
                assert roles == {'hypothesis', 'analysis', 'limits'}
        return {'content': json.dumps([{'claimId': c['claimId'],
                'status': 'failed' if c.get('designRole') == 'budget' else 'passed',
                'reason': 'recovery budget unspecified' if c.get('designRole') == 'budget' else '',
                'designAudit': {slot: {'claimId': c['claimId'], 'quote': c['text']}
                                for slot in REQUIRED.get(c.get('designRole'), [])}}
                for c in targets])}
    facts = [{'claimId': 'fact', 'kind': 'reported', 'text': 'Quality is measured.', 'evidenceRefs': ['e']}]
    evidence = [{'evidenceId': 'e', 'quote': 'UNRELATED_PAPER_QUOTE Quality is measured.',
                 'verification': {'literal': 'passed'}}]
    claims = [*facts, *design_claims()]
    checked = verify_claims(claims, evidence, BudgetedSemanticChecker(invoke, 'r'))
    assert len(batches) == 3
    assert [c['claimId'] for c in checked['accepted']] == [c['claimId'] for c in claims if c['claimId'] != 'budget']
    result = publish(checked['accepted'])
    assert result['outcome'] == 'partial'
    assert any(g.get('designRole') == 'budget' for g in result['payload']['gaps'])


def test_invalid_design_metadata_is_rejected_not_a_crash_or_completion():
    claims = [{'claimId': str(i), 'kind': 'proposal', 'text': 'Example', 'evidenceRefs': [], 'designRole': role}
              for i, role in enumerate([['budget'], 'invented'])]
    result = verify_claims(claims, [], lambda c, e: [])
    assert [r['reason'] for r in result['rejected']] == ['invalid_design_role'] * 2
    assert build_sections(claims, 'experiment_design')


def test_revision_checker_retains_design_definitions_without_promoting_context_facts():
    captured = []
    def invoke(**kwargs):
        captured.append(kwargs)
        return {'content': json.dumps([{'claimId': 'fix', 'status': 'passed'}])}
    target = {'claimId': 'fix', 'kind': 'proposal', 'text': 'Use the defined paired loss.', 'evidenceRefs': []}
    context = [{'claimId': 'definition', 'kind': 'proposal', 'text': 'L=-PSNR',
                'conditions': {'unit': 'scene'}},
               {'claimId': 'fact', 'kind': 'reported', 'text': 'UNRELATED FACT', 'evidenceRefs': ['x']}]
    result = BudgetedSemanticChecker(invoke, 'r').check_revisions([target], [], context)
    assert [v['claimId'] for v in result] == ['fix']
    assert captured[0]['node'] == 'verify_repair_design_science' and captured[0]['use_reserve']
    assert 'L=-PSNR' in captured[0]['prompt'] and 'scene' in captured[0]['prompt']
    assert 'UNRELATED FACT' not in captured[0]['prompt']


def test_generic_pass_without_specific_configuration_audit_is_rejected():
    c = {'claimId': 'd', 'kind': 'proposal', 'designRole': 'data',
         'text': 'Use multiple scenes, a fixed split and the same seed.', 'evidenceRefs': []}
    checker = BudgetedSemanticChecker(lambda **kw: {'content': json.dumps([
        {'claimId': 'd', 'status': 'passed', 'reason': 'The configuration is complete.'}])}, 'r')
    result = verify_claims([c], [], checker)
    assert not result['accepted']
    assert 'split' in result['rejected'][0]['detail']


def test_measurement_scope_is_read_after_brief_and_used_in_prompt_and_audit():
    scope = {'domains': None}
    text = 'Negate PSNR, average held-out views within each scene, then average paired scene losses.'
    c = {'claimId': 'm', 'kind': 'proposal', 'designRole': 'metrics', 'text': text, 'evidenceRefs': []}
    prompts = []
    def invoke(**kwargs):
        prompts.append(kwargs['prompt'])
        return {'content': json.dumps([{'claimId': 'm', 'status': 'passed', 'designAudit': {
            'quality_protocol': {'claimId': 'm', 'quote': text}}}])}
    checker = BudgetedSemanticChecker(invoke, 'r', metric_domains=lambda: scope['domains'])
    scope['domains'] = ['quality']
    assert verify_claims([c], [], checker)['accepted']
    assert 'speed_protocol' not in prompts[-1] and 'storage_protocol' not in prompts[-1]
    scope['domains'] = ['quality', 'speed']
    result = verify_claims([c], [], checker)
    assert not result['accepted']
    assert 'speed_protocol' in result['rejected'][0]['detail']


def test_brief_grounds_metric_scope_in_original_question():
    from services.deep_research.graph import make_resolve_brief_node
    record = {'question': '如何分离图像质量损失？', 'status': 'running', 'state': {}}
    def update(rid, fn, **kwargs):
        nonlocal record
        record = fn(record)
        return record
    invoke = lambda *args: {'content': json.dumps({'outputKind': 'experiment_design',
        'measurementScope': [{'domain': 'quality', 'requestExcerpt': '图像质量'}]})}
    make_resolve_brief_node(invoke, update)({'run_id': 'r'})
    assert record['state']['metricDomains'] == ['quality']
