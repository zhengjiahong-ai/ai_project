"""Tests for the agent debate orchestrator foundation module."""

import unittest

from services.agent_debate import _cluster_findings, _compute_jaccard_similarity


class TestJaccardSimilarity(unittest.TestCase):
    def test_identical_sets(self):
        result = _compute_jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"})
        self.assertAlmostEqual(result, 1.0)

    def test_disjoint_sets(self):
        result = _compute_jaccard_similarity({"a", "b"}, {"c", "d"})
        self.assertAlmostEqual(result, 0.0)

    def test_partial_overlap(self):
        result = _compute_jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        self.assertAlmostEqual(result, 0.5)

    def test_empty_sets(self):
        result = _compute_jaccard_similarity(set(), set())
        self.assertAlmostEqual(result, 0.0)

    def test_one_empty_set(self):
        result = _compute_jaccard_similarity({"a", "b"}, set())
        self.assertAlmostEqual(result, 0.0)


class TestClusterFindings(unittest.TestCase):
    def _make_finding(self, finding_id, source_ids, keywords):
        return {
            "finding_id": finding_id,
            "sourceIds": source_ids,
            "keywords": keywords,
            "credibility": 0.8,
        }

    def test_identical_findings_cluster_together(self):
        f1 = self._make_finding("f1", ["s1", "s2"], ["covid", "vaccine"])
        f2 = self._make_finding("f2", ["s1", "s2"], ["covid", "vaccine"])
        clusters = _cluster_findings([f1, f2])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    def test_disjoint_findings_separate_clusters(self):
        f1 = self._make_finding("f1", ["s1"], ["covid"])
        f2 = self._make_finding("f2", ["s2"], ["climate"])
        clusters = _cluster_findings([f1, f2])
        self.assertEqual(len(clusters), 2)

    def test_empty_findings(self):
        clusters = _cluster_findings([])
        self.assertEqual(len(clusters), 0)
