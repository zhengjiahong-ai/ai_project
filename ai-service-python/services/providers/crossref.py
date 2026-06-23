import json
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from services.external_evidence import (
    deduplicate_external_evidence,
    normalize_external_evidence,
)
from services.external_search_cache import (
    ExternalSearchCache,
    default_external_search_cache_path,
    normalize_external_search_query,
)
from services.trace_service import record_counter


CROSSREF_ENDPOINT = "https://api.crossref.org/works"
REQUEST_TIMEOUT = (3.05, 10.0)
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_RESULTS = 20
MAX_QUERY_CHARS = 1000
MAX_TITLE_CHARS = 1000
MAX_AUTHOR_COUNT = 100
MAX_AUTHOR_CHARS = 200
MAX_ABSTRACT_CHARS = 10000
MAX_IDENTIFIER_CHARS = 2048
USER_AGENT = "PixiuExternalAcademicSearch/1.0"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 30.0
DEFAULT_MIN_INTERVAL_SECONDS = 1.0


class CrossrefProviderError(RuntimeError):
    def __init__(self, code: str, status_code: Optional[int] = None):
        self.code = code
        self.status_code = status_code
        super().__init__(f"Crossref request failed ({code}).")


class CrossrefProvider:
    name = "crossref"
    enabled = True

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        clock: Optional[Callable[[], datetime]] = None,
        cache: Optional[ExternalSearchCache] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_clock: Callable[[], float] = time.monotonic,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    ):
        self._session = session or requests.Session()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache = cache or ExternalSearchCache(default_external_search_cache_path())
        self._sleep = sleep_fn
        self._monotonic_clock = monotonic_clock
        self._min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._rate_limit_lock = threading.Lock()
        self._next_request_at = 0.0

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "status": "ready",
            "provider": self.name,
        }

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        normalized_query = normalize_external_search_query(_validate_query(query))
        normalized_limit = _validate_limit(limit)
        cached = self._cache.get(self.name, normalized_query, normalized_limit)
        if cached is not None:
            record_counter("externalSearchCacheHits")
            return cached[:normalized_limit]

        retry_delay = 0.0
        for attempt in range(MAX_RETRIES + 1):
            self._wait_before_request(retry_delay)
            response = None
            try:
                response = self._session.get(
                    CROSSREF_ENDPOINT,
                    params={
                        "query.bibliographic": normalized_query,
                        "rows": normalized_limit,
                    },
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                    },
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                    stream=True,
                )
                status_code = int(response.status_code)
                if 200 <= status_code < 300:
                    payload = _read_json_response(response)
                    results = deduplicate_external_evidence(
                        _normalize_items(
                            payload,
                            query=normalized_query,
                            retrieved_at=_format_timestamp(self._clock()),
                            limit=normalized_limit,
                        ),
                        limit=normalized_limit,
                    )
                    self._cache.put(
                        self.name,
                        normalized_query,
                        normalized_limit,
                        results,
                    )
                    return results
                if status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    retry_delay = _retry_delay(response.headers, attempt, self._clock)
                    if retry_delay is not None:
                        continue
                raise CrossrefProviderError("http_error", status_code=status_code)
            except CrossrefProviderError:
                raise
            except requests.Timeout:
                raise CrossrefProviderError("timeout") from None
            except requests.RequestException:
                raise CrossrefProviderError("network_error") from None
            finally:
                if response is not None:
                    response.close()
        raise CrossrefProviderError("http_error")

    def _wait_before_request(self, retry_delay: float) -> None:
        with self._rate_limit_lock:
            now = float(self._monotonic_clock())
            delay = max(float(retry_delay), self._next_request_at - now, 0.0)
            if delay > 0:
                self._sleep(delay)
            started_at = float(self._monotonic_clock())
            self._next_request_at = started_at + self._min_interval_seconds


def build_crossref_provider(_config: Any) -> CrossrefProvider:
    return CrossrefProvider(
        cache=ExternalSearchCache(default_external_search_cache_path()),
    )


