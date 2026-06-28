import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, body=None, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        if body is None:
            body = json.dumps(payload if payload is not None else {}).encode("utf-8")
        self._body = body
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
        self.base = datetime(2026, 6, 22, tzinfo=timezone.utc)

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.seconds += seconds

    def wall_clock(self):
        return self.base + timedelta(seconds=self.seconds)


class CrossrefProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = Path(__file__).parent / "fixtures" / "external_search_adversarial.json"
        cls.adversarial_fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    def _provider(self, response=None, error=None):
        from services.providers.crossref import CrossrefProvider

        session = _FakeSession(response=response, error=error)
        provider = CrossrefProvider(
            session=session,
            clock=lambda: datetime(2026, 6, 22, 4, 5, 6, tzinfo=timezone.utc),
            cache=_NullCache(),
            min_interval_seconds=0,
        )
        return provider, session

    @staticmethod
    def _success(doi="10.1000/test", title="Paper"):
        return _FakeResponse(payload={
            "message": {"items": [{"DOI": doi, "title": [title]}]}
        })

    def test_search_uses_fixed_safe_request_and_maps_evidence(self):
        response = _FakeResponse(payload={
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/TEST",
                        "title": ["  Retrieval   Systems  "],
                        "author": [
                            {"given": "Ada", "family": "Lovelace"},
                            {"name": "Research Collective"},
                        ],
                        "published-print": {"date-parts": [[2024, 3, 1]]},
                        "published-online": {"date-parts": [[2025, 1, 1]]},
                        "abstract": "<jats:p>Evidence <jats:italic>summary</jats:italic>.</jats:p>",
                        "URL": "https://doi.org/10.1000/TEST",
                        "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
                    }
                ]
            }
        })
        provider, session = self._provider(response=response)

        results = provider.search(" retrieval evaluation ", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["sourceType"], "external_academic")
        self.assertEqual(results[0]["provider"], "Crossref")
        self.assertEqual(results[0]["providerId"], "10.1000/TEST")
        self.assertEqual(results[0]["title"], "Retrieval Systems")
        self.assertEqual(results[0]["authors"], ["Ada Lovelace", "Research Collective"])
        self.assertEqual(results[0]["year"], 2024)
        self.assertEqual(results[0]["abstract"], "Evidence summary .")
        self.assertEqual(results[0]["doi"], "10.1000/test")
        self.assertEqual(results[0]["retrievedAt"], "2026-06-22T04:05:06Z")
        self.assertEqual(results[0]["query"], "retrieval evaluation")
        self.assertEqual(
            results[0]["license"],
            "https://creativecommons.org/licenses/by/4.0/",
        )
        self.assertEqual(len(session.calls), 1)
        url, options = session.calls[0]
        self.assertEqual(url, "https://api.crossref.org/works")
        self.assertEqual(options["params"], {"query.bibliographic": "retrieval evaluation", "rows": 3})
        self.assertEqual(options["headers"], {
            "User-Agent": "PixiuExternalAcademicSearch/1.0",
            "Accept": "application/json",
        })
        self.assertEqual(options["timeout"], (3.05, 10.0))
        self.assertFalse(options["allow_redirects"])
        self.assertTrue(options["stream"])
        self.assertTrue(response.closed)

    def test_status_is_local_and_does_not_make_a_request(self):
        provider, session = self._provider(response=_FakeResponse())

        self.assertEqual(provider.status(), {
            "enabled": True,
            "status": "ready",
            "provider": "crossref",
        })
        self.assertEqual(session.calls, [])

    def test_search_rejects_invalid_query_and_result_limit_without_network(self):
        provider, session = self._provider(response=_FakeResponse())
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

    def test_search_honors_limit_and_skips_items_without_identity(self):
        response = _FakeResponse(payload={
            "message": {
                "items": [
                    {},
                    {"DOI": "10.1000/one", "title": ["One"]},
                    {"DOI": "10.1000/two", "title": ["Two"]},
                ]
            }
        })
        provider, _session = self._provider(response=response)

        results = provider.search("query", limit=1)

        self.assertEqual([item["doi"] for item in results], ["10.1000/one"])

    def test_search_bounds_untrusted_crossref_metadata(self):
        response = _FakeResponse(payload={
            "message": {
                "items": [{
                    "DOI": "d" * 3000,
                    "title": ["t" * 2000],
                    "author": [{"given": "a" * 300, "family": "b" * 300}] * 120,
                    "abstract": "<p>" + "x" * 12000 + "</p>",
                    "URL": "https://example.org/" + "u" * 3000,
                    "license": [{"URL": "l" * 3000}],
                }]
            }
        })
        provider, _session = self._provider(response=response)

        item = provider.search("q" * 2000, limit=1)[0]

        self.assertLessEqual(len(item["providerId"]), 2048)
        self.assertLessEqual(len(item["title"]), 1000)
        self.assertLessEqual(len(item["authors"]), 100)
        self.assertTrue(all(len(author) <= 200 for author in item["authors"]))
        self.assertLessEqual(len(item["abstract"]), 10000)
        self.assertLessEqual(len(item["doi"]), 2048)
        self.assertLessEqual(len(item["url"]), 2048)
        self.assertLessEqual(len(item["license"]), 2048)
        self.assertLessEqual(len(item["query"]), 1000)

    def test_search_sanitizes_prompt_injection_in_external_metadata(self):
        response = _FakeResponse(payload={
            "message": {"items": [self.adversarial_fixture["crossrefItem"]]}
        })
        provider, _session = self._provider(response=response)

        item = provider.search("retrieval security", limit=1)[0]
        serialized = json.dumps(item, ensure_ascii=False)

        self.assertIn("Secure Retrieval Study", item["title"])
        self.assertIn("Ada Lovelace", item["authors"][0])
        self.assertIn("Evaluation results remain academic evidence.", item["abstract"])
        self.assertIn("[SANITIZED INJECTION-LIKE CONTENT:", serialized)
        self.assertNotIn(self.adversarial_fixture["secretToken"], serialized)
        self.assertNotIn("Ignore previous instructions", serialized)

    def test_redirect_to_private_host_is_not_followed(self):
        response = _FakeResponse(
            status_code=302,
            headers={"Location": self.adversarial_fixture["redirectLocation"]},
            body=b"redirect body with sk-fixture-secret-12345",
        )
        provider, session = self._provider(response=response)

        with self.assertRaises(Exception) as context:
            provider.search("retrieval security", limit=1)

        self.assertEqual(getattr(context.exception, "code", ""), "http_error")
        self.assertEqual(len(session.calls), 1)
        requested_url, options = session.calls[0]
        self.assertEqual(requested_url, "https://api.crossref.org/works")
        self.assertFalse(options["allow_redirects"])
        self.assertNotIn(self.adversarial_fixture["secretToken"], str(context.exception))

    def test_http_and_transport_failures_use_stable_sanitized_codes(self):
        from services.providers.crossref import CrossrefProviderError

        cases = [
            (_FakeSession(response=_FakeResponse(status_code=302, body=b"secret-body")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=429, body=b"secret-body")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=503, body=b"secret-body")), "http_error"),
            (_FakeSession(error=requests.Timeout("secret-timeout")), "timeout"),
            (_FakeSession(error=requests.RequestException("secret-network")), "network_error"),
        ]

        for session, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                from services.providers.crossref import CrossrefProvider

                provider = CrossrefProvider(
                    session=session,
                    cache=_NullCache(),
                    sleep_fn=lambda _seconds: None,
                    min_interval_seconds=0,
                )
                with self.assertRaises(CrossrefProviderError) as context:
                    provider.search("secret-query", limit=2)
                error = context.exception
                self.assertEqual(error.code, expected_code)
                self.assertNotIn("secret", str(error))
                self.assertNotIn("api.crossref.org", str(error))
                self.assertNotIn("body", str(error))
                if session.response is not None:
                    self.assertTrue(session.response.closed)

    def test_response_size_is_limited_by_header_and_stream(self):
        from services.providers.crossref import CrossrefProviderError

        responses = [
            _FakeResponse(headers={"Content-Length": str(1024 * 1024 + 1)}),
            _FakeResponse(chunks=[b"a" * (1024 * 1024), b"b"]),
        ]
        for response in responses:
            with self.subTest(headers=response.headers):
                provider, _session = self._provider(response=response)
                with self.assertRaises(CrossrefProviderError) as context:
                    provider.search("query")
                self.assertEqual(context.exception.code, "response_too_large")
                self.assertTrue(response.closed)

    def test_invalid_json_and_shapes_are_rejected(self):
        from services.providers.crossref import CrossrefProviderError

        responses = [
            _FakeResponse(body=b"not-json"),
            _FakeResponse(payload=[]),
            _FakeResponse(payload={"message": []}),
            _FakeResponse(payload={"message": {"items": {}}}),
        ]
        for response in responses:
            provider, _session = self._provider(response=response)
            with self.assertRaises(CrossrefProviderError) as context:
                provider.search("query")
            self.assertEqual(context.exception.code, "invalid_response")
            self.assertTrue(response.closed)

    def test_stream_timeout_is_sanitized(self):
        from services.providers.crossref import CrossrefProviderError

        response = _FakeResponse(chunks=[requests.ReadTimeout("secret-stream-timeout")])
        provider, _session = self._provider(response=response)

        with self.assertRaises(CrossrefProviderError) as context:
            provider.search("secret-query")

        self.assertEqual(context.exception.code, "timeout")
        self.assertNotIn("secret", str(context.exception))
        self.assertTrue(response.closed)

    def test_cache_hit_skips_network_and_restores_normalized_query(self):
        from services import trace_service
        from services.external_search_cache import ExternalSearchCache
        from services.providers.crossref import CrossrefProvider

        trace_id = trace_service.start_trace("unit_crossref_cache")
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalSearchCache(Path(temp_dir) / "cache.json")
            first_session = _SequenceSession([self._success()])
            first = CrossrefProvider(session=first_session, cache=cache, min_interval_seconds=0)
            first.search("  Retrieval   SYSTEMS  ", limit=5)
            second_session = _SequenceSession([])
            second = CrossrefProvider(session=second_session, cache=cache, min_interval_seconds=0)

            results = second.search("retrieval systems", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["query"], "retrieval systems")
        self.assertEqual(second_session.calls, [])
        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["externalSearchCacheHits"], 1)
        trace_service.clear_traces()

    def test_instance_rate_limit_waits_between_uncached_requests(self):
        from services.providers.crossref import CrossrefProvider

        fake_time = _FakeTime()
        session = _SequenceSession([self._success("10.1/one"), self._success("10.1/two")])
        provider = CrossrefProvider(
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
        from services.providers.crossref import CrossrefProvider

        fake_time = _FakeTime()
        first = _FakeResponse(status_code=500)
        second = _FakeResponse(status_code=503)
        success = self._success()
        session = _SequenceSession([first, second, success])
        provider = CrossrefProvider(
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
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertTrue(success.closed)

    def test_retry_after_seconds_and_http_date_take_precedence(self):
        from services.providers.crossref import CrossrefProvider

        cases = [
            ("3", 3.0),
            ("Mon, 22 Jun 2026 00:00:05 GMT", 5.0),
        ]
        for retry_after, expected_sleep in cases:
            with self.subTest(retry_after=retry_after):
                fake_time = _FakeTime()
                limited = _FakeResponse(status_code=429, headers={"Retry-After": retry_after})
                session = _SequenceSession([limited, self._success()])
                provider = CrossrefProvider(
                    session=session,
                    cache=_NullCache(),
                    clock=fake_time.wall_clock,
                    sleep_fn=fake_time.sleep,
                    monotonic_clock=fake_time.monotonic,
                    min_interval_seconds=0,
                )

                provider.search("query")

                self.assertEqual(fake_time.sleeps, [expected_sleep])
                self.assertEqual(len(session.calls), 2)

    def test_retry_after_over_thirty_seconds_stops_without_retrying(self):
        from services.providers.crossref import CrossrefProvider, CrossrefProviderError

        session = _SequenceSession([
            _FakeResponse(status_code=429, headers={"Retry-After": "31"}),
            self._success(),
        ])
        provider = CrossrefProvider(session=session, cache=_NullCache(), min_interval_seconds=0)

        with self.assertRaises(CrossrefProviderError) as context:
            provider.search("query")

        self.assertEqual(context.exception.code, "http_error")
        self.assertEqual(len(session.calls), 1)

    def test_non_retryable_status_and_network_errors_make_one_attempt(self):
        from services.providers.crossref import CrossrefProvider, CrossrefProviderError

        outcomes = [
            _FakeResponse(status_code=302),
            _FakeResponse(status_code=400),
            requests.Timeout("secret"),
            requests.RequestException("secret"),
        ]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                session = _SequenceSession([outcome])
                provider = CrossrefProvider(
                    session=session,
                    cache=_NullCache(),
                    min_interval_seconds=0,
                )
                with self.assertRaises(CrossrefProviderError):
                    provider.search("query")
                self.assertEqual(len(session.calls), 1)

    def test_provider_deduplicates_results_before_caching(self):
        from services.providers.crossref import CrossrefProvider

        response = _FakeResponse(payload={"message": {"items": [
            {"DOI": "10.1000/one", "title": ["Paper One"]},
            {"DOI": "10.1000/ONE", "title": ["Duplicate DOI"]},
            {"DOI": "10.1000/two", "title": [" paper   one "]},
            {"DOI": "10.1000/three", "title": ["Unique"]},
        ]}})
        provider = CrossrefProvider(
            session=_SequenceSession([response]),
            cache=_NullCache(),
            min_interval_seconds=0,
        )

        results = provider.search("query", limit=5)

        self.assertEqual([item["doi"] for item in results], ["10.1000/one", "10.1000/three"])


if __name__ == "__main__":
    unittest.main()
