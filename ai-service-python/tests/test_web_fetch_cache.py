import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


class WebFetchCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._cache_path = os.path.join(self._tmpdir, "cache.json")

    def tearDown(self):
        try:
            os.remove(self._cache_path)
        except FileNotFoundError:
            pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    def test_module_imports(self):
        from services import web_fetch_cache
        self.assertIsNotNone(web_fetch_cache)

    def test_put_and_get(self):
        from services.web_fetch_cache import WebFetchCache

        cache = WebFetchCache(self._cache_path)
        url = "https://www.nature.com/article"
        result = {"status": "success", "content": "test content", "grade": "safe"}
        cache.put(url, result)

        cached = cache.get(url)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["content"], "test content")

    def test_cache_miss(self):
        from services.web_fetch_cache import WebFetchCache

        cache = WebFetchCache(self._cache_path)
        self.assertIsNone(cache.get("https://never-cached.example.com"))

    def test_blocked_content_not_cached(self):
        from services.web_fetch_cache import WebFetchCache

        cache = WebFetchCache(self._cache_path)
        url = "https://evil.example.com"
        result = {"status": "success", "content": "", "grade": "blocked"}
        cache.put(url, result)

        self.assertIsNone(cache.get(url))

    def test_expired_entry_not_returned(self):
        from services.web_fetch_cache import WebFetchCache

        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        clock = _FakeClock(now)
        cache = WebFetchCache(self._cache_path, ttl_seconds=3600, clock=clock.now)

        url = "https://www.nature.com/article"
        cache.put(url, {"status": "success", "content": "old", "grade": "safe"})

        # Advance past TTL
        clock.advance(hours=2)
        self.assertIsNone(cache.get(url))

    def test_valid_entry_returned_within_ttl(self):
        from services.web_fetch_cache import WebFetchCache

        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        clock = _FakeClock(now)
        cache = WebFetchCache(self._cache_path, ttl_seconds=3600, clock=clock.now)

        url = "https://www.nature.com/article"
        cache.put(url, {"status": "success", "content": "valid", "grade": "safe"})

        clock.advance(minutes=30)
        cached = cache.get(url)
        self.assertIsNotNone(cached)

    def test_sha256_key_is_deterministic(self):
        from services.web_fetch_cache import _cache_key

        k1 = _cache_key("https://example.com/page")
        k2 = _cache_key("https://example.com/page")
        k3 = _cache_key("https://example.com/other")
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)
        self.assertEqual(len(k1), 64)  # SHA-256 hex = 64 chars


class _FakeClock:
    def __init__(self, start: datetime):
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, *, hours: float = 0, minutes: float = 0) -> None:
        self._now += timedelta(hours=hours, minutes=minutes)


if __name__ == "__main__":
    unittest.main()
