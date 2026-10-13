"""Behavioral gates for complete judgments, calibrated coverage and scoped composition."""
import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from schemas.conversation import ConversationCapabilityRequest
from services.evidence_quotes import prepare_quote_sources
from services.grounded_critique import synthesize_critique
from services.conversation_capability_service import execute_conversation, critique_targets
from services.focused_evidence import select_critique_evidence

SOURCES = [
    {'sourceId': 'method', 'pdfId': 'A.pdf', 'pageIndex': 1, 'text': 'Pruning reduces storage with a quality tradeoff.'},
    {'sourceId': 'settings', 'pdfId': 'A.pdf', 'pageIndex': 2, 'text': 'The baseline is retrained under the same experimental settings.'},
]


def fixture():
    _, _, catalog = prepare_quote_sources(SOURCES)
    def claim(summary, sid):
        return {'summary': summary, 'references': [{'quoteId': next(iter(catalog[sid]))}]}
    return {'questionParts': [{'id': 'main', 'text': '质量主张的适用条件'}],
            'assessments': [
                {'section': 'weakness', 'title': '压缩代价', 'topicKey': 'quality', 'conclusion': 'inference',
                 'observation': claim('作者说明剪枝减少存储并伴随质量取舍。', 'method'),
                 'inference': claim('评价剪枝应同时核对存储收益和质量代价。', 'method')},
                {'section': 'risk', 'title': '比较条件', 'topicKey': 'conditions', 'conclusion': 'inference',
                 'observation': claim('作者在相同实验设置下重训基线。', 'settings'),
                 'inference': claim('这一比较的结论受相同训练设置约束。', 'settings')},
            ]}


def run(value=None, question='只给最关键的两点', sources=SOURCES):
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(value or fixture(), ensure_ascii=False)) as model:
        result = synthesize_critique(question, sources, allow_partial=True)
    assert model.call_count == 1
    return result


def test_two_complete_groups_survive_chat_artifact_and_validation():
    result = run()
    critique = result['critique']
    assert len(critique['issues']) == 2 and len(critique['claims']) == 4
    assert len(critique['chatBlocks']) == 2
    assert '这一比较的结论受相同训练设置约束。' in result['summary']
    assert '作者在相同实验设置下重训基线。' in result['summary']
    assert '补充结论' not in result['message']
    assert not result['partial']
    assert critique['presentation']['chatIssueIds'] == critique['presentation']['artifactIssueIds']


def test_requested_decision_count_and_optional_pending_are_not_hidden_as_success():
    value = fixture()
    value['assessments'] = value['assessments'][:1]
    value['pendingQuestions'] = [{'topic': '新场景下的质量效果'}]
    result = run(value, question='最影响复现和使用决策的两个判断是什么？')
    assert result['partial'] and result['critique']['question']['requestedPoints'] == 2
    assert '仅形成1项' in result['summary']
    complete = run({**fixture(), 'pendingQuestions': [{'topic': '新场景下的质量效果'}]})
    assert '待核查：新场景' not in complete['summary']
    assert complete['critique']['pending']


def test_invalid_optional_pending_does_not_discard_valid_judgments_or_shift_part_identity():
    value = fixture()
    value['questionParts'].append({'id': 'next', 'text': '另一个需要核查的条件'})
    value['pendingQuestions'] = [{'topic': '论文没有给出实验', 'questionPartIds': ['main']},
                                 {'topic': '其他视角下的表现', 'questionPartIds': ['next']}]
    result = run(value)
    assert len(result['critique']['issues']) == 2
    assert result['critique']['pending'][0]['questionPartIds'] == ['next']
    assert '论文没有给出实验' not in result['message']


def test_inability_to_match_reported_effect_is_not_a_paper_absence_claim():
    value = fixture()
    value['assessments'][0]['inference']['summary'] = '更改剪枝配置可能无法得到作者报告的质量平衡。'
    result = run(value)
    assert len(result['critique']['issues']) == 2


def test_training_supervision_cannot_become_a_test_view_quality_boundary():
    value = fixture()
    value['assessments'][0]['inference']['summary'] = '采用训练视角优化，因此质量平衡主要对应训练视角内的场景表示。'
    result = run(value)
    assert len(result['critique']['issues']) == 1 and result['partial']


