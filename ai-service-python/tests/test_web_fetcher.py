import unittest


class WebFetcherModuleTests(unittest.TestCase):
    def test_module_imports(self):
        from services import web_fetcher
        self.assertIsNotNone(web_fetcher)


class _FakeMonotonic:
    def __init__(self, start: float = 0.0):
        self.seconds = start

    def monotonic(self) -> float:
        return self.seconds

    def sleep(self, seconds: float) -> None:
        self.seconds += seconds


class ConcurrencyControlTests(unittest.TestCase):
    def test_semaphore_limits_concurrent_fetches(self):
        import threading
        from services.web_fetcher import _fetch_concurrency_semaphore, _MAX_CONCURRENT_FETCHES

        sem = _fetch_concurrency_semaphore
        acquired = 0
        for _ in range(_MAX_CONCURRENT_FETCHES):
            acquired += sem.acquire(blocking=False)
        self.assertEqual(acquired, _MAX_CONCURRENT_FETCHES)
        # Next acquire should fail (no blocking in test)
        self.assertFalse(sem.acquire(blocking=False))
        # Release all
        for _ in range(_MAX_CONCURRENT_FETCHES):
            sem.release()

    def test_per_host_rate_limiter_enforces_interval(self):
        from services.web_fetcher import _get_host_rate_limiter

        # Reset rate limiters for test isolation
        from services import web_fetcher
        with web_fetcher._host_rate_limiters_lock:
            web_fetcher._host_rate_limiters.clear()

        fake_time = _FakeMonotonic(0.0)
        limiter = _get_host_rate_limiter(
            "example.com",
            monotonic_clock=fake_time.monotonic,
            sleep_fn=fake_time.sleep,
        )
        # First request: allowed
        wait_ms = limiter.wait_before_request(retry_delay=0.0)
        self.assertEqual(wait_ms, 0)
        # Immediate second request: should wait ~2000ms
        wait_ms = limiter.wait_before_request(retry_delay=0.0)
        self.assertGreaterEqual(wait_ms, 1900)
        # Advance time well past the rate limit window
        fake_time.seconds = 5.0
        wait_ms = limiter.wait_before_request(retry_delay=0.0)
        self.assertEqual(wait_ms, 0)


class _FakeResponse:
    """Mimics requests.Response for testing."""
    def __init__(self, status_code=200, headers=None, body=b"", chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size=65536):
        if self._chunks:
            yield from self._chunks
        elif self._body:
            yield self._body

    def close(self):
        self.closed = True


class _FakeSession:
    """Mimics requests.Session for testing."""
    def __init__(self):
        self.calls = []
        self.response = None
        self.error = None

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if self.error:
            raise self.error
        return self.response


class _SequenceSession:
    """Returns responses in order for testing retry logic."""
    def __init__(self, responses):
        self.calls = []
        self._responses = list(responses)

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if not self._responses:
            raise RuntimeError("no more responses")
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FetchExecutionTests(unittest.TestCase):
    def setUp(self):
        from services import web_fetcher
        # Clear rate limiters between tests to avoid cross-test delays
        with web_fetcher._host_rate_limiters_lock:
            web_fetcher._host_rate_limiters.clear()

    def _fake_clock_sleep(self):
        """Return a (clock, sleep_fn) pair using _FakeMonotonic for instant tests."""
        ft = _FakeMonotonic(0.0)
        return ft.monotonic, ft.sleep

    def test_fetch_rejects_http_url(self):
        from services.web_fetcher import fetch_web_page, FetchError

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("http://example.com/some-path", clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, FetchError.NOT_WHITELISTED)
        self.assertEqual(result.content, "")

    def test_fetch_rejects_non_whitelisted_host(self):
        from services.web_fetcher import fetch_web_page, FetchError

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://evil.example.com/page", clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, FetchError.NOT_WHITELISTED)
        self.assertNotIn("evil.example.com", repr(result))

    def test_fetch_content_type_pre_check(self):
        from services.web_fetcher import fetch_web_page, FetchError

        fake_response = _FakeResponse(
            status_code=200,
            headers={"Content-Type": "application/pdf"},
            body=b"%PDF-1.4 fake pdf",
        )
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/article", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, FetchError.UNSUPPORTED_CONTENT_TYPE)

    def test_fetch_2mib_limit_via_header(self):
        from services.web_fetcher import fetch_web_page, FetchError

        fake_response = _FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/html", "Content-Length": str(2 * 1024 * 1024 + 1)},
            body=b"x",
        )
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/article", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, FetchError.RESPONSE_TOO_LARGE)

    def test_fetch_success_returns_content(self):
        from services.web_fetcher import fetch_web_page

        html = b"<html><body><p>Hello World</p></body></html>"
        fake_response = _FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            body=html,
        )
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/article", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, "success")
        self.assertIn("Hello World", result.content)
        self.assertEqual(result.content_type, "text/html; charset=utf-8")

    def test_fetch_http_error_no_retry_on_4xx(self):
        from services.web_fetcher import fetch_web_page, FetchError

        fake_response = _FakeResponse(status_code=404, headers={}, body=b"")
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/notfound", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, FetchError.HTTP_ERROR)
        self.assertEqual(result.retry_count, 0)

    def test_fetch_retries_on_5xx_once(self):
        from services.web_fetcher import fetch_web_page

        responses = [
            _FakeResponse(status_code=503, headers={}, body=b""),
            _FakeResponse(status_code=200, headers={"Content-Type": "text/html"}, body=b"<html>ok</html>"),
        ]
        fake_session = _SequenceSession(responses)

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/article", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.retry_count, 1)

    def test_fetch_timeout_returns_timeout_error(self):
        import requests
        from services.web_fetcher import fetch_web_page, FetchError

        fake_session = _FakeSession()
        fake_session.error = requests.Timeout("connect timeout")

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/article", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, FetchError.TIMEOUT)

    def test_fetch_redirect_detected(self):
        from services.web_fetcher import fetch_web_page, FetchError

        fake_response = _FakeResponse(status_code=301, headers={"Location": "https://other.com"}, body=b"")
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/article", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, FetchError.REDIRECT_DETECTED)

    def test_fetch_plain_text_content_type(self):
        from services.web_fetcher import fetch_web_page

        text = b"Plain text content from a web page."
        fake_response = _FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/plain"},
            body=text,
        )
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/robots.txt", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, "success")
        self.assertIn("Plain text", result.content)

    def test_fetch_json_content_type(self):
        from services.web_fetcher import fetch_web_page

        json_body = b'{"key": "value", "data": [1, 2, 3]}'
        fake_response = _FakeResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=json_body,
        )
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = self._fake_clock_sleep()
        result = fetch_web_page("https://www.nature.com/api/data", session=fake_session, clock=clock, sleep_fn=sleep_fn)
        self.assertEqual(result.status, "success")
        self.assertIn('"key"', result.content)


