"""Versioned citations must stay distinct before quote validation."""
import pytest

from services.research_executor import ensure_stable_source_ids, merge_evidence_lists
from services.research_task_results import _ensure_stable_source_ids as result_ids
from services.tools._common import _ensure_stable_source_ids as tool_ids
from services.research_synthesis import validate_claim


@pytest.mark.parametrize('normalizer', [tool_ids, result_ids, ensure_stable_source_ids])
def test_versioned_chunk_ids_survive_each_boundary(normalizer):
    prefix = 'a' * 64 + '.pdf-v' + 'b' * 16
    sources = [{'sourceId': prefix + '-chunk-' + str(i), 'pdfId': 'paper',
                'text': 'Distinct body evidence number ' + str(i)} for i in (1, 2)]
    result = normalizer(sources, 'paper')
    assert [x['sourceId'] for x in result] == [x['sourceId'] for x in sources]
    checked = validate_claim({'summary': 'Second chunk supports this statement.', 'kind': 'reported',
                              'references': [{'sourceId': result[1]['sourceId'], 'quote': result[1]['text']}]}, result)
    assert checked['references'][0]['sourceId'] == sources[1]['sourceId']


@pytest.mark.parametrize('normalizer', [tool_ids, result_ids, ensure_stable_source_ids])
def test_oversized_ids_do_not_collapse_or_change_on_repeated_normalization(normalizer):
    sources = [{'sourceId': 'x' * 200 + str(i), 'text': str(i)} for i in (1, 2)]
    result = normalizer(sources, 'paper')
    assert len({x['sourceId'] for x in result}) == 2
    assert all(len(x['sourceId']) <= 180 for x in result)
    assert normalizer(result, 'paper') == result


def test_tool_to_research_merge_retains_both_chunks():
    prefix = 'a' * 64 + '.pdf-v' + 'b' * 16
    sources = [{'sourceId': prefix + '-chunk-' + str(i), 'pdfId': 'paper',
                'text': 'Content:\nDifferent evidence text ' + str(i)} for i in (1, 2)]
    merged = merge_evidence_lists(tool_ids(sources, 'paper'))
    assert len({x['sourceId'] for x in merged}) == 2