def _retry_delay(
    headers: Any,
    attempt: int,
    clock: Callable[[], datetime],
) -> Optional[float]:
    retry_after = ""
    if hasattr(headers, "get"):
        retry_after = str(headers.get("Retry-After") or headers.get("retry-after") or "").strip()
    delay = _parse_retry_after(retry_after, clock) if retry_after else None
    if delay is None:
        delay = 0.5 * (2 ** attempt)
    if delay > MAX_RETRY_AFTER_SECONDS:
        return None
    return max(0.0, delay)


def _parse_retry_after(value: str, clock: Callable[[], datetime]) -> Optional[float]:
    try:
        delay = float(value)
        return delay if delay >= 0 else None
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        now = clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - now).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _validate_query(query: Any) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Crossref search query must be a non-empty string.")
    return _bounded_text(query, MAX_QUERY_CHARS)


def _validate_limit(limit: Any) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise ValueError("Crossref result limit must be an integer between 1 and 20.")
    return limit


def _read_json_response(response: Any) -> Dict[str, Any]:
    content_length = response.headers.get("Content-Length") or response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise CrossrefProviderError("response_too_large")
        except (TypeError, ValueError):
            raise CrossrefProviderError("invalid_response") from None

    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise CrossrefProviderError("response_too_large")
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise CrossrefProviderError("invalid_response") from None
    if not isinstance(payload, dict):
        raise CrossrefProviderError("invalid_response")
    return payload


def _normalize_items(
    payload: Dict[str, Any],
    query: str,
    retrieved_at: str,
    limit: int,
) -> List[Dict[str, Any]]:
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("items"), list):
        raise CrossrefProviderError("invalid_response")

    results = []
    for raw_item in message["items"]:
        if not isinstance(raw_item, dict):
            continue
        try:
            results.append(normalize_external_evidence(
                _map_item(raw_item, query=query, retrieved_at=retrieved_at)
            ))
        except ValueError:
            continue
        if len(results) >= limit:
            break
    return results


def _map_item(item: Dict[str, Any], query: str, retrieved_at: str) -> Dict[str, Any]:
    doi = _bounded_text(item.get("DOI"), MAX_IDENTIFIER_CHARS)
    return {
        "provider": "Crossref",
        "providerId": doi,
        "title": _first_bounded(item.get("title"), MAX_TITLE_CHARS),
        "authors": _authors(item.get("author")),
        "year": _publication_year(item),
        "abstract": _abstract(item.get("abstract")),
        "doi": doi,
        "url": _bounded_text(item.get("URL"), MAX_IDENTIFIER_CHARS),
        "retrievedAt": retrieved_at,
        "query": query,
        "license": _license(item.get("license")),
    }


def _authors(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    authors = []
    for author in value[:MAX_AUTHOR_COUNT]:
        if not isinstance(author, dict):
            continue
        name = _bounded_text(author.get("name"), MAX_AUTHOR_CHARS)
        if not name:
            name = _bounded_text(
                " ".join(
                    part for part in (
                        _clean_text(author.get("given")),
                        _clean_text(author.get("family")),
                    )
                    if part
                ),
                MAX_AUTHOR_CHARS,
            )
        if name:
            authors.append(name)
    return authors


def _publication_year(item: Dict[str, Any]) -> Optional[int]:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts or not isinstance(date_parts[0], list):
            continue
        try:
            year = int(date_parts[0][0])
        except (IndexError, TypeError, ValueError):
            continue
        if 1000 <= year <= 9999:
            return year
    return None


def _abstract(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return _bounded_text(text, MAX_ABSTRACT_CHARS)


def _license(value: Any) -> str:
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        return ""
    return _bounded_text(value[0].get("URL"), MAX_IDENTIFIER_CHARS)


def _first_bounded(value: Any, limit: int) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return _bounded_text(value, limit)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _bounded_text(value: Any, limit: int) -> str:
    return _clean_text(value)[:limit]


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
