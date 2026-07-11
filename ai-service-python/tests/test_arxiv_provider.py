import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import requests


_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2401.00001</id>
    <title>  Retrieval   Systems  </title>
    <published>2024-01-15T10:00:00Z</published>
    <author><name>Ada Lovelace</name></author>
    <author><name>Charles Babbage</name></author>
    <summary>  A study of <em>retrieval</em> methods.  </summary>
    <link rel="related" title="doi" href="https://doi.org/10.1000/TEST"/>
    <arxiv:license href="https://creativecommons.org/licenses/by/4.0/"/>
  </entry>
</feed>
"""

_ATOM_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>0</opensearch:totalResults>
</feed>
"""

_ATOM_MALFORMED = b"not-xml-content"

_ATOM_WITHOUT_IDENTITY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Untitled</title>
    <summary>No identity.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002</id>
    <title>Has Identity</title>
    <author><name>Someone</name></author>
    <published>2024</published>
    <summary>Has an arxiv id.</summary>
  </entry>
</feed>
"""

_ATOM_MULTI_AUTHORS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00003</id>
    <title>Collaborative Paper</title>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <author><name>Carol</name></author>
    <author><name>Dave</name></author>
    <published>2023-06-01T00:00:00Z</published>
    <summary>Multi-author research.</summary>
  </entry>
</feed>
"""

_ATOM_BOUNDED_FIELDS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{}aaaa</id>
    <title>{}</title>
    <author><name>{}</name></author>
    <published>2025</published>
    <summary>{}</summary>
    <link rel="related" title="doi" href="https://doi.org/{}.long"/>
  </entry>
