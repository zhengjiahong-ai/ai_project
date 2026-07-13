import unittest

from services.evidence_service import compact_evidence_for_response, normalize_evidence_items
from services.external_evidence import (
    build_external_source_id,
    normalize_external_evidence,
    normalize_external_evidence_items,
)


class ExternalEvidenceTests(unittest.TestCase):
    def test_normalizes_complete_external_evidence(self):
        item = normalize_external_evidence({
            "provider": " Crossref ",
            "providerId": " work-1 ",
            "title": "  Retrieval   Augmented Generation  ",
            "authors": [" Ada Lovelace ", "", "Alan Turing"],
            "year": "2024",
            "abstract": " Evidence summary. ",
            "doi": " DOI:10.1000/ABC ",
            "url": "HTTPS://Example.org/Paper?b=2&a=1#results",
            "retrievedAt": " 2026-06-21T12:00:00Z ",
            "query": " retrieval evaluation ",
            "license": " cc-by ",
        })

        self.assertEqual(item["sourceType"], "external_academic")
        self.assertEqual(item["provider"], "Crossref")
        self.assertEqual(item["providerId"], "work-1")
        self.assertEqual(item["title"], "Retrieval Augmented Generation")
        self.assertEqual(item["authors"], ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(item["year"], 2024)
        self.assertEqual(item["abstract"], "Evidence summary.")
        self.assertEqual(item["doi"], "10.1000/abc")
        self.assertEqual(item["url"], "https://example.org/Paper?a=1&b=2")
        self.assertEqual(item["retrievedAt"], "2026-06-21T12:00:00Z")
        self.assertEqual(item["query"], "retrieval evaluation")
        self.assertEqual(item["license"], "cc-by")
        self.assertRegex(item["sourceId"], r"^external-doi-[0-9a-f]{24}$")

    def test_missing_optional_fields_have_stable_defaults(self):
        item = normalize_external_evidence({
            "provider": "Crossref",
            "providerId": "work-2",
        })

        self.assertEqual(item, {
            "sourceId": build_external_source_id({"provider": "Crossref", "providerId": "work-2"}),
            "sourceType": "external_academic",
            "provider": "Crossref",
            "providerId": "work-2",
            "title": "",
            "authors": [],
            "year": None,
            "abstract": "",
            "doi": "",
            "url": "",
            "retrievedAt": "",
            "query": "",
            "license": "",
            "provenance": {
                "discoveryPath": "external_academic",
                "searchQuery": "",
                "searchIteration": None,
                "sourceUrl": "",
                "retrievalTimestamp": "",
            },
        })

    def test_doi_has_priority_and_deduplicates_across_providers(self):
        first = build_external_source_id({
            "provider": "Crossref",
            "providerId": "crossref-id",
            "doi": "https://doi.org/10.1000/ABC",
            "url": "https://example.org/one",
        })
        second = build_external_source_id({
            "provider": "Semantic Scholar",
            "providerId": "s2-id",
            "doi": "10.1000/abc",
            "url": "https://example.org/two",
        })

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("external-doi-"))

    def test_provider_id_is_scoped_by_normalized_provider(self):
        first = build_external_source_id({"provider": " Crossref ", "providerId": "Work-1"})
        same = build_external_source_id({"provider": "crossref", "providerId": "Work-1"})
        other = build_external_source_id({"provider": "Semantic Scholar", "providerId": "Work-1"})

        self.assertEqual(first, same)
        self.assertNotEqual(first, other)
        self.assertTrue(first.startswith("external-provider-"))

    def test_url_identity_is_canonical_and_ignores_fragment(self):
        first = build_external_source_id({
            "provider": "Crossref",
            "url": "HTTPS://Example.org/paper?b=2&a=1#section",
        })
        second = build_external_source_id({
            "provider": "Crossref",
            "url": "https://example.org/paper?a=1&b=2",
        })

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("external-url-"))

    def test_title_fingerprint_is_last_stable_fallback(self):
        first = build_external_source_id({
            "provider": " Crossref ",
            "title": " Evidence   Retrieval ",
            "year": "2025",
        })
        second = build_external_source_id({
            "provider": "crossref",
            "title": "evidence retrieval",
            "year": 2025,
            "sourceId": "untrusted-id",
        })

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("external-title-"))

    def test_rejects_missing_provider_or_identity(self):
        with self.assertRaisesRegex(ValueError, "provider"):
            normalize_external_evidence({"doi": "10.1000/test"})

        with self.assertRaisesRegex(ValueError, "identity"):
            normalize_external_evidence({"provider": "Crossref"})

    def test_batch_normalization_honors_limit(self):
        items = normalize_external_evidence_items(
            [
                {"provider": "Crossref", "providerId": "work-1"},
                {"provider": "Crossref", "providerId": "work-2"},
            ],
            limit=1,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["providerId"], "work-1")

    def test_deduplicates_by_doi_provider_id_and_normalized_title_in_first_seen_order(self):
        from services.external_evidence import deduplicate_external_evidence

        items = [
            normalize_external_evidence({
                "provider": "Crossref", "providerId": "work-1",
                "doi": "10.1000/ONE", "title": "First Paper",
            }),
            normalize_external_evidence({
                "provider": "Other", "providerId": "other-1",
                "doi": "https://doi.org/10.1000/one", "title": "Different Title",
            }),
            normalize_external_evidence({
                "provider": "Crossref", "providerId": "WORK-1",
                "title": "Provider Duplicate",
            }),
            normalize_external_evidence({
                "provider": "Crossref", "providerId": "work-3",
                "title": "  First   PAPER ",
            }),
            normalize_external_evidence({
                "provider": "Crossref", "providerId": "work-4",
                "title": "Unique Paper",
            }),
        ]

        deduplicated = deduplicate_external_evidence(items)

        self.assertEqual(
            [item["providerId"] for item in deduplicated],
            ["work-1", "work-4"],
        )

    def test_deduplication_rejects_invalid_items_and_honors_limit(self):
        from services.external_evidence import deduplicate_external_evidence

        valid = normalize_external_evidence({
            "provider": "Crossref", "providerId": "work-1", "title": "Paper",
        })

        self.assertEqual(deduplicate_external_evidence([None, {}, valid], limit=1), [valid])
        self.assertEqual(deduplicate_external_evidence([valid], limit=0), [])

    def test_existing_evidence_pipeline_preserves_external_fields(self):
        external = normalize_external_evidence({
            "provider": "Crossref",
            "providerId": "work-3",
            "title": "External Paper",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "abstract": "External abstract evidence.",
            "doi": "10.1000/external",
            "url": "https://example.org/external",
            "retrievedAt": "2026-06-21T12:00:00Z",
            "query": "external evidence",
            "license": "cc-by",
        })

        normalized = normalize_evidence_items([external])
        compacted = compact_evidence_for_response([external])

        self.assertEqual(normalized[0]["sourceType"], "external_academic")
        self.assertEqual(normalized[0]["text"], "External abstract evidence.")
        for field in (
            "provider", "providerId", "title", "authors", "year", "abstract",
            "doi", "url", "retrievedAt", "query", "license",
        ):
            self.assertEqual(normalized[0][field], external[field])
            self.assertEqual(compacted[0][field], external[field])

    # ---- P6-19: provenance field ----

    def test_provenance_field_populated_from_existing_fields(self):
        """normalize_external_evidence constructs provenance from existing fields."""
        item = normalize_external_evidence({
            "provider": "Semantic Scholar",
            "providerId": "paper-1",
            "title": "Test Paper",
            "url": "https://example.org/paper",
            "retrievedAt": "2026-07-13T10:00:00Z",
            "query": "deep learning evaluation",
        })

        self.assertIn("provenance", item)
        provenance = item["provenance"]
        self.assertIsInstance(provenance, dict)
        self.assertEqual(provenance["discoveryPath"], "external_academic")
        self.assertEqual(provenance["searchQuery"], "deep learning evaluation")
        self.assertIsNone(provenance["searchIteration"])
        self.assertEqual(provenance["sourceUrl"], "https://example.org/paper")
        self.assertEqual(provenance["retrievalTimestamp"], "2026-07-13T10:00:00Z")

    def test_provenance_web_search_source_type(self):
        """Web search evidence gets discoveryPath='web_search'."""
        item = normalize_external_evidence(
            {
                "provider": "Brave Search",
                "providerId": "https://example.com/result",
                "title": "Web Result",
                "url": "https://example.com/result",
                "retrievedAt": "2026-07-13T10:00:00Z",
                "query": "research topic",
            },
            source_type="web_search",
        )

        self.assertEqual(item["provenance"]["discoveryPath"], "web_search")

    def test_provenance_missing_optional_fields_has_stable_defaults(self):
        """Provenance fields default to empty strings when source data is missing."""
        item = normalize_external_evidence({
            "provider": "Crossref",
            "providerId": "work-minimal",
            "title": "Minimal Paper",
        })

        provenance = item["provenance"]
        self.assertEqual(provenance["discoveryPath"], "external_academic")
        self.assertEqual(provenance["searchQuery"], "")
        self.assertIsNone(provenance["searchIteration"])
        self.assertEqual(provenance["sourceUrl"], "")
        self.assertEqual(provenance["retrievalTimestamp"], "")

    def test_provenance_propagates_through_evidence_pipeline(self):
        """Provenance field is preserved through normalize_evidence_items and compact_evidence_for_response."""
        external = normalize_external_evidence({
            "provider": "Crossref",
            "providerId": "work-provenance",
            "title": "Provenance Paper",
            "abstract": "Provenance paper abstract.",
            "url": "https://example.org/provenance",
            "retrievedAt": "2026-07-13T10:00:00Z",
            "query": "provenance query",
        })

        normalized = normalize_evidence_items([external])
        compacted = compact_evidence_for_response([external])

        self.assertIn("provenance", normalized[0])
        self.assertEqual(normalized[0]["provenance"]["discoveryPath"], "external_academic")
        self.assertIn("provenance", compacted[0])
        self.assertEqual(compacted[0]["provenance"]["searchQuery"], "provenance query")

    def test_provenance_null_backward_compatible(self):
        """Evidence items without provenance field are handled gracefully (null-safe)."""
        evidence_without_provenance = {
            "sourceId": "external-doi-abc123",
            "sourceType": "external_academic",
            "provider": "Crossref",
            "providerId": "old-item",
            "title": "Old Paper",
            "authors": [],
            "year": None,
            "abstract": "Old evidence abstract text for backward compatibility.",
            "doi": "",
            "url": "",
            "retrievedAt": "",
            "query": "",
            "license": "",
        }

        # normalize_evidence_items should accept items without provenance
        normalized = normalize_evidence_items([evidence_without_provenance])
        self.assertEqual(len(normalized), 1)
        # Old items get provenance=None (not set by normalize_evidence_items)
        self.assertIsNone(normalized[0].get("provenance"))


if __name__ == "__main__":
    unittest.main()