def test_overall_cannot_retain_references_from_a_discarded_issue():
    value = fixture()
    value['overall'] = {'kind': 'inference', **value['assessments'][1]['inference']}
    value['assessments'][1]['inference']['summary'] = '论文没有给出验证实验。'
    result = run(value)
    assert result['critique']['presentation']['leadClaimIds'] == []


def test_repeated_topic_merges_evidence_without_filling_requested_count():
    value = fixture()
    value['assessments'][1]['topicKey'] = 'quality'
    result = run(value)
    assert len(result['critique']['issues']) == 1 and len(result['critique']['claims']) == 4
    assert result['partial'] and '仅形成1项' in result['summary']


def test_rejected_irrelevant_candidate_does_not_mean_failed_coverage():
    value = fixture()
    value['assessments'].append({'section': 'risk', 'observation': {'summary': '论文未提供动态实验。', 'references': []}})
    result = run(value)
    assert len(result['critique']['issues']) == 2 and not result['partial']
    assert '拒绝' not in result['summary'] and '部分分析' not in result['summary']


def test_invalid_conclusion_drops_dependent_point_but_preserves_other_point():
    value = fixture()
    value['assessments'][1]['inference']['references'] = [{'quoteId': 'unknown'}]
    result = run(value)
    assert len(result['critique']['issues']) == 1 and result['partial']
    assert '作者在相同实验设置下重训基线' not in result['message']


@pytest.mark.parametrize('question,limit', [('用150字回答，只给两点', 150), ('只用一句话', 400), ('只用20字总结', 20), ('1字以内', 1)])
def test_budget_never_slices_claim_condition_or_citation(question, limit):
    result = run(question=question)
    assert len(result['summary']) <= limit
    if '一句话' in question:
        assert result['summary'].count('。') <= 1
    for block in result['critique']['chatBlocks']:
        assert block['text'].endswith('[1]') or block['text'].endswith('[2]')
    assert len(result['critique']['artifactBlocks']) == 2


def test_per_point_limit_does_not_replace_the_whole_answer_limit():
    from services.conversation_capability_service import _requested_chat_limit
    assert _requested_chat_limit('每个结论句最多70字，给两点', 400) == 400
    assert _requested_chat_limit('每点60字，总共150字', 400) == 150


def test_cited_experiment_step_identifiers_are_not_unbound_measurements():
    sources = [{'sourceId': 'ablation', 'pdfId': 'A.pdf', 'text': 'Pruning and recovery (Exp #1 →3) show negligible quality change.'}]
    _, _, catalog = prepare_quote_sources(sources)
    value = {'assessments': [{'section': 'contribution', 'observation': {
        'summary': '作者报告剪枝恢复（Exp #1→3）的质量变化可忽略。',
        'references': [{'quoteId': next(iter(catalog['ablation']))}]}}]}
    assert len(run(value, sources=sources)['critique']['issues']) == 1
    value['assessments'][0]['observation']['summary'] = '作者报告剪枝恢复（Exp #1→4）的质量变化可忽略。'
    with pytest.raises(ValueError):
        run(value, sources=sources)


def test_explicit_author_limitation_is_retained_with_direct_attributed_reference():
    sources = [{'sourceId': 'limit', 'pdfId': 'A.pdf', 'text': 'We did not evaluate dynamic scenes; this is a limitation of our experiments.'}]
    _, _, catalog = prepare_quote_sources(sources)
    value = {'assessments': [{'section': 'risk', 'conclusion': 'observation',
             'observation': {'summary': '作者明确说明没有评估动态场景。', 'authorLimitation': True,
                             'references': [{'quoteId': next(iter(catalog['limit']))}]}}]}
    result = run(value, sources=sources)
    assert len(result['critique']['issues']) == 1
    value['assessments'][0]['observation']['references'] = [{'quoteId': next(iter(prepare_quote_sources(SOURCES)[2]['method']))}]
    with pytest.raises(ValueError, match='没有给出结论'):
        run(value)


def test_mechanism_does_not_complete_an_explicitly_unresolved_empirical_subquestion():
    value = fixture()
    value['unresolvedQuestionPartIds'] = ['main']
    result = run(value)
    assert result['partial'] and result['critique']['coverage']['answeredQuestionPartIds'] == []
    assert '尚不能判断' in result['message']


