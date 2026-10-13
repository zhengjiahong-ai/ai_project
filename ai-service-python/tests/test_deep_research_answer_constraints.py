import json
from unittest.mock import Mock

from services.deep_research.answer_constraints import compact_answer, requested_character_limit


def test_prompt_local_evidence_aliases_resolve_exactly_without_prefix_guessing():
    from services.deep_research.answer_constraints import resolve_evidence_aliases
    report = {'claims': [{'evidenceRefs': ['E1', 'ev_1234', 'E99']}]}
    result = resolve_evidence_aliases(report, {'E1': 'ev_123456789abcdef'})
    assert result['claims'][0]['evidenceRefs'] == ['ev_123456789abcdef', 'ev_1234', 'E99']


def test_bounded_compaction_retains_claim_identity_before_reverification():
    claim = {'claimId': 'c', 'text': '很长的结论' * 30, 'kind': 'reported', 'evidenceRefs': ['e']}
    compact = {'sections': [], 'claims': [{**claim, 'text': '测试条件下画质接近，仍有损失。'}]}
    invoke = Mock(return_value={'content': json.dumps(compact)})
    assert compact_answer({'claims': [claim]}, '两点，80字以内', invoke, json.loads) == compact
    invoke.assert_called_once()
    assert requested_character_limit('不超过300字') == 300


def test_compaction_cannot_change_sources_or_evade_length_with_conditions():
    claim = {'claimId': 'c', 'text': '很长的结论' * 30, 'kind': 'reported', 'evidenceRefs': ['e']}
    invoke = Mock(return_value={'content': json.dumps({'claims': [{**claim, 'text': '简短', 'evidenceRefs': ['foreign']}]})})
    assert compact_answer({'claims': [claim]}, '80字以内', invoke, json.loads) is None
    invoke.return_value = {'content': json.dumps({'claims': [{**claim, 'text': '简短', 'conditions': {'重复': '条件' * 100}}]})}
    assert compact_answer({'claims': [claim]}, '80字以内', invoke, json.loads) is None


def test_unconstrained_or_short_answers_do_not_add_paid_calls():
    report = {'claims': [{'claimId': 'c', 'text': '短结论'}]}
    invoke = Mock()
    assert compact_answer(report, '80字以内', invoke, json.loads) is report
    assert compact_answer(report, '详细比较', invoke, json.loads) is report
    invoke.assert_not_called()


def test_truncated_compaction_is_rejected_even_when_json_is_valid():
    from types import SimpleNamespace
    report = {'claims': [{'claimId': 'c', 'text': 'Very long claim ' * 100}]}
    content = json.dumps({'claims': [{'claimId': 'c', 'text': 'Short'}]})
    for response in ({'content': content, 'finishReason': 'length'},
                     {'content': content, 'finish_reason': 'length'},
                     SimpleNamespace(content=content, finish_reason='length')):
        invoke = Mock(return_value=response)
        assert compact_answer(report, '80字以内', invoke, json.loads) is None
        invoke.assert_called_once()


def test_string_conditions_are_preserved_before_length_and_evidence_checks():
    report = {'claims': [{'claimId': 'c', 'text': '结论', 'conditions': '只在当前测试设置下'}]}
    invoke = Mock()
    result = compact_answer(report, '80字以内', invoke, json.loads)
    assert result['claims'][0]['conditions'] == {'context': '只在当前测试设置下'}
    invoke.assert_not_called()


def test_compaction_can_drop_secondary_claims_but_retains_kept_identity():
    important = {'claimId': 'answer', 'kind': 'inference', 'text': '需要保留的判断' * 20, 'evidenceRefs': ['e']}
    secondary = {'claimId': 'extra', 'kind': 'reported', 'text': '不影响判断的背景' * 20, 'evidenceRefs': ['e2']}
    compact = {'claims': [{**important, 'text': '当前证据不足以支持普遍结论。'}]}
    invoke = Mock(return_value={'content': json.dumps(compact)})
    assert compact_answer({'claims': [important, secondary]}, '100字以内', invoke, json.loads) == compact
    assert 'MAY DROP' in invoke.call_args.args[0]


def test_list_conditions_are_preserved_without_wasting_a_compaction_call():
    report = {'claims': [{'text': '摘要提出三部分方法。', 'conditions': ['仅摘要', '未读取全文']}]}
    invoke = Mock()
    result = compact_answer(report, '300字以内', invoke, json.loads)
    assert result['claims'][0]['conditions'] == {'1': '仅摘要', '2': '未读取全文'}
    invoke.assert_not_called()


def test_comparison_compression_keeps_each_paper_and_joint_judgment():
    claims = [{'claimId': key, 'kind': kind, 'text': '长结论' * 100, 'evidenceRefs': refs}
              for key, kind, refs in [('a', 'reported', ['ea']), ('extra', 'reported', ['ea']),
                                      ('b', 'reported', ['eb']), ('joint', 'inference', ['ea', 'eb'])]]
    evidence = [{'evidenceId': 'ea', 'sourceWorkId': 'A'}, {'evidenceId': 'eb', 'sourceWorkId': 'B'}]
    patches = [{'claimId': key, 'text': text, 'conditions': {}} for key, text in
               [('a', '甲论文报告压缩结果。'), ('b', '乙论文报告渲染结果。'), ('joint', '两篇的实验条件尚未对齐，不能直接拼接百分比。')]]
    invoke = Mock(return_value={'content': json.dumps({'claims': patches})})
    result = compact_answer({'claims': claims}, '200字以内', invoke, json.loads,
                            output_kind='paper_comparison', evidence=evidence)
    assert [c['claimId'] for c in result['claims']] == ['a', 'b', 'joint']
    assert result['claims'][1]['evidenceRefs'] == ['eb']
    assert 'extra' not in invoke.call_args.args[0]
    invoke.return_value = {'content': json.dumps({'claims': patches[:1]})}
    assert compact_answer({'claims': claims}, '200字以内', invoke, json.loads,
                          output_kind='paper_comparison', evidence=evidence) is None


def test_short_rewrite_cannot_reintroduce_omitted_or_duplicate_claims():
    claims = [{'claimId': str(i), 'text': '背景' * 100, 'kind': 'reported', 'evidenceRefs': ['e']} for i in range(4)]
    invoke = Mock(return_value={'content': json.dumps({'claims': [claims[3]]})})
    assert compact_answer({'claims': claims}, '100字以内', invoke, json.loads) is None
    patch = {'claimId': '0', 'text': '短结论'}
    invoke.return_value = {'content': json.dumps({'claims': [patch, patch]})}
    assert compact_answer({'claims': claims}, '100字以内', invoke, json.loads) is None
