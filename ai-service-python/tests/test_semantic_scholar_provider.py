import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import requests


_VALID_RESPONSE = json.dumps({
    "total": 1,
    "offset": 0,
    "data": [
        {
            "paperId": "649def34f8be52c8b66281af98ae884c09aef38b",
            "title": "  Retrieval   Systems  ",
            "authors": [
                {"authorId": "111", "name": "Ada Lovelace"},
                {"authorId": "222", "name": "Charles Babbage"},
            ],
            "year": 2024,
            "abstract": "  A study of retrieval methods.  ",
            "externalIds": {
                "DOI": "10.1000/TEST",
                "CorpusId": 27771234,
            },
            "url": "https://www.semanticscholar.org/paper/649def34f8be52c8b66281af98ae884c09aef38b",
            "publicationVenue": "Journal of Testing",
        },
    ],
}).encode("utf-8")

_EMPTY_RESPONSE = json.dumps({
    "total": 0,
    "offset": 0,
    "data": [],
}).encode("utf-8")

_MALFORMED = b"not-json-content"

_INVALID_SHAPE = json.dumps({"unexpected": "structure"}).encode("utf-8")

_DATA_NOT_LIST = json.dumps({"total": 0, "offset": 0, "data": "not-a-list"}).encode("utf-8")

_RESPONSE_WITHOUT_IDENTITY = json.dumps({
    "total": 2,
    "offset": 0,
    "data": [
        {
            "paperId": None,
            "title": None,
            "year": None,
            "abstract": "No identity paper.",
        },
        {
            "paperId": "2401.00002",
            "title": "Has Identity",
            "authors": [{"authorId": "333", "name": "Someone"}],
            "year": 2025,
            "abstract": "Has an identity.",
        },
    ],
}).encode("utf-8")

_RESPONSE_MULTI_AUTHORS = json.dumps({
    "total": 1,
    "offset": 0,
    "data": [
        {
            "paperId": "2401.00003",
            "title": "Collaborative Paper",
            "authors": [
                {"authorId": "1", "name": "Alice"},
                {"authorId": "2", "name": "Bob"},
                {"authorId": "3", "name": "Carol"},
                {"authorId": "4", "name": "Dave"},
            ],
            "year": 2023,
            "abstract": "Multi-author research.",
        },
    ],
}).encode("utf-8")

_BOUNDED_FIELDS = json.dumps({
    "total": 1,
    "offset": 0,
    "data": [
        {
            "paperId": "{}aaaa".format("x" * 300),
            "title": "t" * 2000,
            "authors": [{"authorId": "x", "name": "a" * 300}],
            "year": 2025,
            "abstract": "x" * 12000,
            "externalIds": {"DOI": "{}.long".format("d" * 300)},
            "url": "https://semanticscholar.org/paper/{}zzzz".format("u" * 500),
        },
    ],
}).encode("utf-8")

_RESPONSE_NULL_ABSTRACT = json.dumps({
    "total": 1,
    "offset": 0,
    "data": [
        {
            "paperId": "abc123",
            "title": "No Abstract Paper",
            "authors": [],
            "year": None,
            "abstract": None,
        },
    ],
}).encode("utf-8")

_RESPONSE_WITH_VENUE = json.dumps({
    "total": 1,
    "offset": 0,
    "data": [
        {
            "paperId": "venue123",
            "title": "Published Paper",
            "authors": [{"authorId": "a1", "name": "First Author"}],
            "year": 2022,
            "abstract": "Some abstract.",
            "publicationVenue": {
                "name": "Nature",
                "type": "journal",
            },
        },
    ],
}).encode("utf-8")

_RESPONSE_NO_DOI = json.dumps({
    "total": 1,
    "offset": 0,
    "data": [
        {
            "paperId": "nodoipaper",
            "title": "Paper Without DOI",
            "authors": [{"authorId": "a2", "name": "Author Two"}],
            "year": 2021,
            "abstract": "Abstract without DOI.",
            "externalIds": {"CorpusId": 99999},
            "url": "https://semanticscholar.org/paper/nodoipaper",
        },
    ],
}).encode("utf-8")


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


