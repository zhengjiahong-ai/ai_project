from copy import deepcopy
import json

import pytest

from services.deep_research.verification import make_evidence, verify_claims
from services.deep_research.answer_constraints import resolve_evidence_aliases
from services.deep_research.repair import repair_rejected


def fixture():
    quote = 'Table row 3: Ours* | 134 | 734MB | 154 | 411MB'
    ev = make_evidence({'workId': 'paper', 'versionId': 'v1', 'contentHash': 'hash', 'accessLevel': 'fulltext'},
                       quote, quote, location={'table': 't1'}, obligation_ids=[])
    ev['tableData'] = {'groups': [['Dataset A', ['FPS', 'Mem']], ['Dataset B', ['FPS', 'Mem']]],
                       'rows': [[3, 'Ours*', ['134', '734MB', '154', '411MB']]]}
    claim = {'claimId': 'c', 'kind': 'reported', 'text': 'Dataset A 的 Ours*：FPS 134，Mem 734MB',
             'evidenceRefs': [ev['evidenceId']], 'tableBindings': [
                 {'evidenceId': ev['evidenceId'], 'rowNumber': 3, 'groupIndex': 0, 'metric': 'FPS', 'value': '134'},
                 {'evidenceId': ev['evidenceId'], 'rowNumber': 3, 'groupIndex': 0, 'metric': 'Mem', 'value': '734MB'}]}
    return ev, claim


def check(ev, claim):
    return verify_claims([claim], [ev], lambda c, e: [{'claimId': 'c', 'status': 'passed'}])


def test_reported_cells_pass_only_with_visible_dataset_method_and_exact_binding():
    ev, claim = fixture()
    assert check(ev, claim)['accepted']


def test_dataset_descriptor_and_identifier_numbers_are_not_measurements():
    ev, claim = fixture()
    ev['tableData']['groups'][0][0] = 'Mip-NeRF 360 Datasets'
    claim['text'] = '论文Table 1的' + claim['text'].replace('Dataset A', 'Mip-NeRF360')
    claim['conditions'] = {'table': 'Table 1', 'dataset': 'Mip-NeRF 360 Datasets'}
    assert check(ev, claim)['accepted']
    assert not verify_claims([claim], [ev])['accepted']
    wrong = {**claim, 'text': claim['text'].replace('FPS 134', 'FPS 360')}
    assert check(ev, wrong)['rejected'][0]['reason'] == 'numeric_mismatch'
    for other in ('Mip-NeRF3600', 'Mip-NeRF360-heldout'):
        # A distinct split is not normalized away from the evidence identity.
        changed = deepcopy(ev)
        changed['tableData']['groups'][0][0] = other
        assert not check(changed, claim)['accepted']
        from services.deep_research.table_bindings import validate_table_bindings
        assert validate_table_bindings(claim, [changed]) == 'table_condition_not_displayed'


@pytest.mark.parametrize('mutation,reason', [
    (lambda c: c.pop('tableBindings'), 'missing_table_bindings'),
    (lambda c: c['tableBindings'][0].update(groupIndex=1), 'table_cell_mismatch'),
    (lambda c: c['tableBindings'][0].update(rowNumber=4), 'unverified_table_cell'),
    (lambda c: c['tableBindings'][0].update(evidenceId='foreign'), 'table_binding_outside_citation'),
    (lambda c: c.update(text=c['text'].replace('Dataset A', 'Dataset B')), 'table_condition_not_displayed'),
    (lambda c: c.update(text=c['text'].replace('Ours*', 'Ours')), 'table_condition_not_displayed'),
    (lambda c: c.update(text='Dataset A Ours* FPS134/154 Mem734MB'), 'ambiguous_table_series'),
    (lambda c: c['tableBindings'].pop(), 'unbound_table_measurement'),
])
def test_numbers_present_elsewhere_do_not_override_binding_errors(mutation, reason):
    ev, claim = fixture()
    mutation(claim)
    result = check(ev, claim)
    assert not result['accepted']
    assert result['rejected'][0]['reason'] == reason


