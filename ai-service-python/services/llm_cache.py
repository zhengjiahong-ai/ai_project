"""
LLM response cache (15-2).

Provides exact-match (SHA-256) caching of LLM responses backed by SQLite.
Semantic / embedding-based matching is reserved for future activation via
``PIXIU_LLM_CACHE_MODE=semantic``.

Usage::

    from services.llm_cache import LLMCache

    cache = LLMCache()
    cached = cache.get(model, temperature, system_prompt, user_prompt)
    if cached:
        return cached
    response = llm._call(prompt)
    cache.put(model, temperature, system_prompt, user_prompt, response)
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
from typing import Optional


def _cache_db_path() -> str:
    return os.environ.get(
        "PIXIU_LLM_CACHE_PATH",
        os.path.join(os.path.dirname(__file__), "..", "data", "llm_cache.sqlite3"),
    )


def _cache_ttl_seconds() -> int:
    try:
        return int(os.environ.get("PIXIU_LLM_CACHE_TTL_MINUTES", "60")) * 60
    except (TypeError, ValueError):
        return 3600


def _cache_mode() -> str:
    return os.environ.get("PIXIU_LLM_CACHE_MODE", "exact").strip().lower()


def _build_cache_key(
    model: str,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """SHA-256 of (model, temp, system, user) → stable cache key."""
    payload = f"{model}|{temperature:.3f}|{system_prompt}|{user_prompt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMCache:
    """Thread-safe, TTL-aware LLM response cache."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or _cache_db_path()
        self._ttl = _cache_ttl_seconds()
        self._lock = threading.Lock()
        self._init_db()

    # ── public API ──────────────────────────────────────────────────────

    def get(
        self,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[str]:
        """Return cached response or None if miss / expired."""
        if _cache_mode() not in ("exact", "semantic"):
            return None
        key = _build_cache_key(model, temperature, system_prompt, user_prompt)
        with self._lock:
            row = self._db.execute(
                "SELECT response, created_at FROM llm_cache WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        response, created_at = row
        if time.time() - float(created_at) > self._ttl:
            self._evict(key)
            return None
        return response

    def put(
        self,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
        response: str,
    ) -> None:
        """Store a response in the cache."""
        if _cache_mode() not in ("exact", "semantic"):
            return
        key = _build_cache_key(model, temperature, system_prompt, user_prompt)
        now = time.time()
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO llm_cache (key, model, temperature, system_prompt_hash, user_prompt_hash, response, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    model,
                    temperature,
                    hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
                    hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                    response,
                    now,
                ),
            )
            self._db.commit()

    # ── maintenance ─────────────────────────────────────────────────────

    def _evict(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
            self._db.commit()

    def evict_expired(self) -> int:
        """Remove expired entries; return count of removed rows."""
        cutoff = time.time() - self._ttl
        with self._lock:
            cur = self._db.execute(
                "DELETE FROM llm_cache WHERE created_at < ?", (cutoff,)
            )
            self._db.commit()
            return cur.rowcount

    def count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM llm_cache").fetchone()
        return int(row[0]) if row else 0

    # ── internal ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        if self._db_path != ":memory:":
            os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            "  key TEXT PRIMARY KEY,"
            "  model TEXT NOT NULL,"
            "  temperature REAL NOT NULL,"
            "  system_prompt_hash TEXT NOT NULL,"
            "  user_prompt_hash TEXT NOT NULL,"
            "  response TEXT NOT NULL,"
            "  created_at REAL NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_cache_created "
            "ON llm_cache(created_at)"
        )
        self._db.commit()


# ── module-level singleton ───────────────────────────────────────────────

_cache: Optional[LLMCache] = None


def get_llm_cache() -> LLMCache:
    global _cache
    if _cache is None:
        _cache = LLMCache()
    return _cache
