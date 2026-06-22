import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _evidence(identifier="work-1", query="Sensitive Query"):
    return {
        "sourceId": f"external-provider-{identifier}",
        "sourceType": "external_academic",
        "provider": "Crossref",
        "providerId": identifier,
        "title": "External Evidence",
        "authors": ["Ada Lovelace"],
        "year": 2024,
        "abstract": "Bounded abstract.",
        "doi": "",
        "url": "https://example.org/evidence",
        "retrievedAt": "2026-06-22T00:00:00Z",
        "query": query,
        "license": "",
        "authorization": "Bearer secret-token",
    }


class ExternalSearchCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "external-search-cache.json"
        self.now = [1000.0]

    def tearDown(self):
        self.temp_dir.cleanup()

    def _cache(self, ttl_seconds=3600):
        from services.external_search_cache import ExternalSearchCache

        return ExternalSearchCache(
            path=self.path,
            ttl_seconds=ttl_seconds,
            clock=lambda: self.now[0],
        )

    def test_normalized_query_hits_across_instances_without_persisting_sensitive_data(self):
        cache = self._cache()
        cache.put("crossref", "  Retrieval   SYSTEMS  ", 5, [_evidence()])

        hit = self._cache().get("CROSSREF", "retrieval systems", 3)

        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["query"], "retrieval systems")
        self.assertNotIn("authorization", hit[0])
        persisted = self.path.read_text(encoding="utf-8")
        self.assertNotIn("Sensitive Query", persisted)
        self.assertNotIn("Retrieval", persisted)
        self.assertNotIn("secret-token", persisted)
        payload = json.loads(persisted)
        self.assertEqual(payload["schemaVersion"], "1.0")
        self.assertEqual(len(payload["entries"]), 1)

    def test_provider_and_fetched_limit_control_cache_hits(self):
        cache = self._cache()
        cache.put("crossref", "query", 5, [_evidence()])

        self.assertIsNotNone(cache.get("crossref", "query", 5))
        self.assertIsNone(cache.get("crossref", "query", 6))
        self.assertIsNone(cache.get("semantic_scholar", "query", 5))

    def test_empty_results_are_cached_when_fetched_limit_is_sufficient(self):
        cache = self._cache()
        cache.put("crossref", "query", 5, [])

        self.assertEqual(cache.get("crossref", "query", 5), [])
        self.assertIsNone(cache.get("crossref", "query", 6))

    def test_expired_entries_are_cache_misses(self):
        cache = self._cache(ttl_seconds=60)
        cache.put("crossref", "query", 5, [_evidence()])
        self.now[0] += 61

        self.assertIsNone(cache.get("crossref", "query", 5))

    def test_missing_corrupt_and_invalid_schema_cache_fall_back_to_empty(self):
        self.assertIsNone(self._cache().get("crossref", "query", 5))

        invalid_payloads = [
            "not-json",
            json.dumps([]),
            json.dumps({"schemaVersion": "9.9", "entries": {}}),
            json.dumps({"schemaVersion": "1.0", "entries": []}),
            json.dumps({"schemaVersion": "1.0", "entries": {"bad": []}}),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload[:20]):
                self.path.write_text(payload, encoding="utf-8")
                self.assertIsNone(self._cache().get("crossref", "query", 5))

    def test_put_uses_atomic_replace_and_overwrites_corrupt_cache(self):
        import services.external_search_cache as cache_module

        self.path.write_text("corrupt", encoding="utf-8")
        cache = self._cache()
        real_replace = cache_module.os.replace
        calls = []

        def recording_replace(source, destination):
            calls.append((Path(source), Path(destination)))
            return real_replace(source, destination)

        with patch.object(cache_module.os, "replace", side_effect=recording_replace):
            cache.put("crossref", "query", 5, [_evidence()])

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], self.path)
        self.assertFalse(calls[0][0].exists())
        self.assertIsNotNone(cache.get("crossref", "query", 5))

    def test_structurally_valid_but_invalid_evidence_is_a_cache_miss(self):
        cache = self._cache()
        cache.put("crossref", "query", 5, [_evidence()])
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        entry = next(iter(payload["entries"].values()))
        entry["results"][0].pop("provider")
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        self.assertIsNone(cache.get("crossref", "query", 5))


if __name__ == "__main__":
    unittest.main()
