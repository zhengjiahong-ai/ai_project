import pytest

from services.deep_research_academic import (
    AcademicAccessError, AcademicPolicy, AcademicSourceClient, checked_arxiv_id, pinned_https_get,
)


def test_disabled_policy_rejects_before_transport():
    calls = []
    client = AcademicSourceClient(AcademicPolicy(), lambda *args: calls.append(args))
    with pytest.raises(AcademicAccessError):
        client.discover('Gaussian splatting')
    assert not calls


def test_fulltext_requires_separate_permission():
    calls = []
    client = AcademicSourceClient(AcademicPolicy(enabled=True, mode='academic_external'), lambda *args: calls.append(args))
    with pytest.raises(AcademicAccessError):
        client.fetch_fulltext('2311.17245v6')
    assert not calls


def test_fulltext_parse_has_process_timeout_and_no_retry(monkeypatch):
    import subprocess
    from services import deep_research_academic as academic
    calls = []
    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(academic.subprocess, 'run', timeout)
    client = AcademicSourceClient(AcademicPolicy(enabled=True, mode='academic_external', allow_fulltext=True),
                                  lambda *args: ('application/pdf', b'%PDF-malformed'))
    with pytest.raises(AcademicAccessError, match='解析超时'):
        client.fetch_fulltext('2311.17245v6')
    assert len(calls) == 1
    assert calls[0]['timeout'] == 20


@pytest.mark.parametrize('value', ['https://localhost/a', '../secret', '2311.17245?x=1', '2311.17245#x', '2311.17245v0', '', None])
def test_identifier_cannot_supply_urls_or_paths(value):
    with pytest.raises(AcademicAccessError):
        checked_arxiv_id(value)


def test_discovery_preserves_version_and_abstract_identity():
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2311.17245v6</id>
    <title> Example paper </title><summary>Abstract only.</summary></entry></feed>'''
    calls = []
    def transport(*args):
        calls.append(args)
        return 'application/atom+xml', atom
    client = AcademicSourceClient(AcademicPolicy(enabled=True, mode='academic_external'), transport)
    result = client.discover('all:Gaussian AND all:compression')
    assert result[0]['workId'] == 'arxiv:2311.17245'
    assert result[0]['versionId'] == 'arxiv:2311.17245v6'
    assert result[0]['accessLevel'] == 'abstract'
    assert 'pages' not in result[0]
    assert len(calls) == 1
    assert calls[0][0] == 'export.arxiv.org'
    assert calls[0][1].startswith('/api/query?')


def test_exact_identifier_lookup_filters_unrelated_provider_results():
    from urllib.parse import parse_qs, urlsplit
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom">
    <entry><id>http://arxiv.org/abs/1304.1836</id><title>Unrelated</title><summary>Wrong paper</summary></entry>
    <entry><id>http://arxiv.org/abs/2311.17245v6</id><title>Target</title><summary>Abstract</summary></entry></feed>'''
    calls = []
    def transport(*args):
        calls.append(args)
        return 'application/atom+xml', atom
    client = AcademicSourceClient(AcademicPolicy(enabled=True, mode='academic_external'), transport)
    results = client.discover('LightGaussian arXiv 2311.17245 compression', limit=3)
    assert [r['workId'] for r in results] == ['arxiv:2311.17245']
    params = parse_qs(urlsplit(calls[0][1]).query)
    assert params['id_list'] == ['2311.17245'] and 'search_query' not in params


def test_plain_discovery_omits_generic_request_words():
    from urllib.parse import parse_qs, urlsplit
    calls = []
    def transport(*args):
        calls.append(args)
        return 'application/atom+xml', b'<feed xmlns="http://www.w3.org/2005/Atom" />'
    client = AcademicSourceClient(AcademicPolicy(enabled=True, mode='academic_external'), transport)
    client.discover('LightGaussian paper compression method components')
    assert parse_qs(urlsplit(calls[0][1]).query)['search_query'] == ['all:"LightGaussian" AND all:"compression"']
    with pytest.raises(AcademicAccessError, match='缺少主题'):
        client.discover('the paper method')
    assert len(calls) == 1


def test_rejects_entities_and_does_not_retry():
    calls = []
    def transport(*args):
        calls.append(args)
        return 'application/xml', b'<!DOCTYPE feed [<!ENTITY x SYSTEM "file:///secret">]><feed/>'
    client = AcademicSourceClient(AcademicPolicy(enabled=True, mode='academic_external'), transport)
    with pytest.raises(AcademicAccessError):
        client.discover('topic')
    assert len(calls) == 1


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
def test_private_dns_is_rejected_before_connection(monkeypatch, address):
    from services import deep_research_academic as academic
    def forbidden(*args, **kwargs):
        raise AssertionError('must not construct connection')
    monkeypatch.setattr(academic.http.client, 'HTTPSConnection', forbidden)
    with pytest.raises(AcademicAccessError):
        pinned_https_get('arxiv.org', '/pdf/2311.17245v6', 100, resolver=lambda _: [address])


@pytest.mark.parametrize('status', [301, 302, 307, 308, 429, 500])
def test_redirect_and_failure_never_reissue_request(monkeypatch, status):
    from services import deep_research_academic as academic
    calls = []
    class Response:
        def getheader(self, *args): return None
    response = Response()
    response.status = status
    class Connection:
        def __init__(self, host, **kwargs): self.host = host
        def request(self, *args, **kwargs): calls.append(args)
        def getresponse(self): return response
        def close(self): calls.append('closed')
    monkeypatch.setattr(academic.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(AcademicAccessError):
        pinned_https_get('arxiv.org', '/pdf/2311.17245v6', 100, resolver=lambda _: ['8.8.8.8'])
    assert len([call for call in calls if isinstance(call, tuple)]) == 1
    assert calls[-1] == 'closed'


def test_enforces_body_limit_even_without_content_length(monkeypatch):
    from services import deep_research_academic as academic
    class Response:
        status = 200
        def getheader(self, name, default=None): return default
        def read(self, size): return b'x' * size
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(academic.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(AcademicAccessError, match='大小限制'):
        pinned_https_get('arxiv.org', '/pdf/2311.17245v6', 100, resolver=lambda _: ['8.8.8.8'])