def test_no_packet_or_uncited_row_cannot_support_declared_cell():
    ev, claim = fixture()
    ev.pop('tableData')
    assert check(ev, claim)['rejected'][0]['reason'] == 'unverified_table_cell'
    ev, claim = fixture()
    ev['tableData']['rows'][0][1] = 'Different'
    assert check(ev, claim)['rejected'][0]['reason'] == 'unverified_table_cell'


def test_alias_resolution_preserves_binding_identity():
    ev, claim = fixture()
    original = deepcopy(claim)
    claim['evidenceRefs'] = ['E1']
    for binding in claim['tableBindings']:
        binding['evidenceId'] = 'E1'
    assert resolve_evidence_aliases({'claims': [claim]}, {'E1': ev['evidenceId']})['claims'][0] == original


def test_explicit_caption_prose_does_not_require_invented_cell_bindings():
    text = 'With 2 SH degrees, SSIM drops from 0.927 to 0.926.'
    ev = make_evidence({'workId': 'p', 'versionId': 'v1', 'contentHash': 'h', 'accessLevel': 'fulltext'},
        text, text, location={'table': 't1', 'tableColumnMappingUnverified': True}, obligation_ids=[])
    c = {'claimId': 'c', 'kind': 'reported', 'text': '2阶SH下SSIM 0.926', 'evidenceRefs': [ev['evidenceId']]}
    assert check(ev, c)['accepted']
    assert not verify_claims([c], [ev])['accepted']
    assert check(ev, {**c, 'text': '2阶SH下SSIM 0.999'})['rejected'][0]['reason'] == 'numeric_mismatch'
    ev['quote'] = 'Table row 1: Ours | 2 | 0.926'
    assert check(ev, c)['rejected'][0]['reason'] == 'missing_table_bindings'


def test_mixed_citations_bind_only_measurements_not_explicit_in_cited_prose():
    table, _ = fixture()
    quote = 'We achieve at least 30 fps at 1080p.'
    prose = make_evidence({'workId': 'p', 'versionId': 'v1', 'contentHash': 'h', 'accessLevel': 'fulltext'},
        quote, quote, location={'page': 1}, obligation_ids=[])
    c = {'claimId': 'c', 'kind': 'reported', 'text': '论文报告1080p下至少30fps，并给出了模型存储表。',
         'evidenceRefs': [prose['evidenceId'], table['evidenceId']]}
    passed = lambda *_: [{'claimId': 'c', 'status': 'passed'}]
    assert verify_claims([c], [table, prose], passed)['accepted']
    wrong = {**c, 'text': 'FPS 134，Mem 734MB'}
    assert verify_claims([wrong], [table, prose], passed)['rejected'][0]['reason'] == 'missing_table_bindings'
    unrelated = {**c, 'evidenceRefs': [table['evidenceId']]}
    assert not verify_claims([unrelated], [table, prose], passed)['accepted']


@pytest.mark.parametrize('bindings', [42, 'E1', {}, [None], [{'evidenceId': []}]])
def test_malformed_bindings_reject_without_crashing(bindings):
    ev, claim = fixture()
    claim['tableBindings'] = bindings
    report = resolve_evidence_aliases({'claims': [claim]}, {})
    assert not check(ev, report['claims'][0])['accepted']


def test_repair_receives_exact_cells_and_revised_binding_is_checked_again():
    ev, valid = fixture()
    original = deepcopy(valid)
    original.pop('tableBindings')
    rejected = check(ev, original)
    def invoke(prompt):
        assert json.dumps(ev['tableData'], ensure_ascii=False) in prompt
        return {'content': json.dumps([valid])}
    repaired = repair_rejected({'claims': [original]}, rejected, [ev], '比较', invoke, json.loads)
    assert check(ev, repaired[0])['accepted']
    repaired[0]['tableBindings'][0]['groupIndex'] = 1
    assert not check(ev, repaired[0])['accepted']
