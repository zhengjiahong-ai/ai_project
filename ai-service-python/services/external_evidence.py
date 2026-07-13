import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


EXTERNAL_SOURCE_TYPE = "external_academic"
WEB_SEARCH_SOURCE_TYPE = "web_search"


def build_external_source_id(item: Any) -> str:
    raw = _require_mapping(item)
    provider = _normalize_provider(raw.get("provider"))
    if not provider:
        raise ValueError("External evidence provider is required.")

    doi = _normalize_doi(raw.get("doi"))
    provider_id = _clean_string(raw.get("providerId"))
    url = _normalize_url(raw.get("url"))
    title = _normalize_title(raw.get("title"))
    year = _normalize_year(raw.get("year"))

    if doi:
        identity_type = "doi"
        identity = doi
    elif provider_id:
        identity_type = "provider"
        identity = f"{provider.lower()}:{provider_id}"
    elif url:
        identity_type = "url"
        identity = url
    elif title:
        identity_type = "title"
        identity = f"{provider.lower()}:{title.lower()}:{year or ''}"
    else:
        raise ValueError("External evidence requires an identity field or title.")

    digest = hashlib.sha256(f"{identity_type}:{identity}".encode("utf-8")).hexdigest()[:24]
    return f"external-{identity_type}-{digest}"


def normalize_external_evidence(item: Any, *, source_type: str = EXTERNAL_SOURCE_TYPE) -> Dict[str, Any]:
    raw = _require_mapping(item)
    provider = _normalize_provider(raw.get("provider"))
    if not provider:
        raise ValueError("External evidence provider is required.")

    normalized = {
        "sourceId": build_external_source_id(raw),
        "sourceType": str(source_type or EXTERNAL_SOURCE_TYPE),
        "provider": provider,
        "providerId": _clean_string(raw.get("providerId")),
        "title": _normalize_title(raw.get("title")),
        "authors": _normalize_authors(raw.get("authors")),
        "year": _normalize_year(raw.get("year")),
        "abstract": _clean_string(raw.get("abstract")),
        "doi": _normalize_doi(raw.get("doi")),
        "url": _normalize_url(raw.get("url")),
        "retrievedAt": _clean_string(raw.get("retrievedAt")),
        "query": _clean_string(raw.get("query")),
        "license": _clean_string(raw.get("license")),
        "provenance": {
            "discoveryPath": str(source_type or EXTERNAL_SOURCE_TYPE),
            "searchQuery": _clean_string(raw.get("query")),
            "searchIteration": None,
            "sourceUrl": _normalize_url(raw.get("url")),
            "retrievalTimestamp": _clean_string(raw.get("retrievedAt")),
        },
    }
    return normalized


def normalize_external_evidence_items(items: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if limit is not None and limit <= 0:
        return []

    normalized = []
    for item in _iter_items(items):
        normalized.append(normalize_external_evidence(item))
        if limit is not None and len(normalized) >= limit:
            break
    return normalized


def deduplicate_external_evidence(
    items: Any,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if limit is not None and limit <= 0:
        return []

    seen_dois = set()
    seen_provider_ids = set()
    seen_titles = set()
    deduplicated = []
    for item in _iter_items(items):
        if not isinstance(item, dict):
            continue
        doi = _normalize_doi(item.get("doi"))
        provider = _normalize_provider(item.get("provider")).casefold()
        provider_id = _clean_string(item.get("providerId")).casefold()
        title = _normalize_title(item.get("title")).casefold()
        provider_identity = f"{provider}\0{provider_id}" if provider and provider_id else ""
        if not any((doi, provider_identity, title)):
            continue
        if (
            (doi and doi in seen_dois)
            or (provider_identity and provider_identity in seen_provider_ids)
            or (title and title in seen_titles)
        ):
            continue
        if doi:
            seen_dois.add(doi)
        if provider_identity:
            seen_provider_ids.add(provider_identity)
        if title:
            seen_titles.add(title)
        deduplicated.append(item)
        if limit is not None and len(deduplicated) >= limit:
            break
    return deduplicated


def _require_mapping(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("External evidence must be a mapping.")
    return item


def _iter_items(items: Any) -> Iterable[Any]:
    if items is None:
        return []
    if isinstance(items, (list, tuple)):
        return items
    return [items]


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_provider(value: Any) -> str:
    return " ".join(_clean_string(value).split())


def _normalize_title(value: Any) -> str:
    return " ".join(_clean_string(value).split())


def _normalize_authors(value: Any) -> List[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    authors = []
    for author in values:
        normalized = " ".join(_clean_string(author).split())
        if normalized:
            authors.append(normalized)
    return authors


def _normalize_year(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1000 <= year <= 9999 else None


def _normalize_doi(value: Any) -> str:
    doi = _clean_string(value).lower()
    doi = re.sub(r"^doi:\s*", "", doi)
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    return doi.strip()


def _normalize_url(value: Any) -> str:
    raw_url = _clean_string(value)
    if not raw_url:
        return ""

    try:
        parsed = urlsplit(raw_url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        if parsed.username or parsed.password:
            return ""
        host = parsed.hostname.lower()
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
        return urlunsplit((scheme, host, parsed.path or "", query, ""))
    except ValueError:
        return ""