def test_unseen_dataset_topic_and_bare_literal_ids_are_not_false_absence_or_free_quotes():
    value = fixture()
    value['pendingQuestions'] = [{'topic': '未见数据集或极端视角下的画质保持情况'}]
    for item in value['assessments']:
        for field in ('observation', 'inference'):
            item[field]['references'] = [ref['quoteId'] for ref in item[field]['references']]
    result = run(value)
    assert len(result['critique']['issues']) == 2
    assert '未见数据集' in result['message']
    assert all(isinstance(ref, dict) and ref['quote'] for claim in result['critique']['claims'] for ref in claim['references'])


def test_current_paper_is_target_without_removing_allowed_materials(monkeypatch):
    captured = []
    result = run()
    monkeypatch.setattr('services.conversation_capability_service._critique', lambda request, paper: captured.append(paper) or result)
    request = ConversationCapabilityRequest(taskId='task', message='这篇只给两点', capability='critique',
        allowedPaperIds=['A.pdf', 'B.pdf'], primaryPaperId='A.pdf')
    answer = execute_conversation(request)
    assert captured == ['A.pdf']
    assert answer['critique']['scope']['allowedPaperIds'] == ['A.pdf', 'B.pdf']
    assert answer['critique']['scope']['targetPaperIds'] == ['A.pdf']
    assert answer['artifact']['paperIds'] == ['A.pdf', 'B.pdf']
    assert len(answer['critique']['chatBlocks']) == 2


def test_large_task_can_critique_one_target_within_the_four_target_limit(monkeypatch):
    captured = []
    result = run()
    monkeypatch.setattr('services.conversation_capability_service._critique', lambda request, paper: captured.append(paper) or result)
    request = ConversationCapabilityRequest(taskId='task', message='批判这篇', capability='critique',
        allowedPaperIds=['A.pdf', *[f'{i}.pdf' for i in range(8)]], primaryPaperId='A.pdf')
    answer = execute_conversation(request)
    assert captured == ['A.pdf'] and len(answer['materialScope']['allowedPaperIds']) == 9


def test_followup_binds_saved_issue_version_and_separates_edited_prose(monkeypatch):
    from services import chat_service
    captured = []
    monkeypatch.setattr(chat_service, 'chat', lambda request: captured.append(request) or {'message': '解释已保存的观点。', 'rag_sources': []})
    result = run()
    critique = result['critique']
    context = {'sourceArtifactId': 'artifact', 'version': 'saved-version', 'scope': critique['scope'],
               'focusedIssueId': critique['issues'][1]['id'], 'claims': critique['claims'], 'issues': critique['issues'],
               'text': result['message'], 'edited': False}
    request = ConversationCapabilityRequest(taskId='task', message='第二点为什么', allowedPaperIds=['A.pdf'], critiqueContext=context)
    execute_conversation(request)
    prompt = captured[-1].message
    assert 'saved-version' in prompt and critique['issues'][1]['id'] in prompt
    # The text may still mention earlier points, but the structural selection is explicit.
    assert '"issues": [{"id": "' + critique['issues'][1]['id'] in prompt
    execute_conversation(request.model_copy(update={'critiqueContext': {**context, 'edited': True, 'text': '用户改动'}}))
    assert '"claims": []' in captured[-1].message and '"issues": []' in captured[-1].message
    assert '用户编辑不可当作论文事实' in captured[-1].message


def test_composed_critique_keeps_complete_conclusions_and_one_shared_artifact(monkeypatch):
    critique = run()
    monkeypatch.setattr('services.conversation_capability_service._run_step', lambda step, request, prior:
        [{'message': '先解释压缩取舍。', 'rag_sources': []}] if step == 'chat' else [critique])
    request = ConversationCapabilityRequest(taskId='task', message='用150字先解释再批判两点', capability='compose',
        steps=['chat', 'critique'], allowedPaperIds=['A.pdf'], primaryPaperId='A.pdf')
    answer = execute_conversation(request)
    assert len(answer['message']) <= 150
    assert '先解释压缩取舍。' in answer['message']
    assert all(issue['id'] in answer['critique']['presentation']['artifactIssueIds'] for issue in critique['critique']['issues'])
    assert not answer['critique']['presentation']['standalone']
    assert answer['artifact']['text'].count('先解释压缩取舍。') == 1


def test_ambiguous_object_is_resolved_before_any_composed_provider(monkeypatch):
    monkeypatch.setattr('services.conversation_capability_service._chat', lambda *args: pytest.fail('provider must not run'))
    request = ConversationCapabilityRequest(taskId='task', message='批判画质主张', capability='compose',
        allowedPaperIds=['A.pdf', 'B.pdf'], steps=['chat', 'critique'])
    with pytest.raises(ValueError, match='哪篇'):
        execute_conversation(request)
    assert critique_targets(request.model_copy(update={'targetPaperIds': ['B.pdf']})) == ['B.pdf']


