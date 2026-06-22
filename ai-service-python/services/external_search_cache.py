import copy
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.external_evidence import normalize_external_evidence


CACHE_SCHEMA_VERSION = "1.0"
DEFAULT_CACHE_TTL_SECONDS = 3600
CACHEABLE_EVIDENCE_FIELDS = (
    "sourceId",
    "sourceType",
    "provider",
    "providerId",
    "title",
    "authors",
    "year",
    "abstract",
    "doi",
    "url",
    "retrievedAt",
    "license",
)

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: Dict[str, threading.RLock] = {}


def normalize_external_search_query(query: Any) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("External search cache query must be a non-empty string.")
    return " ".join(query.split()).casefold()


class ExternalSearchCache:
    def __init__(
        self,
        path: Any,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ):
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)):
            raise ValueError("External search cache TTL must be a positive number.")
        if ttl_seconds <= 0:
            raise ValueError("External search cache TTL must be a positive number.")
        self.path = Path(path)
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._lock = _path_lock(self.path)

    def get(self, provider: str, query: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        normalized_provider = _normalize_provider(provider)
        normalized_query = normalize_external_search_query(query)
        _validate_limit(limit)
        cache_key = _cache_key(normalized_provider, normalized_query)
        with self._lock:
            payload = self._read_payload()
            entry = payload["entries"].get(cache_key)
            if not _valid_entry(entry):
                return None
            if float(self._clock()) - float(entry["createdAt"]) > self.ttl_seconds:
                return None
            if int(entry["fetchedLimit"]) < limit:
                return None
            try:
                results = [
                    normalize_external_evidence(item)
                    for item in copy.deepcopy(entry["results"][:limit])
                ]
            except ValueError:
                return None
        for item in results:
            item["query"] = normalized_query
        return results

    def put(
        self,
        provider: str,
        query: str,
        fetched_limit: int,
        results: Any,
    ) -> None:
        normalized_provider = _normalize_provider(provider)
        normalized_query = normalize_external_search_query(query)
        _validate_limit(fetched_limit)
        safe_results = _sanitize_results(results)
        cache_key = _cache_key(normalized_provider, normalized_query)
        with self._lock:
            payload = self._read_payload()
            payload["entries"][cache_key] = {
                "createdAt": float(self._clock()),
                "fetchedLimit": fetched_limit,
                "results": safe_results,
            }
            self._write_payload(payload)

    def _read_payload(self) -> Dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _empty_payload()
        if not _valid_payload(payload):
            return _empty_payload()
        return payload

    def _write_payload(self, payload: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


def default_external_search_cache_path() -> Path:
    return Path(__file__).resolve().parents[1] / "tmp" / "external_search_cache.json"


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def _empty_payload() -> Dict[str, Any]:
    return {"schemaVersion": CACHE_SCHEMA_VERSION, "entries": {}}


def _valid_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schemaVersion") != CACHE_SCHEMA_VERSION:
        return False
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return False
    return all(isinstance(key, str) and _valid_entry(value) for key, value in entries.items())


def _valid_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    created_at = entry.get("createdAt")
    fetched_limit = entry.get("fetchedLimit")
    results = entry.get("results")
    if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
        return False
    if isinstance(fetched_limit, bool) or not isinstance(fetched_limit, int) or fetched_limit <= 0:
        return False
    if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
        return False
    return all(set(item).issubset(CACHEABLE_EVIDENCE_FIELDS) for item in results)


def _sanitize_results(results: Any) -> List[Dict[str, Any]]:
    if not isinstance(results, list):
        return []
    safe_results = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            normalized = normalize_external_evidence(item)
        except ValueError:
            continue
        safe_results.append(copy.deepcopy({
            field: normalized[field]
            for field in CACHEABLE_EVIDENCE_FIELDS
            if field in normalized
        }))
    return safe_results


def _normalize_provider(provider: Any) -> str:
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("External search cache provider must be a non-empty string.")
    return " ".join(provider.split()).casefold()


def _validate_limit(limit: Any) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("External search cache limit must be a positive integer.")


def _cache_key(provider: str, normalized_query: str) -> str:
    return hashlib.sha256(f"{provider}\0{normalized_query}".encode("utf-8")).hexdigest()
