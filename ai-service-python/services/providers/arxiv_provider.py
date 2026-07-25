import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

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
from services.safety_service import sanitize_untrusted_text
from services.trace_service import record_counter

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
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

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_OPENSEARCH_NS = "{http://a9.com/-/spec/opensearch/1.1/}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivProviderError(RuntimeError):
    def __init__(self, code: str, status_code: int | None = None):
        self.code = code
        self.status_code = status_code
        super().__init__(f"ArXiv request failed ({code}).")


class ArxivProvider:
    name = "arxiv"
    enabled = True
    supports_web_search = False
    supports_page_fetch = False

    def __init__(
        self,
        session: requests.Session | None = None,
        clock: Callable[[], datetime] | None = None,
        cache: ExternalSearchCache | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_clock: Callable[[], float] = time.monotonic,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    ):
        self._session = session or requests.Session()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._cache = cache or ExternalSearchCache(default_external_search_cache_path())
        self._sleep = sleep_fn
        self._monotonic_clock = monotonic_clock
        self._min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._rate_limit_lock = threading.Lock()
        self._next_request_at = 0.0

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "status": "ready",
            "provider": self.name,
        }

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
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
                    ARXIV_ENDPOINT,
                    params={
                        "search_query": normalized_query,
                        "start": 0,
                        "max_results": normalized_limit,
                    },
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/atom+xml",
                    },
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                    stream=True,
                )
                status_code = int(response.status_code)
                if 200 <= status_code < 300:
                    raw_bytes = _read_response_bytes(response)
                    results = deduplicate_external_evidence(
                        _parse_atom_entries(
                            raw_bytes,
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
                raise ArxivProviderError("http_error", status_code=status_code)
            except ArxivProviderError:
                raise
            except requests.Timeout:
                raise ArxivProviderError("timeout") from None
            except requests.RequestException:
                raise ArxivProviderError("network_error") from None
            finally:
                if response is not None:
                    response.close()

        raise ArxivProviderError("http_error")

    def _wait_before_request(self, retry_delay: float) -> None:
        with self._rate_limit_lock:
            now = float(self._monotonic_clock())
            delay = max(float(retry_delay), self._next_request_at - now, 0.0)
            if delay > 0:
                self._sleep(delay)
            started_at = float(self._monotonic_clock())
            self._next_request_at = started_at + self._min_interval_seconds


def build_arxiv_provider(_config: Any) -> ArxivProvider:
    return ArxivProvider(
        cache=ExternalSearchCache(default_external_search_cache_path()),
    )


def _retry_delay(headers: Any, attempt: int, clock: Callable[[], datetime]) -> float | None:
    retry_after = ""
    if hasattr(headers, "get"):
        retry_after = str(headers.get("Retry-After") or headers.get("retry-after") or "").strip()
    delay = _parse_retry_after(retry_after, clock) if retry_after else None
    if delay is None:
        delay = 0.5 * (2 ** attempt)
    if delay > MAX_RETRY_AFTER_SECONDS:
        return None
    return max(0.0, delay)


def _parse_retry_after(value: str, clock: Callable[[], datetime]) -> float | None:
    from email.utils import parsedate_to_datetime

    try:
        delay = float(value)
        return delay if delay >= 0 else None
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        now = clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return max(0.0, (retry_at - now).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _validate_query(query: Any) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("ArXiv search query must be a non-empty string.")
    return _bounded_text(query, MAX_QUERY_CHARS)


def _validate_limit(limit: Any) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise ValueError("ArXiv result limit must be an integer between 1 and 20.")
    return limit


def _read_response_bytes(response: Any) -> bytes:
    content_length = response.headers.get("Content-Length") or response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise ArxivProviderError("response_too_large")
        except (TypeError, ValueError):
            raise ArxivProviderError("invalid_response") from None

    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise ArxivProviderError("response_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_atom_entries(
    raw_bytes: bytes,
    query: str,
    retrieved_at: str,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        root = ElementTree.fromstring(raw_bytes.decode("utf-8"))
    except (ElementTree.ParseError, UnicodeDecodeError):
        raise ArxivProviderError("invalid_response") from None

    entries = root.findall(f"{_ATOM_NS}entry")
    results = []
    for entry in entries:
        if not _is_valid_entry(entry):
            continue
        try:
            results.append(normalize_external_evidence(
                _map_entry(entry, query=query, retrieved_at=retrieved_at)
            ))
        except ValueError:
            continue
        if len(results) >= limit:
            break
    return results


def _is_valid_entry(entry: ElementTree.Element) -> bool:
    title_elem = entry.find(f"{_ATOM_NS}title")
    if title_elem is None or not _clean_text(title_elem.text).strip():
        return False
    id_elem = entry.find(f"{_ATOM_NS}id")
    if id_elem is None or not _clean_text(id_elem.text).strip():
        return False
    return True


def _map_entry(entry: ElementTree.Element, query: str, retrieved_at: str) -> dict[str, Any]:
    arxiv_id = _entry_id(entry)
    return {
        "provider": "ArXiv",
        "providerId": arxiv_id,
        "title": _entry_title(entry),
        "authors": _entry_authors(entry),
        "year": _entry_year(entry),
        "abstract": _entry_summary(entry),
        "doi": _entry_doi(entry),
        "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
        "retrievedAt": retrieved_at,
        "query": query,
        "license": _entry_license(entry),
    }


def _entry_id(entry: ElementTree.Element) -> str:
    raw = _clean_text(_child_text(entry, f"{_ATOM_NS}id"))
    if not raw:
        return ""
    m = re.search(r"arxiv[:.]org/abs/([a-zA-Z0-9./-]+)", raw)
    if m:
        return _bounded_text(m.group(1), MAX_ID_CHARS)
    m = re.match(r"^([a-zA-Z0-9./-]+)$", raw)
    if m:
        return _bounded_text(m.group(1), MAX_ID_CHARS)
    return ""


def _entry_title(entry: ElementTree.Element) -> str:
    raw = _clean_text(_child_text(entry, f"{_ATOM_NS}title"))
    return _sanitize_untrusted_metadata(raw, MAX_TITLE_CHARS)


def _entry_authors(entry: ElementTree.Element) -> list[str]:
    authors = []
    for author_elem in entry.findall(f"{_ATOM_NS}author"):
        name = _clean_text(_child_text(author_elem, f"{_ATOM_NS}name"))
        if not name:
            continue
        authors.append(_sanitize_untrusted_metadata(name, MAX_AUTHOR_CHARS))
        if len(authors) >= MAX_AUTHOR_COUNT:
            break
    return authors


def _entry_year(entry: ElementTree.Element) -> int | None:
    published = _clean_text(_child_text(entry, f"{_ATOM_NS}published"))
    match = re.match(r"(\d{4})", published)
    if match:
        try:
            year = int(match.group(1))
            if 1000 <= year <= 9999:
                return year
        except (TypeError, ValueError):
            pass
    return None


def _entry_summary(entry: ElementTree.Element) -> str:
    raw = _clean_text(_child_text(entry, f"{_ATOM_NS}summary"))
    if raw:
        text = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
        raw = _clean_text(text)
    return _sanitize_untrusted_metadata(raw, MAX_ABSTRACT_CHARS)


def _entry_doi(entry: ElementTree.Element) -> str:
    for link in entry.findall(f"{_ATOM_NS}link"):
        rel = link.get("rel", "")
        title_attr = (link.get("title") or "").lower()
        href = (link.get("href") or "").strip()
        if rel == "related" and "doi" in title_attr:
            doi = _clean_text(href)
            doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
            doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
            return _bounded_text(doi.strip().lower(), MAX_ID_CHARS)
    return ""


def _entry_license(entry: ElementTree.Element) -> str:
    license_elem = entry.find(f"{_ARXIV_NS}license")
    if license_elem is not None:
        href = (license_elem.get("href") or "").strip()
        if href:
            return _bounded_text(href, MAX_ID_CHARS)
    return ""


def _child_text(elem: ElementTree.Element, tag: str) -> str:
    child = elem.find(tag)
    if child is not None:
        return "".join(child.itertext())
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
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
