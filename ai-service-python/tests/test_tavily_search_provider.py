import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import requests


_VALID_RESPONSE = json.dumps({
    "results": [
        {
            "title": "  Attention Is All You Need  ",
            "url": "https://arxiv.org/abs/1706.03762",
            "content": "  The dominant sequence transduction models based on attention.  ",
        },
    ],
    "answer": "This paper introduced the Transformer architecture.",
}).encode("utf-8")

_NO_ANSWER_RESPONSE = json.dumps({
    "results": [
        {
            "title": "Attention Mechanisms",
            "url": "https://example.com/attention",
            "content": "A survey of attention mechanisms in deep learning.",
        },
    ],
}).encode("utf-8")

_EMPTY_RESPONSE = json.dumps({
    "results": [],
    "answer": None,
}).encode("utf-8")

_MALFORMED = b"not-json-content"

_MISSING_RESULTS = json.dumps({"answer": "no results key"}).encode("utf-8")

_RESULTS_NOT_LIST = json.dumps({"results": "not-a-list"}).encode("utf-8")

_BOUNDED_FIELDS = json.dumps({
    "results": [
        {
            "title": "t" * 2000,
            "url": "https://example.com/" + ("p" * 3000),
            "content": "c" * 12000,
        },
    ],
    "answer": "a" * 5000,
}).encode("utf-8")


class _FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, chunks=None, check_post_body=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body if body is not None else b""
        self._chunks = chunks
        self.closed = False
        self._check_post_body = check_post_body

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

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


class _SequenceSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, url, **kwargs):
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