def test_mult_paper_repeated_local_citations_are_remapped_once(monkeypatch):
    first = run()
    second = deepcopy(first)
    for source in second['rag_sources']:
        source['pdfId'] = 'B.pdf'
    second['critique']['scope'] = {'allowedPaperIds': ['B.pdf'], 'targetPaperIds': ['B.pdf'], 'primaryPaperId': 'B.pdf'}
    # Independent generation gives paper-specific claim/issue identities.
    remap = {}
    for field in ('claims', 'issues'):
        for item in second['critique'][field]:
            remap[item['id']] = item['id'] + '-b'
            item['id'] += '-b'
            item['paperIds'] = ['B.pdf']
    for issue in second['critique']['issues']:
        issue['conclusionClaimId'] = remap[issue['conclusionClaimId']]
        issue['supportClaimIds'] = [remap[cid] for cid in issue['supportClaimIds']]
    for field in ('chatBlocks', 'artifactBlocks'):
        for block in second['critique'][field]:
            block['issueId'] = remap[block['issueId']]
    for field in ('chatIssueIds', 'artifactIssueIds'):
        second['critique']['presentation'][field] = [remap[cid] for cid in second['critique']['presentation'][field]]
    monkeypatch.setattr('services.conversation_capability_service._critique', lambda request, paper: first if paper == 'A.pdf' else second)
    request = ConversationCapabilityRequest(taskId='task', message='分别批判两篇论文', capability='critique', allowedPaperIds=['A.pdf', 'B.pdf'])
    answer = execute_conversation(request)
    assert len({source['sourceId'] for source in answer['sources']}) == 4
    assert '[3]' in answer['artifact']['text'] and '[4]' in answer['artifact']['text']
    assert len({claim['id'] for claim in answer['critique']['claims']}) == 8
    assert answer['critique']['presentation']['standalone']
    assert [issue['paperIds'][0] for issue in answer['critique']['issues']] == ['A.pdf', 'B.pdf', 'A.pdf', 'B.pdf']
    assert [issue['paperIds'][0] for issue in answer['critique']['issues'][:2]] == ['A.pdf', 'B.pdf']


def test_chinese_adjacent_metric_needs_its_own_selected_quote():
    value = fixture()
    value['assessments'][0]['observation']['summary'] = '作者报告剪枝导致SSIM下降。'
    result = run(value)
    assert all('SSIM' not in claim['text'] for claim in result['critique']['claims'])
    assert len(result['critique']['issues']) == 2


def test_improved_metric_is_not_reported_as_restored():
    sources = [{'sourceId': 'metric', 'pdfId': 'A.pdf', 'text': 'Fine tuning improves SSIM.'}]
    _, _, catalog = prepare_quote_sources(sources)
    claim = {'summary': '微调使SSIM恢复。', 'references': [{'quoteId': next(iter(catalog['metric']))}]}
    value = {'assessments': [{'section': 'risk', 'observation': claim}],
             'pendingQuestions': [{'topic': '微调后的质量范围'}]}
    result = run(value, sources=sources)
    assert not result['critique']['issues']
    assert 'SSIM恢复' not in result['message']


def test_evidence_selection_reserves_results_conditions_ablation_and_counterevidence():
    def item(index, section, text):
        return {'sourceId': str(index), 'pdfId': 'A', 'chunkIndex': index, 'text': text, 'metadata': {'section_title': section}}
    corpus = [item(i, 'Method', 'Pruning and compression are defined by the significance score.') for i in range(7)]
    corpus += [item(10, 'Experimental Setup', 'The dataset and baseline use the same GPU hardware.'),
               item(11, 'Quantitative Results', 'Table: PSNR SSIM LPIPS quality results.'),
               item(12, 'Ablation', 'Ablation isolates pruning and distillation.'),
               item(13, 'Limitations', 'The method fails on transparent objects.')]
    selected = select_critique_evidence(corpus[:7], corpus, '压缩后画质几乎不变可信吗', limit=8)
    assert {10, 11, 12, 13} <= {item['chunkIndex'] for item in selected}
    assert all(item in corpus for item in selected)
