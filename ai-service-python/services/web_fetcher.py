"""Web page fetcher with security chain, concurrency control, and rate limiting.

Reuses validate_fetch_url() from url_whitelist.py for whitelist/DNS checks.
Follows the synchronous requests.Session pattern established by Brave/Tavily providers.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import requests


# ---- Error codes (sanitized, never leak raw URL or response body) ----

class FetchError:
    """Error code constants for fetch results. Not an enum to match provider patterns."""
    INVALID_URL = "invalid_url"
    NOT_WHITELISTED = "not_whitelisted"
    NOT_HTTPS = "not_https"
    REDIRECT_DETECTED = "redirect_detected"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    RESPONSE_TOO_LARGE = "response_too_large"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    DECODE_ERROR = "decode_error"
    RATE_LIMITED = "rate_limited"
    CONCURRENCY_BLOCKED = "concurrency_blocked"


# ---- Data structures ----

@dataclass(frozen=True)
class FetchResult:
    """Immutable result of a fetch attempt."""
    status: str                    # "success" or error code from FetchError
    url: str = ""                  # sanitized URL (hostname only, never full URL)
    content: str = ""              # decoded text content (empty on error)
    content_type: str = ""         # from Content-Type header
    content_length: int = 0        # bytes received
    fetched_at: str = ""           # ISO 8601 timestamp
    elapsed_ms: int = 0            # total fetch time in milliseconds
    retry_count: int = 0           # number of retries performed
    cache_hit: bool = False        # True when result came from WebFetchCache


# ---- Constants ----

_MAX_CONTENT_BYTES = 2 * 1024 * 1024   # 2 MiB
_REQUEST_TIMEOUT = (5.0, 15.0)          # (connect, read) seconds
_MAX_RETRIES = 1                        # at most 1 retry (2 total attempts)
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_ALLOWED_CONTENT_TYPES = frozenset({"text/html", "text/plain", "application/json"})
_MAX_CONCURRENT_FETCHES = 3
_MIN_INTERVAL_PER_HOST_SECONDS = 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---- Concurrency control ----

_fetch_concurrency_semaphore = threading.Semaphore(_MAX_CONCURRENT_FETCHES)


# ---- Per-host rate limiting ----

class _HostRateLimiter:
    """Per-host rate limiter using a lock and wall-clock scheduling."""

    def __init__(
        self,
        min_interval: float,
        monotonic_clock: Callable[[], float],
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self._min_interval = min_interval
        self._monotonic_clock = monotonic_clock
        self._sleep = sleep_fn
        self._lock = threading.Lock()
        self._next_request_at = 0.0

    def wait_before_request(self, retry_delay: float = 0.0) -> float:
        """Wait until the host is available. Returns milliseconds actually waited."""
        with self._lock:
            now = self._monotonic_clock()
            delay = max(retry_delay, self._next_request_at - now, 0.0)
            if delay > 0:
                self._sleep(delay)
            started_at = self._monotonic_clock()
            self._next_request_at = started_at + self._min_interval
            return max(0.0, (started_at - now) * 1000)


_host_rate_limiters: Dict[str, _HostRateLimiter] = {}
_host_rate_limiters_lock = threading.Lock()


def _get_host_rate_limiter(
    hostname: str,
    *,
    monotonic_clock: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> _HostRateLimiter:
    """Return or create a rate limiter for the given hostname."""
    normalized = hostname.strip().lower()
    with _host_rate_limiters_lock:
        if normalized not in _host_rate_limiters:
            _host_rate_limiters[normalized] = _HostRateLimiter(
                _MIN_INTERVAL_PER_HOST_SECONDS,
                monotonic_clock=monotonic_clock,
                sleep_fn=sleep_fn,
            )
        return _host_rate_limiters[normalized]


# ---- Public API ----

def fetch_web_page(
    url: str,
    *,
    session: Optional[requests.Session] = None,
    max_chars: int = 50000,
    clock: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    cache: Optional[Any] = None,
) -> FetchResult:
    """Fetch a web page through the full security chain.

    Args:
        url: The URL to fetch. Must pass validate_fetch_url().
        session: Optional requests.Session for dependency injection.
        max_chars: Maximum decoded characters to return (default 50000).
        clock: Monotonic clock for latency measurement.
        sleep_fn: Sleep function for rate limiting (injectable for tests).
        cache: Optional WebFetchCache for caching results (default None = no cache).

    Returns:
        FetchResult with status, content, and metadata.
        On any error, content is empty and status holds the error code.
    """
    from urllib.parse import urlparse

    from services.url_whitelist import validate_fetch_url

    # Step 0: Cache check (before any network or semaphore work)
    if cache is not None:
        cached = cache.get(url)
        if cached is not None:
            cached_with_flag = dict(cached)
            cached_with_flag["cache_hit"] = True
            return FetchResult(**cached_with_flag)

    # Step 1: URL sanity check
    if not url or not isinstance(url, str):
        return _error_result(FetchError.INVALID_URL)

    # Step 2: Whitelist + DNS + internal IP check
    try:
        hostname = validate_fetch_url(url)
    except ValueError:
        return _error_result(FetchError.NOT_WHITELISTED)

    # Step 3: HTTPS only (double-check; validate_fetch_url already checks this)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return _error_result(FetchError.NOT_HTTPS)

    # Step 4: Acquire concurrency semaphore (with timeout)
    acquired = _fetch_concurrency_semaphore.acquire(timeout=30.0)
    if not acquired:
        return _error_result(FetchError.CONCURRENCY_BLOCKED)

    try:
        result = _perform_fetch(url, hostname, session=session, max_chars=max_chars, clock=clock, sleep_fn=sleep_fn)
    finally:
        _fetch_concurrency_semaphore.release()

    # Step 5: Cache successful results (blocked content excluded by WebFetchCache.put)
    if cache is not None and result.status == "success":
        from services.content_safety import sanitize_fetched_web_content

        safety = sanitize_fetched_web_content(result.content, url=url)
        cache.put(url, {
            "status": result.status,
            "url": result.url,
            "content": result.content,
            "content_type": result.content_type,
            "content_length": result.content_length,
            "fetched_at": result.fetched_at,
            "elapsed_ms": 0,
            "retry_count": 0,
            "grade": safety["grade"],
        })

    return result


def _perform_fetch(
    url: str,
    hostname: str,
    *,
    session: Optional[requests.Session] = None,
    max_chars: int = 50000,
    clock: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Execute the HTTP fetch with retry, rate limiting, and safety checks."""
    sess = session or requests.Session()
    limiter = _get_host_rate_limiter(hostname, monotonic_clock=clock, sleep_fn=sleep_fn)
    retry_count = 0

    for attempt in range(_MAX_RETRIES + 1):
        # Rate limit with retry backoff
        retry_delay = 0.0 if attempt == 0 else _compute_retry_delay(attempt)
        limiter.wait_before_request(retry_delay=retry_delay)

        fetch_started = clock()
        try:
            response = sess.get(
                url,
                headers={"User-Agent": "Pixiu-Research/1.0"},
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout:
            return _error_result(FetchError.TIMEOUT, retry_count=retry_count)
        except requests.RequestException:
            return _error_result(FetchError.NETWORK_ERROR, retry_count=retry_count)

        try:
            # Check for redirects
            if 300 <= response.status_code <= 399:
                response.close()
                return _error_result(FetchError.REDIRECT_DETECTED, retry_count=retry_count)

            # Check for retryable errors
            if response.status_code in _RETRYABLE_STATUSES and retry_count < _MAX_RETRIES:
                response.close()
                retry_count += 1
                continue

            # Non-retryable HTTP errors
            if response.status_code >= 400:
                response.close()
                return _error_result(FetchError.HTTP_ERROR, retry_count=retry_count)

            # Content-Type pre-check
            content_type = response.headers.get("Content-Type", "")
            if not _is_allowed_content_type(content_type):
                response.close()
                return _error_result(FetchError.UNSUPPORTED_CONTENT_TYPE, retry_count=retry_count)

            # Size check via Content-Length header (early rejection)
            content_length_str = response.headers.get("Content-Length", "")
            if content_length_str:
                try:
                    if int(content_length_str) > _MAX_CONTENT_BYTES:
                        response.close()
                        return _error_result(FetchError.RESPONSE_TOO_LARGE, retry_count=retry_count)
                except (ValueError, TypeError):
                    pass

            # Read response in chunks with size enforcement
            chunks: list[bytes] = []
            total_bytes = 0
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    total_bytes += len(chunk)
                    if total_bytes > _MAX_CONTENT_BYTES:
                        response.close()
                        return _error_result(FetchError.RESPONSE_TOO_LARGE, retry_count=retry_count)
                    chunks.append(chunk)

            raw_body = b"".join(chunks)

            # UTF-8 decode with latin-1 fallback
            try:
                text = raw_body.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = raw_body.decode("latin-1")
                except Exception:
                    return _error_result(FetchError.DECODE_ERROR, retry_count=retry_count)

            text = text[:max_chars]

            # Content safety validation
            from services.content_safety import sanitize_fetched_web_content

            safety = sanitize_fetched_web_content(text, url=url)
            safe_text = safety["text"] if safety["grade"] != "blocked" else ""

            elapsed_ms = int((clock() - fetch_started) * 1000)
            return FetchResult(
                status="success",
                url=hostname,
                content=safe_text,
                content_type=content_type[:200],
                content_length=total_bytes,
                fetched_at=_now_iso(),
                elapsed_ms=elapsed_ms,
                retry_count=retry_count,
            )
        finally:
            response.close()

    return _error_result(FetchError.RATE_LIMITED, retry_count=retry_count)


# ---- Internal helpers ----

def _is_allowed_content_type(content_type: str) -> bool:
    """Check if the Content-Type header is in the allowed set."""
    normalized = content_type.split(";")[0].strip().lower()
    for allowed in _ALLOWED_CONTENT_TYPES:
        if normalized == allowed or normalized.startswith(allowed):
            return True
    return False


def _compute_retry_delay(attempt: int) -> float:
    """Exponential backoff: 0.5s on first retry, 1.0s on second."""
    return 0.5 * (2 ** (attempt - 1))


def _error_result(status: str, retry_count: int = 0) -> FetchResult:
    return FetchResult(
        status=status,
        url="",
        content="",
        content_type="",
        content_length=0,
        fetched_at=_now_iso(),
        elapsed_ms=0,
        retry_count=retry_count,
    )