class TavilySearchProviderTests(unittest.TestCase):
    def _provider(self, response=None, error=None, clock=None, min_interval=0, api_key="test-tavily-key"):
        from services.providers.tavily_provider import TavilyProvider

        session = _FakeSession(response=response, error=error)
        return TavilyProvider(
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
        from services.providers.tavily_provider import TavilyProvider
        with self.assertRaises(ValueError):
            TavilyProvider(cache=_NullCache(), api_key=None)
        with self.assertRaises(ValueError):
            TavilyProvider(cache=_NullCache(), api_key="")
        with self.assertRaises(ValueError):
            TavilyProvider(cache=_NullCache(), api_key="   ")

    # ── happy path ──────────────────────────────────────────────

    def test_search_uses_post_and_maps_web_evidence(self):
        response = self._success()
        provider, session = self._provider(response=response)

        results = provider.search(" attention mechanisms ", limit=3)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["sourceType"], "web_search")
        self.assertEqual(item["provider"], "Tavily Search")
        self.assertEqual(item["providerId"], "https://arxiv.org/abs/1706.03762")
        self.assertEqual(item["title"], "Attention Is All You Need")
        self.assertEqual(item["abstract"], "The dominant sequence transduction models based on attention.")
        self.assertEqual(item["url"], "https://arxiv.org/abs/1706.03762")
        self.assertEqual(item["doi"], "")
        self.assertEqual(item["authors"], [])
        self.assertIsNone(item["year"])
        self.assertEqual(item["retrievedAt"], "2026-07-12T12:00:00Z")
        self.assertEqual(item["query"], "attention mechanisms")
        # Answer field stored in license as JSON with ai_generated_summary marker
        self.assertIn("ai_generated_summary", item["license"])
        self.assertIn("Transformer architecture", item["license"])

        self.assertEqual(len(session.calls), 1)
        url, options = session.calls[0]
        self.assertEqual(url, "https://api.tavily.com/search")
        body = json.loads(options["data"])
        self.assertEqual(body["query"], "attention mechanisms")
        self.assertEqual(body["search_depth"], "advanced")
        self.assertTrue(body["include_answer"])
        self.assertFalse(body["include_raw_content"])
        self.assertEqual(body["max_results"], 3)
        self.assertEqual(body["api_key"], "test-tavily-key")
        self.assertEqual(options["headers"]["Content-Type"], "application/json")
        self.assertEqual(options["timeout"], (3.05, 10.0))
        self.assertFalse(options["allow_redirects"])
        self.assertTrue(options["stream"])
        self.assertTrue(response.closed)

    def test_no_answer_field_produces_empty_license(self):
        provider, _session = self._provider(response=_FakeResponse(body=_NO_ANSWER_RESPONSE))
        results = provider.search("attention")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Attention Mechanisms")
        self.assertNotIn("ai_generated_summary", results[0]["license"])

    def test_status_is_local_no_network(self):
        provider, session = self._provider(response=self._success())
        self.assertEqual(provider.status(), {
            "enabled": True, "status": "ready", "provider": "tavily",
        })
        self.assertEqual(session.calls, [])

    def test_capability_flags(self):
        provider, _session = self._provider(response=self._success())
        self.assertTrue(provider.supports_web_search)
        self.assertFalse(provider.supports_page_fetch)

    def test_search_rejects_invalid_query_and_limit(self):
        provider, session = self._provider(response=self._success())
        cases = [("", 5), ("   ", 5), (None, 5), ("q", 0), ("q", 21), ("q", True)]
        for query, limit in cases:
            with self.subTest(query=query, limit=limit):
                with self.assertRaises(ValueError):
                    provider.search(query, limit=limit)
        self.assertEqual(session.calls, [])

    def test_empty_results(self):
        provider, _session = self._provider(response=_FakeResponse(body=_EMPTY_RESPONSE))
        results = provider.search("nothing", limit=5)
        self.assertEqual(results, [])

    def test_search_bounds_untrusted_fields(self):
        provider, _session = self._provider(response=_FakeResponse(body=_BOUNDED_FIELDS))
        item = provider.search("q" * 2000, limit=1)[0]
        self.assertLessEqual(len(item["title"]), 1000)
        self.assertLessEqual(len(item["abstract"]), 10000)
        self.assertLessEqual(len(item["url"]), 2048)
        self.assertLessEqual(len(item["query"]), 1000)

    # ── error handling ──────────────────────────────────────────

    def test_malformed_json_is_rejected(self):
        from services.providers.tavily_provider import TavilyProviderError
        provider, _session = self._provider(response=_FakeResponse(body=_MALFORMED))
        with self.assertRaises(TavilyProviderError) as ctx:
            provider.search("query")
        self.assertEqual(ctx.exception.code, "invalid_response")

    def test_invalid_response_shape_is_rejected(self):
        from services.providers.tavily_provider import TavilyProviderError
        for body in (_MISSING_RESULTS, _RESULTS_NOT_LIST):
            with self.subTest(body=body[:30]):
                provider, _session = self._provider(response=_FakeResponse(body=body))
                with self.assertRaises(TavilyProviderError) as ctx:
                    provider.search("query")
                self.assertEqual(ctx.exception.code, "invalid_response")

    def test_http_errors_use_sanitized_codes(self):
        from services.providers.tavily_provider import TavilyProvider, TavilyProviderError
        cases = [
            (_FakeSession(response=_FakeResponse(status_code=302, body=b"s")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=429, body=b"s")), "http_error"),
            (_FakeSession(response=_FakeResponse(status_code=503, body=b"s")), "http_error"),
            (_FakeSession(error=requests.Timeout("secret")), "timeout"),
            (_FakeSession(error=requests.RequestException("secret")), "network_error"),
        ]
        for session, expected in cases:
            with self.subTest(expected=expected):
                p = TavilyProvider(session=session, cache=_NullCache(), min_interval_seconds=0, api_key="k")
                with self.assertRaises(TavilyProviderError) as ctx:
                    p.search("s", limit=2)
                self.assertEqual(ctx.exception.code, expected)
                self.assertNotIn("secret", str(ctx.exception))

    def test_response_size_is_limited(self):
        from services.providers.tavily_provider import TavilyProviderError
        r = _FakeResponse(headers={"Content-Length": str(1024 * 1024 + 1)})
        p, _ = self._provider(response=r)
        with self.assertRaises(TavilyProviderError) as ctx:
            p.search("q")
        self.assertEqual(ctx.exception.code, "response_too_large")

    # ── cache ───────────────────────────────────────────────────

    def test_cache_hit_skips_network(self):
        from services import trace_service
        from services.external_search_cache import ExternalSearchCache
        from services.providers.tavily_provider import TavilyProvider

        trace_id = trace_service.start_trace("unit_tavily_cache")
        with tempfile.TemporaryDirectory() as d:
            cache = ExternalSearchCache(Path(d) / "cache.json")
            first = TavilyProvider(
                session=_SequenceSession([self._success()]), cache=cache,
                min_interval_seconds=0, api_key="k",
            )
            first.search("  Attention   Mechanisms  ", limit=5)
            second = TavilyProvider(
                session=_SequenceSession([]), cache=cache,
                min_interval_seconds=0, api_key="k",
            )
            results = second.search("attention mechanisms", limit=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["query"], "attention mechanisms")
        snap = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(snap["counters"]["externalSearchCacheHits"], 1)
        trace_service.clear_traces()

    # ── rate limiting ───────────────────────────────────────────

    def test_rate_limit_waits_between_requests(self):
        from services.providers.tavily_provider import TavilyProvider
        ft = _FakeTime()
        s = _SequenceSession([self._success(), self._success()])
        p = TavilyProvider(session=s, cache=_NullCache(), sleep_fn=ft.sleep,
                           monotonic_clock=ft.monotonic, min_interval_seconds=1.0, api_key="k")
        p.search("a")
        p.search("b")
        self.assertEqual(ft.sleeps, [1.0])
        self.assertEqual(len(s.calls), 2)

    # ── retry ───────────────────────────────────────────────────

    def test_retryable_statuses_use_exponential_backoff(self):
        from services.providers.tavily_provider import TavilyProvider
        ft = _FakeTime()
        s = _SequenceSession([_FakeResponse(status_code=500), _FakeResponse(status_code=503), self._success()])
        p = TavilyProvider(session=s, cache=_NullCache(), sleep_fn=ft.sleep,
                           monotonic_clock=ft.monotonic, min_interval_seconds=0, api_key="k")
        r = p.search("q")
        self.assertEqual(len(r), 1)
        self.assertEqual(ft.sleeps, [0.5, 1.0])
        self.assertEqual(len(s.calls), 3)

    def test_retry_after_over_thirty_seconds_stops(self):
        from services.providers.tavily_provider import TavilyProvider, TavilyProviderError
        s = _SequenceSession([_FakeResponse(status_code=429, headers={"Retry-After": "31"}), self._success()])
        p = TavilyProvider(session=s, cache=_NullCache(), min_interval_seconds=0, api_key="k")
        with self.assertRaises(TavilyProviderError) as ctx:
            p.search("q")
        self.assertEqual(ctx.exception.code, "http_error")
        self.assertEqual(len(s.calls), 1)

    def test_non_retryable_status_one_attempt(self):
        from services.providers.tavily_provider import TavilyProvider, TavilyProviderError
        for o in (_FakeResponse(status_code=302), _FakeResponse(status_code=400)):
            with self.subTest(status=o.status_code):
                s = _SequenceSession([o])
                p = TavilyProvider(session=s, cache=_NullCache(), min_interval_seconds=0, api_key="k")
                with self.assertRaises(TavilyProviderError):
                    p.search("q")
                self.assertEqual(len(s.calls), 1)

    # ── builder ─────────────────────────────────────────────────

    def test_builder_extracts_api_key(self):
        from services.providers.tavily_provider import build_tavily_provider
        p = build_tavily_provider({"TAVILY_API_KEY": "bk"})
        self.assertEqual(p.name, "tavily")
        self.assertTrue(p.supports_web_search)

    def test_builder_without_api_key_raises(self):
        from services.providers.tavily_provider import build_tavily_provider
        with self.assertRaises(ValueError):
            build_tavily_provider({})


if __name__ == "__main__":
    unittest.main()
