from unittest.mock import Mock

from services.deep_research.facade import ResearchFacade


def test_source_response_retains_exact_quote_and_location_for_each_evidence():
    source = {'sourceId': 's', 'workId': 'p', 'contentHash': 'h', 'text': 'Private full passage'}
    evidence = [dict(evidenceId=key, sourceId='s', sourceWorkId='p', contentHash='h',
                     quote=quote, location={'page': page})
                for key, quote, page in [('baseline', 'Baseline row', 6), ('ours', 'Author row', 7)]]
    evidence.append({**evidence[0], 'evidenceId': 'foreign', 'sourceId': 'other'})
    repo = Mock()
    repo.require_run.return_value = {'state': {'sources': [source], 'evidence': evidence}}
    facade = ResearchFacade(repo, lambda **kwargs: None, llm_client=Mock())
    try:
        result = facade.get_sources('r')[0]
        assert result['evidenceQuotes'] == {'baseline': {'quote': 'Baseline row', 'location': {'page': 6}},
                                           'ours': {'quote': 'Author row', 'location': {'page': 7}}}
        assert 'text' not in result
        assert result['evidenceIds'] == ['baseline', 'ours']
    finally:
        facade.shutdown(wait=True)
