import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import requests


_VALID_RESPONSE = json.dumps({
    "web": {
        "results": [
            {
                "title": "  Attention Is All You Need  ",
                "url": "https://arxiv.org/abs/1706.03762",
                "description": "  The dominant sequence transduction models based on attention mechanisms.  ",
            },
        ],
    },
}).encode("utf-8")

_EMPTY_RESPONSE = json.dumps({
    "web": {"results": []},
}).encode("utf-8")

_MALFORMED = b"not-json-content"

_MISSING_WEB_KEY = json.dumps({"unexpected": "shape"}).encode("utf-8")

_WEB_RESULTS_NOT_LIST = json.dumps({"web": "not-a-list"}).encode("utf-8")

_BOUNDED_FIELDS = json.dumps({
    "web": {
        "results": [
            {
                "title": "t" * 2000,
                "url": "https://example.com/" + ("p" * 3000),
                "description": "d" * 12000,
            },
        ],
    },
}).encode("utf-8")

_MULTI_RESULTS = json.dumps({
    "web": {
        "results": [
            {
                "title": "First Result",
                "url": "https://example.com/1",
                "description": "First description.",
            },
            {
                "title": "Second Result",
                "url": "https://example.com/2",
                "description": "Second description.",
            },
            {
                "title": "Third Result",
                "url": "https://example.com/3",
                "description": "Third description.",
            },
        ],
    },
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


class BraveSearchProviderTests(unittest.TestCase):
    def _provider(self, response=None, error=None, clock=None, min_interval=0, api_key="test-api-key"):
        from services.providers.brave_search_provider import BraveSearchProvider

        session = _FakeSession(response=response, error=error)
        return BraveSearchProvider(
            session=session,
            clock=clock or (lambda: datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)),
            cache=_NullCache(),
            min_interval_seconds=min_interval,
            api_key=api_key,
        ), session

    @staticmethod
    def _success(body=None):
        return _FakeResponse(body=body if body is not None else _VALID_RESPONSE)

    # ── construction ────────────────────────────────────────────

    def test_api_key_is_required(self):
        from services.providers.brave_search_provider import BraveSearchProvider

        with self.assertRaises(ValueError):
            BraveSearchProvider(cache=_NullCache(), api_key=None)
        with self.assertRaises(ValueError):
            BraveSearchProvider(cache=_NullCache(), api_key="")
        with self.assertRaises(ValueError):
            BraveSearchProvider(cache=_NullCache(), api_key="   ")

    # ── happy path ──────────────────────────────────────────────

    def test_search_maps_brave_response_to_web_evidence(self):
        response = self._success()
        provider, session = self._provider(response=response)

        results = provider.search(" attention mechanisms ", limit=3)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["sourceType"], "web_search")
        self.assertEqual(item["provider"], "Brave Search")
        self.assertEqual(item["providerId"], "https://arxiv.org/abs/1706.03762")
        self.assertEqual(item["title"], "Attention Is All You Need")
        self.assertEqual(item["abstract"], "The dominant sequence transduction models based on attention mechanisms.")
        self.assertEqual(item["url"], "https://arxiv.org/abs/1706.03762")
        self.assertEqual(item["doi"], "")
        self.assertEqual(item["authors"], [])
        self.assertIsNone(item["year"])
        self.assertEqual(item["license"], "")
        self.assertEqual(item["retrievedAt"], "2026-07-12T12:00:00Z")
        self.assertEqual(item["query"], "attention mechanisms")
        self.assertEqual(len(session.calls), 1)
        url, options = session.calls[0]
        self.assertEqual(url, "https://api.search.brave.com/res/v1/web/search")
        self.assertEqual(options["params"]["q"], "attention mechanisms")
        self.assertEqual(options["params"]["count"], 3)
        self.assertIn("X-Subscription-Token", options["headers"])
        self.assertEqual(options["headers"]["X-Subscription-Token"], "test-api-key")
        self.assertEqual(options["headers"]["Accept"], "application/json")
        self.assertEqual(options["headers"]["Accept-Encoding"], "gzip")
        self.assertEqual(options["timeout"], (3.05, 10.0))
        self.assertFalse(options["allow_redirects"])
        self.assertTrue(options["stream"])
        self.assertTrue(response.closed)

    def test_status_is_local_no_network(self):
        provider, session = self._provider(response=self._success())

        self.assertEqual(provider.status(), {
            "enabled": True,
            "status": "ready",
            "provider": "brave",
        })
        self.assertEqual(session.calls, [])

    def test_capability_flags(self):
        provider, _session = self._provider(response=self._success())
        self.assertTrue(provider.supports_web_search)
        self.assertFalse(provider.supports_page_fetch)

    def test_search_rejects_invalid_query_and_limit_without_network(self):
        provider, session = self._provider(response=self._success())
        cases = [
            ("", 5), ("   ", 5), (None, 5),
            ("secret-query", 0), ("secret-query", 21), ("secret-query", True),
        ]
        for query, limit in cases:
            with self.subTest(query=query, limit=limit):
                with self.assertRaises(ValueError) as ctx:
                    provider.search(query, limit=limit)
                if query and str(query).strip():
                    self.assertNotIn(str(query), str(ctx.exception))
        self.assertEqual(session.calls, [])

    def test_empty_results(self):
        provider, _session = self._provider(response=_FakeResponse(body=_EMPTY_RESPONSE))
        results = provider.search("nothing matches", limit=5)
        self.assertEqual(results, [])

    def test_multiple_results(self):
        provider, _session = self._provider(response=_FakeResponse(body=_MULTI_RESULTS))
        results = provider.search("multi query")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["title"], "First Result")
        self.assertEqual(results[1]["title"], "Second Result")
        self.assertEqual(results[2]["title"], "Third Result")

    def test_search_bounds_untrusted_fields(self):
        provider, _session = self._provider(response=_FakeResponse(body=_BOUNDED_FIELDS))
        item = provider.search("q" * 2000, limit=1)[0]
        self.assertLessEqual(len(item["title"]), 1000)
        self.assertLessEqual(len(item["abstract"]), 10000)
        self.assertLessEqual(len(item["url"]), 2048)
        self.assertLessEqual(len(item["query"]), 1000)

    # ── error handling ──────────────────────────────────────────

    def test_malformed_json_is_rejected(self):
        from services.providers.brave_search_provider import BraveSearchProviderError
        provider, _session = self._provider(response=_FakeResponse(body=_MALFORMED))
        with self.assertRaises(BraveSearchProviderError) as ctx:
            provider.search("query")
        self.assertEqual(ctx.exception.code, "invalid_response")

    def test_invalid_response_shape_is_rejected(self):
        from services.providers.brave_search_provider import BraveSearchProviderError
        for body in (_MISSING_WEB_KEY, _WEB_RESULTS_NOT_LIST):
            with self.subTest(body=body[:30]):
                provider, _session = self._provider(response=_FakeResponse(body=body))
                with self.assertRaises(BraveSearchProviderError) as ctx:
                    provider.search("query")
                self.assertEqual(ctx.exception.code, "invalid_response")

    def test_http_errors_use_sanitized_codes(self):
        from services.providers.brave_search_provider import BraveSearchProvider, BraveSearchProviderError
        cases = [
            (_FakeSession(response=_FakeResponse(status_code=302, body=b"secret")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=429, body=b"secret")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=503, body=b"secret")), "http_error"),
            (_FakeSession(error=requests.Timeout("secret-timeout")), "timeout"),
            (_FakeSession(error=requests.RequestException("secret-network")), "network_error"),
        ]
        for session, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                provider = BraveSearchProvider(session=session, cache=_NullCache(), min_interval_seconds=0, api_key="k")
                with self.assertRaises(BraveSearchProviderError) as ctx:
                    provider.search("secret-query", limit=2)
                self.assertEqual(ctx.exception.code, expected_code)
                self.assertNotIn("secret", str(ctx.exception))

    def test_response_size_is_limited(self):
        from services.providers.brave_search_provider import BraveSearchProviderError
        response = _FakeResponse(headers={"Content-Length": str(1024 * 1024 + 1)})
        provider, _session = self._provider(response=response)
        with self.assertRaises(BraveSearchProviderError) as ctx:
            provider.search("query")
        self.assertEqual(ctx.exception.code, "response_too_large")

    def test_stream_timeout_is_sanitized(self):
        from services.providers.brave_search_provider import BraveSearchProviderError
        response = _FakeResponse(chunks=[requests.ReadTimeout("secret-stream-timeout")])
        provider, _session = self._provider(response=response)
        with self.assertRaises(BraveSearchProviderError) as ctx:
            provider.search("secret-query")
        self.assertEqual(ctx.exception.code, "timeout")

    # ── cache ───────────────────────────────────────────────────

    def test_cache_hit_skips_network(self):
        from services import trace_service
        from services.external_search_cache import ExternalSearchCache
        from services.providers.brave_search_provider import BraveSearchProvider

        trace_id = trace_service.start_trace("unit_brave_cache")
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalSearchCache(Path(temp_dir) / "cache.json")
            first = BraveSearchProvider(
                session=_SequenceSession([self._success()]),
                cache=cache,
                min_interval_seconds=0,
                api_key="k",
            )
            first.search("  Attention   Mechanisms  ", limit=5)
            second = BraveSearchProvider(
                session=_SequenceSession([]),
                cache=cache,
                min_interval_seconds=0,
                api_key="k",
            )
            results = second.search("attention mechanisms", limit=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["query"], "attention mechanisms")
        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snapshot["counters"]["externalSearchCacheHits"], 1)
        trace_service.clear_traces()

    # ── rate limiting ───────────────────────────────────────────

    def test_rate_limit_waits_between_requests(self):
        from services.providers.brave_search_provider import BraveSearchProvider
        fake_time = _FakeTime()
        session = _SequenceSession([self._success(), self._success()])
        provider = BraveSearchProvider(
            session=session, cache=_NullCache(),
            sleep_fn=fake_time.sleep, monotonic_clock=fake_time.monotonic,
            min_interval_seconds=1.0, api_key="k",
        )
        provider.search("first")
        provider.search("second")
        self.assertEqual(fake_time.sleeps, [1.0])
        self.assertEqual(len(session.calls), 2)

    # ── retry logic ─────────────────────────────────────────────

    def test_retryable_statuses_use_exponential_backoff(self):
        from services.providers.brave_search_provider import BraveSearchProvider
        fake_time = _FakeTime()
        session = _SequenceSession([
            _FakeResponse(status_code=500),
            _FakeResponse(status_code=503),
            self._success(),
        ])
        provider = BraveSearchProvider(
            session=session, cache=_NullCache(),
            sleep_fn=fake_time.sleep, monotonic_clock=fake_time.monotonic,
            min_interval_seconds=0, api_key="k",
        )
        results = provider.search("query")
        self.assertEqual(len(results), 1)
        self.assertEqual(fake_time.sleeps, [0.5, 1.0])
        self.assertEqual(len(session.calls), 3)

    def test_retry_after_over_thirty_seconds_stops(self):
        from services.providers.brave_search_provider import BraveSearchProvider, BraveSearchProviderError
        session = _SequenceSession([
            _FakeResponse(status_code=429, headers={"Retry-After": "31"}),
            self._success(),
        ])
        provider = BraveSearchProvider(session=session, cache=_NullCache(), min_interval_seconds=0, api_key="k")
        with self.assertRaises(BraveSearchProviderError) as ctx:
            provider.search("query")
        self.assertEqual(ctx.exception.code, "http_error")
        self.assertEqual(len(session.calls), 1)

    def test_non_retryable_status_one_attempt(self):
        from services.providers.brave_search_provider import BraveSearchProvider, BraveSearchProviderError
        for outcome in (_FakeResponse(status_code=302), _FakeResponse(status_code=400)):
            with self.subTest(status=outcome.status_code):
                session = _SequenceSession([outcome])
                provider = BraveSearchProvider(session=session, cache=_NullCache(), min_interval_seconds=0, api_key="k")
                with self.assertRaises(BraveSearchProviderError):
                    provider.search("query")
                self.assertEqual(len(session.calls), 1)

    # ── auth header ─────────────────────────────────────────────

    def test_x_subscription_token_header_sent(self):
        provider, session = self._provider(response=self._success(), api_key="brave-key-123")
        provider.search("test query")
        _url, options = session.calls[0]
        self.assertEqual(options["headers"]["X-Subscription-Token"], "brave-key-123")

    # ── builder ─────────────────────────────────────────────────

    def test_builder_extracts_api_key_from_config(self):
        from services.providers.brave_search_provider import build_brave_search_provider
        config = {"BRAVE_SEARCH_API_KEY": "builder-key"}
        provider = build_brave_search_provider(config)
        self.assertEqual(provider.name, "brave")
        self.assertTrue(provider.enabled)
        self.assertTrue(provider.supports_web_search)

    def test_builder_without_api_key_raises(self):
        from services.providers.brave_search_provider import build_brave_search_provider
        with self.assertRaises(ValueError):
            build_brave_search_provider({})


if __name__ == "__main__":
    unittest.main()
