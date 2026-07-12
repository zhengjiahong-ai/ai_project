"""Web fetch result cache with SHA-256 URL keying and 24h TTL.

Blocked content (grade=blocked) is never cached.
Follows the same pattern as external_search_cache.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class WebFetchCache:
    """Persistent cache for web page fetch results.

    Keyed by SHA-256(url). Entries expire after ttl_seconds (default 24h).
    Blocked content (grade="blocked") is never stored.
    """

    def __init__(
        self,
        path: str,
        ttl_seconds: int = _CACHE_TTL_SECONDS,
        clock: Callable[[], datetime] = _default_clock,
    ):
        self._path = path
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.RLock()

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """Return cached result for url if valid and unexpired, else None."""
        key = _cache_key(url)
        with self._lock:
            entry = self._read_entry(key)
            if entry is None:
                return None
            created = entry.get("createdAt", "")
            try:
                created_dt = datetime.fromisoformat(created)
            except (ValueError, TypeError):
                return None
            age = (self._clock() - created_dt).total_seconds()
            if age > self._ttl:
                return None
            return dict(entry.get("result") or {})

    def put(self, url: str, result: Dict[str, Any]) -> None:
        """Cache a fetch result. Blocked content is not cached."""
        if result.get("grade") == "blocked":
            return
        if result.get("status") != "success":
            return
        key = _cache_key(url)
        with self._lock:
            entry = {
                "key": key,
                "createdAt": self._clock().isoformat(),
                "result": dict(result),
            }
            self._write_entry(key, entry)

    def _read_entry(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return data.get(key)

    def _write_entry(self, key: str, entry: Dict[str, Any]) -> None:
        data: Dict[str, Any] = {}
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        data[key] = entry
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