class SemanticScholarProviderTests(unittest.TestCase):
    def _provider(self, response=None, error=None, clock=None, min_interval=0, api_key=None):
        from services.providers.semantic_scholar_provider import SemanticScholarProvider

        session = _FakeSession(response=response, error=error)
        return SemanticScholarProvider(
            session=session,
            clock=clock or (lambda: datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)),
            cache=_NullCache(),
            min_interval_seconds=min_interval,
            api_key=api_key,
        ), session

    @staticmethod
    def _success(body=None):
        return _FakeResponse(body=body if body is not None else _VALID_RESPONSE)

    # ── happy path ──────────────────────────────────────────────

    def test_search_maps_semantic_scholar_response_to_evidence(self):
        response = self._success()
        provider, session = self._provider(response=response)

        results = provider.search(" retrieval evaluation ", limit=3)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["sourceType"], "external_academic")
        self.assertEqual(item["provider"], "Semantic Scholar")
        self.assertEqual(item["providerId"], "649def34f8be52c8b66281af98ae884c09aef38b")
        self.assertEqual(item["title"], "Retrieval Systems")
        self.assertEqual(item["authors"], ["Ada Lovelace", "Charles Babbage"])
        self.assertEqual(item["year"], 2024)
        self.assertEqual(item["abstract"], "A study of retrieval methods.")
        self.assertEqual(item["doi"], "10.1000/test")
        self.assertEqual(
            item["url"],
            "https://www.semanticscholar.org/paper/649def34f8be52c8b66281af98ae884c09aef38b",
        )
        self.assertEqual(item["retrievedAt"], "2026-07-01T12:00:00Z")
        self.assertEqual(item["query"], "retrieval evaluation")
        self.assertEqual(item["license"], "Journal of Testing")
        self.assertEqual(len(session.calls), 1)
        url, options = session.calls[0]
        self.assertEqual(url, "https://api.semanticscholar.org/graph/v1/paper/search")
        self.assertEqual(options["params"]["query"], "retrieval evaluation")
        self.assertEqual(options["params"]["limit"], 3)
        self.assertEqual(
            options["params"]["fields"],
            "title,authors,year,abstract,externalIds,url,publicationVenue",
        )
        self.assertEqual(options["headers"]["Accept"], "application/json")
        self.assertEqual(options["timeout"], (3.05, 10.0))
        self.assertFalse(options["allow_redirects"])
        self.assertTrue(options["stream"])
        self.assertTrue(response.closed)

    def test_status_is_local_and_does_not_make_a_request(self):
        provider, session = self._provider(response=self._success())

        self.assertEqual(provider.status(), {
            "enabled": True,
            "status": "ready",
            "provider": "semantic_scholar",
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

    def test_search_skips_entries_without_identity(self):
        provider, _session = self._provider(response=_FakeResponse(body=_RESPONSE_WITHOUT_IDENTITY))

        results = provider.search("query", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["providerId"], "2401.00002")

    def test_search_parses_multiple_authors(self):
        provider, _session = self._provider(response=_FakeResponse(body=_RESPONSE_MULTI_AUTHORS))

        results = provider.search("query")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["authors"], ["Alice", "Bob", "Carol", "Dave"])

    def test_empty_results(self):
        provider, _session = self._provider(response=_FakeResponse(body=_EMPTY_RESPONSE))

        results = provider.search("nothing matches", limit=5)

        self.assertEqual(results, [])

    def test_search_bounds_untrusted_fields(self):
        provider, _session = self._provider(response=_FakeResponse(body=_BOUNDED_FIELDS))

        item = provider.search("q" * 2000, limit=1)[0]

        self.assertLessEqual(len(item["providerId"]), 200)
        self.assertLessEqual(len(item["title"]), 1000)
        self.assertLessEqual(len(item["authors"]), 100)
        self.assertLessEqual(len(item["abstract"]), 10000)
        self.assertLessEqual(len(item["doi"]), 200)
        self.assertLessEqual(len(item["query"]), 1000)

    def test_null_abstract_and_year(self):
        provider, _session = self._provider(response=_FakeResponse(body=_RESPONSE_NULL_ABSTRACT))

        results = provider.search("no abstract query")

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["title"], "No Abstract Paper")
        self.assertEqual(item["abstract"], "")
        self.assertIsNone(item["year"])
        self.assertEqual(item["authors"], [])

    def test_publication_venue_in_license(self):
        provider, _session = self._provider(response=_FakeResponse(body=_RESPONSE_WITH_VENUE))

        results = provider.search("venue query")

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["title"], "Published Paper")
        self.assertEqual(item["license"], "Nature")  # publicationVenue name goes to license

    def test_no_doi_produces_fallback_identity(self):
        provider, _session = self._provider(response=_FakeResponse(body=_RESPONSE_NO_DOI))

        results = provider.search("no doi")

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["providerId"], "nodoipaper")
        self.assertEqual(item["doi"], "")
        self.assertNotEqual(item["sourceId"], "")

    # ── error handling ──────────────────────────────────────────

    def test_malformed_json_is_rejected(self):
        from services.providers.semantic_scholar_provider import SemanticScholarProviderError

        provider, _session = self._provider(response=_FakeResponse(body=_MALFORMED))

        with self.assertRaises(SemanticScholarProviderError) as context:
            provider.search("query")
        self.assertEqual(context.exception.code, "invalid_response")

    def test_invalid_json_shape_is_rejected(self):
        from services.providers.semantic_scholar_provider import SemanticScholarProviderError

        for body in (_INVALID_SHAPE, _DATA_NOT_LIST):
            with self.subTest(body=body[:30]):
                provider, _session = self._provider(response=_FakeResponse(body=body))
                with self.assertRaises(SemanticScholarProviderError) as context:
                    provider.search("query")
                self.assertEqual(context.exception.code, "invalid_response")

    def test_http_and_transport_failures_use_stable_sanitized_codes(self):
        from services.providers.semantic_scholar_provider import (
            SemanticScholarProvider,
            SemanticScholarProviderError,
        )

        cases = [
            (_FakeSession(response=_FakeResponse(status_code=302, body=b"secret-body")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=429, body=b"secret-body")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=503, body=b"secret-body")), "http_error"),
            (_FakeSession(error=requests.Timeout("secret-timeout")), "timeout"),
            (_FakeSession(error=requests.RequestException("secret-network")), "network_error"),
        ]
        for session, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                provider = SemanticScholarProvider(session=session, cache=_NullCache(), min_interval_seconds=0)
                with self.assertRaises(SemanticScholarProviderError) as context:
                    provider.search("secret-query", limit=2)
                error = context.exception
                self.assertEqual(error.code, expected_code)
                self.assertNotIn("secret", str(error))
                self.assertNotIn("semanticscholar.org", str(error))

    def test_response_size_is_limited(self):
        from services.providers.semantic_scholar_provider import SemanticScholarProviderError

        response = _FakeResponse(headers={"Content-Length": str(1024 * 1024 + 1)})
        provider, _session = self._provider(response=response)
        with self.assertRaises(SemanticScholarProviderError) as context:
            provider.search("query")
        self.assertEqual(context.exception.code, "response_too_large")

    def test_stream_timeout_is_sanitized(self):
        from services.providers.semantic_scholar_provider import SemanticScholarProviderError

        response = _FakeResponse(chunks=[requests.ReadTimeout("secret-stream-timeout")])
        provider, _session = self._provider(response=response)
        with self.assertRaises(SemanticScholarProviderError) as context:
            provider.search("secret-query")
        self.assertEqual(context.exception.code, "timeout")

    # ── cache ───────────────────────────────────────────────────

    def test_cache_hit_skips_network_and_restores_normalized_query(self):
        from services import trace_service
        from services.external_search_cache import ExternalSearchCache
        from services.providers.semantic_scholar_provider import SemanticScholarProvider

        trace_id = trace_service.start_trace("unit_s2_cache")
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalSearchCache(Path(temp_dir) / "cache.json")
            first = SemanticScholarProvider(
                session=_SequenceSession([self._success()]),
                cache=cache,
                min_interval_seconds=0,
            )
            first.search("  Retrieval   SYSTEMS  ", limit=5)
            second = SemanticScholarProvider(
                session=_SequenceSession([]),
                cache=cache,
                min_interval_seconds=0,
            )

            results = second.search("retrieval systems", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["query"], "retrieval systems")
        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["externalSearchCacheHits"], 1)
        trace_service.clear_traces()

    # ── rate limiting ───────────────────────────────────────────

    def test_instance_rate_limit_waits_between_uncached_requests(self):
        from services.providers.semantic_scholar_provider import SemanticScholarProvider

        fake_time = _FakeTime()
        session = _SequenceSession([self._success(), self._success()])
        provider = SemanticScholarProvider(
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

    # ── retry logic ─────────────────────────────────────────────

    def test_retryable_statuses_use_two_bounded_exponential_retries(self):
        from services.providers.semantic_scholar_provider import SemanticScholarProvider

        fake_time = _FakeTime()
        session = _SequenceSession([
            _FakeResponse(status_code=500),
            _FakeResponse(status_code=503),
            self._success(),
        ])
        provider = SemanticScholarProvider(
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
        from services.providers.semantic_scholar_provider import (
            SemanticScholarProvider,
            SemanticScholarProviderError,
        )

        session = _SequenceSession([
            _FakeResponse(status_code=429, headers={"Retry-After": "31"}),
            self._success(),
        ])
        provider = SemanticScholarProvider(session=session, cache=_NullCache(), min_interval_seconds=0)
        with self.assertRaises(SemanticScholarProviderError) as context:
            provider.search("query")
        self.assertEqual(context.exception.code, "http_error")
        self.assertEqual(len(session.calls), 1)

    def test_non_retryable_status_makes_one_attempt(self):
        from services.providers.semantic_scholar_provider import (
            SemanticScholarProvider,
            SemanticScholarProviderError,
        )

        outcomes = [
            _FakeResponse(status_code=302),
            _FakeResponse(status_code=400),
        ]
        for outcome in outcomes:
            with self.subTest(status=outcome.status_code):
                session = _SequenceSession([outcome])
                provider = SemanticScholarProvider(session=session, cache=_NullCache(), min_interval_seconds=0)
                with self.assertRaises(SemanticScholarProviderError):
                    provider.search("query")
                self.assertEqual(len(session.calls), 1)

    # ── API key ─────────────────────────────────────────────────

    def test_with_api_key_sends_x_api_key_header(self):
        provider, session = self._provider(
            response=self._success(),
            api_key="s2-test-key-12345",
        )

        provider.search("test query")

        self.assertEqual(len(session.calls), 1)
        _url, options = session.calls[0]
        self.assertIn("x-api-key", options["headers"])
        self.assertEqual(options["headers"]["x-api-key"], "s2-test-key-12345")

    def test_without_api_key_sends_no_auth_header(self):
        provider, session = self._provider(response=self._success(), api_key=None)

        provider.search("test query")

        self.assertEqual(len(session.calls), 1)
        _url, options = session.calls[0]
        self.assertNotIn("x-api-key", options["headers"])

    def test_empty_api_key_sends_no_auth_header(self):
        provider, session = self._provider(response=self._success(), api_key="")

        provider.search("test query")

        self.assertEqual(len(session.calls), 1)
        _url, options = session.calls[0]
        self.assertNotIn("x-api-key", options["headers"])

    def test_429_with_retry_works_identically_with_or_without_key(self):
        from services.providers.semantic_scholar_provider import SemanticScholarProvider

        fake_time = _FakeTime()
        session = _SequenceSession([
            _FakeResponse(status_code=429),
            self._success(),
        ])
        provider = SemanticScholarProvider(
            session=session,
            cache=_NullCache(),
            sleep_fn=fake_time.sleep,
            monotonic_clock=fake_time.monotonic,
            min_interval_seconds=0,
            api_key=None,
        )
        results = provider.search("query")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(session.calls), 2)

    # ── builder ─────────────────────────────────────────────────

    def test_builder_extracts_api_key_from_config(self):
        from services.providers.semantic_scholar_provider import build_semantic_scholar_provider

        config = {"SEMANTIC_SCHOLAR_API_KEY": "builder-test-key"}
        provider = build_semantic_scholar_provider(config)

        self.assertEqual(provider.name, "semantic_scholar")
        self.assertTrue(provider.enabled)
        self.assertFalse(provider.supports_web_search)
        self.assertFalse(provider.supports_page_fetch)

    def test_builder_without_api_key_creates_provider(self):
        from services.providers.semantic_scholar_provider import build_semantic_scholar_provider

        config = {}
        provider = build_semantic_scholar_provider(config)

        self.assertEqual(provider.name, "semantic_scholar")
        self.assertTrue(provider.enabled)


if __name__ == "__main__":
    unittest.main()
