import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

from core.config import settings
from services.external_evidence import deduplicate_external_evidence, normalize_external_evidence
from services.external_search_cache import (
    ExternalSearchCache,
    default_external_search_cache_path,
    normalize_external_search_query,
)
from services.safety_service import sanitize_untrusted_text
from services.trace_service import record_counter


SEMANTIC_SCHOLAR_SEARCH_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
REQUEST_TIMEOUT = (3.05, 10.0)
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_RESULTS = 20
MAX_QUERY_CHARS = 1000
MAX_TITLE_CHARS = 1000
MAX_AUTHOR_COUNT = 100
MAX_AUTHOR_CHARS = 200
MAX_ABSTRACT_CHARS = 10000
MAX_ID_CHARS = 200
USER_AGENT = "PixiuExternalAcademicSearch/1.0"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 30.0
DEFAULT_MIN_INTERVAL_SECONDS = 1.0
SEMANTIC_SCHOLAR_FIELDS = "title,authors,year,abstract,externalIds,url,publicationVenue"
SEMANTIC_SCHOLAR_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"


class SemanticScholarProviderError(RuntimeError):
    def __init__(self, code: str, status_code: Optional[int] = None):
        self.code = code
        self.status_code = status_code
        super().__init__(f"Semantic Scholar request failed ({code}).")


class SemanticScholarProvider:
    name = "semantic_scholar"
    enabled = True
    supports_web_search = False
    supports_page_fetch = False

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        clock: Optional[Callable[[], datetime]] = None,
        cache: Optional[ExternalSearchCache] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_clock: Callable[[], float] = time.monotonic,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        api_key: Optional[str] = None,
    ):
        self._session = session or requests.Session()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache = cache or ExternalSearchCache(default_external_search_cache_path())
        self._sleep = sleep_fn
        self._monotonic_clock = monotonic_clock
        self._min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
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
                    SEMANTIC_SCHOLAR_SEARCH_ENDPOINT,
                    params={
                        "query": normalized_query,
                        "limit": normalized_limit,
                        "fields": SEMANTIC_SCHOLAR_FIELDS,
                    },
                    headers=self._build_headers(),
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
                    self._cache.put(self.name, normalized_query, normalized_limit, results)
                    return results
                if status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    retry_delay = _retry_delay(response.headers, attempt, self._clock)
                    if retry_delay is not None:
                        continue
                raise SemanticScholarProviderError("http_error", status_code=status_code)
            except SemanticScholarProviderError:
                raise
            except requests.Timeout:
                raise SemanticScholarProviderError("timeout") from None
            except requests.RequestException:
                raise SemanticScholarProviderError("network_error") from None
            finally:
                if response is not None:
                    response.close()

        raise SemanticScholarProviderError("http_error")

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    def _wait_before_request(self, retry_delay: float) -> None:
        with self._rate_limit_lock:
            now = float(self._monotonic_clock())
            delay = max(float(retry_delay), self._next_request_at - now, 0.0)
            if delay > 0:
                self._sleep(delay)
            started_at = float(self._monotonic_clock())
            self._next_request_at = started_at + self._min_interval_seconds


def build_semantic_scholar_provider(config: Any) -> SemanticScholarProvider:
    api_key = None
    if isinstance(config, dict) or hasattr(config, "get"):
        env_key = str(config.get(SEMANTIC_SCHOLAR_API_KEY_ENV, "")).strip()
        if env_key:
            api_key = env_key
    if not api_key:
        api_key = settings.semantic_scholar_api_key.strip() or None
    return SemanticScholarProvider(
        cache=ExternalSearchCache(default_external_search_cache_path()),
        api_key=api_key or None,
    )


def _retry_delay(headers: Any, attempt: int, clock: Callable[[], datetime]) -> Optional[float]:
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
    from email.utils import parsedate_to_datetime

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
        raise ValueError("Semantic Scholar search query must be a non-empty string.")
    return _bounded_text(query, MAX_QUERY_CHARS)


def _validate_limit(limit: Any) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise ValueError("Semantic Scholar result limit must be an integer between 1 and 20.")
    return limit


def _read_json_response(response: Any) -> Dict[str, Any]:
    content_length = response.headers.get("Content-Length") or response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise SemanticScholarProviderError("response_too_large")
        except (TypeError, ValueError):
            raise SemanticScholarProviderError("invalid_response") from None

    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise SemanticScholarProviderError("response_too_large")
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SemanticScholarProviderError("invalid_response") from None
    if not isinstance(payload, dict):
        raise SemanticScholarProviderError("invalid_response")
    return payload


def _normalize_items(
    payload: Dict[str, Any],
    query: str,
    retrieved_at: str,
    limit: int,
) -> List[Dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise SemanticScholarProviderError("invalid_response")

    results = []
    for paper in data:
        if not isinstance(paper, dict):
            continue
        try:
            mapped = _map_paper(paper, query=query, retrieved_at=retrieved_at)
        except ValueError:
            continue
        if not mapped.get("providerId") or not mapped.get("title"):
            continue
        try:
            results.append(normalize_external_evidence(mapped))
        except ValueError:
            continue
        if len(results) >= limit:
            break
    return results


def _map_paper(paper: Dict[str, Any], query: str, retrieved_at: str) -> Dict[str, Any]:
    external_ids = paper.get("externalIds") or {}
    paper_id = _clean_text(paper.get("paperId"))
    return {
        "provider": "Semantic Scholar",
        "providerId": _bounded_text(paper_id, MAX_ID_CHARS),
        "title": _sanitize_untrusted_metadata(paper.get("title"), MAX_TITLE_CHARS),
        "authors": _extract_authors(paper.get("authors")),
        "year": _extract_year(paper.get("year")),
        "abstract": _extract_abstract(paper.get("abstract")),
        "doi": _bounded_text(_clean_text(external_ids.get("DOI")).lower(), MAX_ID_CHARS),
        "url": _bounded_text(paper.get("url"), MAX_ID_CHARS),
        "retrievedAt": retrieved_at,
        "query": query,
        "license": _extract_venue(paper.get("publicationVenue")),
    }


def _extract_authors(authors_value: Any) -> List[str]:
    if not isinstance(authors_value, list):
        return []
    authors = []
    for author in authors_value[:MAX_AUTHOR_COUNT]:
        if not isinstance(author, dict):
            continue
        name = _sanitize_untrusted_metadata(author.get("name"), MAX_AUTHOR_CHARS)
        if name:
            authors.append(name)
    return authors


def _extract_year(year_value: Any) -> Optional[int]:
    if year_value is None or year_value == "":
        return None
    try:
        year = int(year_value)
    except (TypeError, ValueError):
        return None
    return year if 1000 <= year <= 9999 else None


def _extract_abstract(abstract_value: Any) -> str:
    if abstract_value is None or abstract_value == "":
        return ""
    return _sanitize_untrusted_metadata(abstract_value, MAX_ABSTRACT_CHARS)


def _extract_venue(venue_value: Any) -> str:
    if isinstance(venue_value, dict):
        name = _clean_text(venue_value.get("name"))
        if name:
            return _bounded_text(name, MAX_ID_CHARS)
    if isinstance(venue_value, str):
        return _bounded_text(_clean_text(venue_value), MAX_ID_CHARS)
    return ""


def _sanitize_untrusted_metadata(value: Any, limit: int) -> str:
    sanitized = sanitize_untrusted_text(value, max_tokens=max(1, (limit + 3) // 4))
    return _bounded_text(sanitized.get("text"), limit)


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
