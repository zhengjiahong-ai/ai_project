from copy import deepcopy
from unittest.mock import Mock

import pytest
import requests

from services.deep_research.contracts import DeepResearchError
from services.deep_research.located_evidence import located_evidence_factory
from services.deep_research.verification import make_evidence

QUOTE = 'Each anchor predicts attributes from the camera direction and distance.'


def setup():
    source = dict(workId='paper', versionId='v1', contentHash='chunk-hash', accessLevel='fulltext')
    record = {'materials': [{'materialId': 'paper', 'versionId': 'v1', 'contentHash': 'pdf-hash'}],
              'state': {'sources': [], 'evidence': [{'location': {'page': 1}}]}}
    repo = Mock()
    repo.require_run.return_value = record
    local = Mock()
    local.load_pages.return_value = (record['materials'][0], [{'page': 2, 'text': QUOTE}])
    return located_evidence_factory(repo, 'run', local), source, record, local


def test_new_identity_uses_physical_page_without_mutating_history():
    create, source, record, local = setup()
    before = deepcopy(record)
    args = dict(source=source, quote=QUOTE, original=QUOTE, location={'page': 1, 'section': 'Introduction'},
                obligation_ids=['o'])
    old = make_evidence(**args)
    new = create(**args)
    assert new['location']['page'] == 2
    assert new['location']['pageResolution'] == 'exact'
    assert new['evidenceId'] != old['evidenceId']
    assert new['quote'] == old['quote'] and new['verification']['literal'] == 'passed'
    assert record == before and args['location']['page'] == 1
    local.load_pages.assert_called_once_with('paper')


@pytest.mark.parametrize('error', [DeepResearchError('scope_revoked', 'revoked'),
                                  DeepResearchError('source_changed', 'changed')])
def test_scope_and_version_failures_are_not_hidden(error):
    create, source, _, local = setup()
    local.load_pages.side_effect = error
    with pytest.raises(DeepResearchError):
        create(source, QUOTE, QUOTE, location={'page': 1}, obligation_ids=['o'])


@pytest.mark.parametrize('error', [DeepResearchError('source_unavailable', 'unavailable'), requests.Timeout()])
def test_unavailable_pdf_does_not_publish_stale_page(error):
    create, source, _, local = setup()
    local.load_pages.side_effect = error
    ev = create(source, QUOTE, QUOTE, location={'page': 1}, obligation_ids=['o'])
    assert 'page' not in ev['location']
    assert ev['location']['pageResolution'] == 'unresolved'


def test_external_abstract_does_not_fetch_task_pdf():
    create, source, _, local = setup()
    source.update(workId='external', accessLevel='abstract')
    ev = create(source, QUOTE, QUOTE, location={'section': 'Abstract'}, obligation_ids=['o'])
    assert ev['location'] == {'section': 'Abstract'}
    local.load_pages.assert_not_called()


def test_only_verified_serialized_table_row_preserves_geometry():
    create, source, record, local = setup()
    quote = 'Table row 1: Ours | 120'
    packet = {'groups': [['Scenes', ['FPS']]], 'rows': [[1, 'Ours', ['120']]]}
    record['state']['sources'] = [{**source, 'tableData': packet}]
    location = {'page': 8, 'table': 't1', 'bbox': [0, 0, 1, 1]}
    ev = create(source, quote, quote, location=location, obligation_ids=['o'])
    assert ev['location'] == location
    local.load_pages.assert_not_called()
    record['state']['sources'][0]['tableData'] = None
    ev = create(source, quote, quote, location=location, obligation_ids=['o'])
    assert 'page' not in ev['location']


def test_page_match_does_not_bypass_literal_evidence_check():
    create, source, _, _ = setup()
    with pytest.raises(ValueError, match='Quotation'):
        create(source, QUOTE, 'Different original', location={'page': 1}, obligation_ids=['o'])