</feed>
""".format("x" * 300, "t" * 2000, "a" * 300, "x" * 12000, "d" * 300)


class _FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body if body is not None else b""
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size=65536):
        del chunk_size
        if self._chunks is not None:
            for chunk in self._chunks:
                if isinstance(chunk, Exception):
                    raise chunk
                yield chunk
            return
        if isinstance(self._body, str):
            yield self._body.encode("utf-8")
        else:
            yield self._body

    def close(self):
        self.closed = True


class _FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


class _SequenceSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _NullCache:
    def get(self, _provider, _query, _limit):
        return None

    def put(self, _provider, _query, _fetched_limit, _results):
        return None


class _FakeTime:
    def __init__(self):
        self.seconds = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.seconds += seconds


class ArxivProviderTests(unittest.TestCase):
    def _provider(self, response=None, error=None, clock=None, min_interval=0):
        from services.providers.arxiv_provider import ArxivProvider

        session = _FakeSession(response=response, error=error)
        return ArxivProvider(
            session=session,
            clock=clock or (lambda: datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)),
            cache=_NullCache(),
            min_interval_seconds=min_interval,
        ), session

    @staticmethod
    def _success(body=None):
        return _FakeResponse(body=body if body is not None else _ATOM)

    def test_search_uses_fixed_safe_request_and_maps_evidence(self):
        response = self._success()
        provider, session = self._provider(response=response)

        results = provider.search(" retrieval evaluation ", limit=3)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["sourceType"], "external_academic")
        self.assertEqual(item["provider"], "ArXiv")
        self.assertEqual(item["providerId"], "2401.00001")
        self.assertEqual(item["title"], "Retrieval Systems")
        self.assertEqual(item["authors"], ["Ada Lovelace", "Charles Babbage"])
        self.assertEqual(item["year"], 2024)
        self.assertEqual(item["abstract"], "A study of retrieval methods.")
        self.assertEqual(item["doi"], "10.1000/test")
        self.assertEqual(item["url"], "https://arxiv.org/abs/2401.00001")
        self.assertEqual(item["retrievedAt"], "2026-07-01T12:00:00Z")
        self.assertEqual(item["query"], "retrieval evaluation")
        self.assertEqual(item["license"], "https://creativecommons.org/licenses/by/4.0/")
        self.assertEqual(len(session.calls), 1)
        url, options = session.calls[0]
        self.assertEqual(url, "https://export.arxiv.org/api/query")
        self.assertEqual(options["params"], {
            "search_query": "retrieval evaluation",
            "start": 0,
            "max_results": 3,
        })
        self.assertEqual(options["headers"], {
            "User-Agent": "PixiuExternalAcademicSearch/1.0",
            "Accept": "application/atom+xml",
        })
        self.assertEqual(options["timeout"], (3.05, 10.0))
        self.assertFalse(options["allow_redirects"])
        self.assertTrue(options["stream"])
        self.assertTrue(response.closed)

    def test_status_is_local_and_does_not_make_a_request(self):
        provider, session = self._provider(response=self._success())

        self.assertEqual(provider.status(), {
            "enabled": True,
            "status": "ready",
            "provider": "arxiv",
        })
        self.assertEqual(session.calls, [])

    def test_capability_flags(self):
        provider, _session = self._provider(response=self._success())
        self.assertFalse(provider.supports_web_search)
        self.assertFalse(provider.supports_page_fetch)

    def test_search_rejects_invalid_query_and_result_limit_without_network(self):
        provider, session = self._provider(response=self._success())
        cases = [
            ("", 5),
            ("   ", 5),
            (None, 5),
            ("secret-query", 0),
            ("secret-query", 21),
            ("secret-query", True),
        ]
        for query, limit in cases:
            with self.subTest(query=query, limit=limit):
                with self.assertRaises(ValueError) as context:
                    provider.search(query, limit=limit)
                if query and str(query).strip():
                    self.assertNotIn(str(query), str(context.exception))
        self.assertEqual(session.calls, [])

    def test_search_honors_limit_and_skips_entries_without_identity(self):
        provider, _session = self._provider(response=_FakeResponse(body=_ATOM_WITHOUT_IDENTITY))

        results = provider.search("query", limit=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["providerId"], "2401.00002")

    def test_search_parses_multiple_authors(self):
        provider, _session = self._provider(response=_FakeResponse(body=_ATOM_MULTI_AUTHORS))

        results = provider.search("query")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["authors"], ["Alice", "Bob", "Carol", "Dave"])

    def test_empty_results(self):
        provider, _session = self._provider(response=_FakeResponse(body=_ATOM_EMPTY))

        results = provider.search("nothing matches", limit=5)

        self.assertEqual(results, [])

    def test_search_bounds_untrusted_fields(self):
        provider, _session = self._provider(response=_FakeResponse(body=_ATOM_BOUNDED_FIELDS))

        item = provider.search("q" * 2000, limit=1)[0]

        self.assertLessEqual(len(item["providerId"]), 200)
        self.assertLessEqual(len(item["title"]), 1000)
        self.assertLessEqual(len(item["authors"]), 100)
        self.assertLessEqual(len(item["abstract"]), 10000)
        self.assertLessEqual(len(item["doi"]), 200)
        self.assertLessEqual(len(item["query"]), 1000)

    def test_malformed_xml_is_rejected(self):
        from services.providers.arxiv_provider import ArxivProviderError

        provider, _session = self._provider(response=_FakeResponse(body=_ATOM_MALFORMED))

        with self.assertRaises(ArxivProviderError) as context:
            provider.search("query")
        self.assertEqual(context.exception.code, "invalid_response")

    def test_http_and_transport_failures_use_stable_sanitized_codes(self):
        from services.providers.arxiv_provider import ArxivProvider, ArxivProviderError

        cases = [
            (_FakeSession(response=_FakeResponse(status_code=302, body=b"secret-body")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=429, body=b"secret-body")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=503, body=b"secret-body")), "http_error"),
            (_FakeSession(error=requests.Timeout("secret-timeout")), "timeout"),
            (_FakeSession(error=requests.RequestException("secret-network")), "network_error"),
        ]
        for session, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                provider = ArxivProvider(session=session, cache=_NullCache(), min_interval_seconds=0)
                with self.assertRaises(ArxivProviderError) as context:
                    provider.search("secret-query", limit=2)
                error = context.exception
                self.assertEqual(error.code, expected_code)
                self.assertNotIn("secret", str(error))
                self.assertNotIn("arxiv.org", str(error))

    def test_response_size_is_limited(self):
        from services.providers.arxiv_provider import ArxivProviderError

        response = _FakeResponse(headers={"Content-Length": str(1024 * 1024 + 1)})
        provider, _session = self._provider(response=response)
        with self.assertRaises(ArxivProviderError) as context:
            provider.search("query")
        self.assertEqual(context.exception.code, "response_too_large")

    def test_stream_timeout_is_sanitized(self):
        from services.providers.arxiv_provider import ArxivProviderError

        response = _FakeResponse(chunks=[requests.ReadTimeout("secret-stream-timeout")])
        provider, _session = self._provider(response=response)
        with self.assertRaises(ArxivProviderError) as context:
            provider.search("secret-query")
        self.assertEqual(context.exception.code, "timeout")

    def test_cache_hit_skips_network_and_restores_normalized_query(self):
        from services import trace_service
        from services.external_search_cache import ExternalSearchCache
        from services.providers.arxiv_provider import ArxivProvider

        trace_id = trace_service.start_trace("unit_arxiv_cache")
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalSearchCache(Path(temp_dir) / "cache.json")
            first = ArxivProvider(session=_SequenceSession([self._success()]), cache=cache, min_interval_seconds=0)
            first.search("  Retrieval   SYSTEMS  ", limit=5)
            second = ArxivProvider(session=_SequenceSession([]), cache=cache, min_interval_seconds=0)

            results = second.search("retrieval systems", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["query"], "retrieval systems")
        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["externalSearchCacheHits"], 1)
        trace_service.clear_traces()

    def test_instance_rate_limit_waits_between_uncached_requests(self):
        from services.providers.arxiv_provider import ArxivProvider

        fake_time = _FakeTime()
        session = _SequenceSession([self._success(), self._success()])
        provider = ArxivProvider(
            session=session,
            cache=_NullCache(),
            sleep_fn=fake_time.sleep,
            monotonic_clock=fake_time.monotonic,
            min_interval_seconds=1.0,
        )
        provider.search("first")
        provider.search("second")
        self.assertEqual(fake_time.sleeps, [1.0])
        self.assertEqual(len(session.calls), 2)

    def test_retryable_statuses_use_two_bounded_exponential_retries(self):
        from services.providers.arxiv_provider import ArxivProvider

        fake_time = _FakeTime()
        session = _SequenceSession([
            _FakeResponse(status_code=500),
            _FakeResponse(status_code=503),
            self._success(),
        ])
        provider = ArxivProvider(
            session=session,
            cache=_NullCache(),
            sleep_fn=fake_time.sleep,
            monotonic_clock=fake_time.monotonic,
            min_interval_seconds=0,
        )
        results = provider.search("query")
        self.assertEqual(len(results), 1)
        self.assertEqual(fake_time.sleeps, [0.5, 1.0])
        self.assertEqual(len(session.calls), 3)

    def test_retry_after_over_thirty_seconds_stops(self):
        from services.providers.arxiv_provider import ArxivProvider, ArxivProviderError

        session = _SequenceSession([
            _FakeResponse(status_code=429, headers={"Retry-After": "31"}),
            self._success(),
        ])
        provider = ArxivProvider(session=session, cache=_NullCache(), min_interval_seconds=0)
        with self.assertRaises(ArxivProviderError) as context:
            provider.search("query")
        self.assertEqual(context.exception.code, "http_error")
        self.assertEqual(len(session.calls), 1)

    def test_non_retryable_status_makes_one_attempt(self):
        from services.providers.arxiv_provider import ArxivProvider, ArxivProviderError

        outcomes = [
            _FakeResponse(status_code=302),
            _FakeResponse(status_code=400),
        ]
        for outcome in outcomes:
            with self.subTest(status=outcome.status_code):
                session = _SequenceSession([outcome])
                provider = ArxivProvider(session=session, cache=_NullCache(), min_interval_seconds=0)
                with self.assertRaises(ArxivProviderError):
                    provider.search("query")
                self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