class DnsInternalIpTests(unittest.TestCase):
    def test_fetch_rejects_internal_ip_resolution(self):
        import socket
        from services import url_whitelist
        from services.web_fetcher import fetch_web_page, FetchError

        original_getaddrinfo = url_whitelist._getaddrinfo
        try:
            url_whitelist._getaddrinfo = lambda host: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80))
            ]
            clock, sleep_fn = _fake_clock_sleep_fn()
            result = fetch_web_page(
                "https://www.nature.com/article",
                clock=clock, sleep_fn=sleep_fn,
            )
            self.assertEqual(result.status, FetchError.NOT_WHITELISTED)
            self.assertEqual(result.content, "")
        finally:
            url_whitelist._getaddrinfo = original_getaddrinfo

    def test_fetch_rejects_loopback_resolution(self):
        import socket
        from services import url_whitelist
        from services.web_fetcher import fetch_web_page, FetchError

        original_getaddrinfo = url_whitelist._getaddrinfo
        try:
            url_whitelist._getaddrinfo = lambda host: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
            ]
            clock, sleep_fn = _fake_clock_sleep_fn()
            result = fetch_web_page(
                "https://www.nature.com/article",
                clock=clock, sleep_fn=sleep_fn,
            )
            self.assertEqual(result.status, FetchError.NOT_WHITELISTED)
        finally:
            url_whitelist._getaddrinfo = original_getaddrinfo


class ErrorSanitizationTests(unittest.TestCase):
    def test_error_result_never_leaks_url(self):
        from services.web_fetcher import fetch_web_page

        sensitive_url = "https://www.nature.com/article?token=sk-secret-12345"
        clock, sleep_fn = _fake_clock_sleep_fn()
        result = fetch_web_page(sensitive_url, clock=clock, sleep_fn=sleep_fn)
        result_str = str(result)
        self.assertNotIn("sk-secret", result_str)
        self.assertNotIn("token", result_str)
        self.assertNotIn("nature.com/article", result_str)

    def test_error_result_never_leaks_response_body(self):
        from services.web_fetcher import fetch_web_page

        fake_response = _FakeResponse(
            status_code=500,
            headers={"Content-Type": "text/html"},
            body=b"Internal error: database password=secret123",
        )
        fake_session = _FakeSession()
        fake_session.response = fake_response

        clock, sleep_fn = _fake_clock_sleep_fn()
        result = fetch_web_page(
            "https://www.nature.com/error",
            session=fake_session, clock=clock, sleep_fn=sleep_fn,
        )
        self.assertEqual(result.content, "")
        result_str = str(result)
        self.assertNotIn("secret123", result_str)
        self.assertNotIn("password", result_str)

    def test_all_error_codes_are_defined(self):
        from services.web_fetcher import FetchError

        error_codes = [
            FetchError.INVALID_URL, FetchError.NOT_WHITELISTED,
            FetchError.NOT_HTTPS, FetchError.REDIRECT_DETECTED,
            FetchError.UNSUPPORTED_CONTENT_TYPE, FetchError.RESPONSE_TOO_LARGE,
            FetchError.TIMEOUT, FetchError.NETWORK_ERROR, FetchError.HTTP_ERROR,
            FetchError.DECODE_ERROR, FetchError.RATE_LIMITED,
            FetchError.CONCURRENCY_BLOCKED,
        ]
        for code in error_codes:
            self.assertIsInstance(code, str)
            self.assertGreater(len(code), 0)
            # Error codes should not contain URL patterns (like "://")
            self.assertNotIn("://", code)

    def test_fetch_result_is_immutable(self):
        from services.web_fetcher import FetchResult

        result = FetchResult(
            status="success", url="nature.com", content="test",
            content_type="text/html", content_length=100,
            fetched_at="2026-01-01T00:00:00Z", elapsed_ms=50, retry_count=0,
        )
        with self.assertRaises(Exception):
            result.status = "modified"  # type: ignore[misc]


def _fake_clock_sleep_fn():
    """Return a (clock, sleep_fn) pair using _FakeMonotonic for instant tests."""
    ft = _FakeMonotonic(0.0)
    return ft.monotonic, ft.sleep


if __name__ == "__main__":
    unittest.main()
