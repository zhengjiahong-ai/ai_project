"""Tests for the agent debate orchestrator foundation module."""

import unittest
from unittest.mock import patch

from services.agent_debate import (
    DebateOrchestrator,
    _cluster_findings,
    _compute_finding_similarity,
    _compute_jaccard_similarity,
    synthesize_consensus,
)


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


class TestFindingSimilarity(unittest.TestCase):
    """Direct tests for _compute_finding_similarity."""

    def _make_finding(self, finding_id, source_ids, keywords):
        return {
            "finding_id": finding_id,
            "sourceIds": source_ids,
            "keywords": keywords,
            "credibility": 0.8,
        }

    def test_identical_findings(self):
        f1 = self._make_finding("f1", ["s1", "s2"], ["covid", "vaccine"])
        f2 = self._make_finding("f2", ["s1", "s2"], ["covid", "vaccine"])
        sim = _compute_finding_similarity(f1, f2)
        self.assertAlmostEqual(sim, 1.0)

    def test_disjoint_findings(self):
        f1 = self._make_finding("f1", ["s1"], ["covid"])
        f2 = self._make_finding("f2", ["s2"], ["climate"])
        sim = _compute_finding_similarity(f1, f2)
        self.assertAlmostEqual(sim, 0.0)

    def test_partial_source_overlap(self):
        f1 = self._make_finding("f1", ["s1", "s2"], ["result", "data"])
        f2 = self._make_finding("f2", ["s1", "s3"], ["result", "analysis"])
        # source_jaccard: {s1}/{s1,s2,s3}=1/3≈0.333
        # keyword_jaccard: {"result"}/{"result","data","analysis"}=1/3≈0.333
        # avg ≈ 0.333
        sim = _compute_finding_similarity(f1, f2)
        self.assertAlmostEqual(sim, 1/3, places=3)

    def test_missing_keys(self):
        f1 = {"finding_id": "f1"}
        f2 = {"finding_id": "f2"}
        sim = _compute_finding_similarity(f1, f2)
        self.assertAlmostEqual(sim, 0.0)


class TestDebateOrchestrator(unittest.TestCase):
    def setUp(self):
        self.prompt = "What is the effect of X on Y?"
        self.paper_ids = ["paper-1", "paper-2", "paper-3"]

    def _mock_run_agent_graph(self, prompt, paper_ids, **kwargs):
        import hashlib
        seed = hashlib.md5((prompt + str(paper_ids)).encode()).hexdigest()[:8]
        return {
            "status": "succeeded",
            "findings": [
                {"finding_id": f"finding-{seed}-1", "sourceIds": ["paper-1", "paper-2"],
                 "summary": f"[{seed}] Treatment group showed significant improvement",
                 "credibility": 0.82, "keywords": ["treatment", "improvement", "significant"]},
                {"finding_id": f"finding-{seed}-2", "sourceIds": ["paper-3"],
                 "summary": f"[{seed}] Side effects were minimal across groups",
                 "credibility": 0.71, "keywords": ["side", "effects", "minimal"]},
            ],
            "evidence_items": [{"sourceId": "paper-1", "sourceType": "current_paper"}],
            "weighted_evidence": [],
            "cross_paper_insights": {"consensus": [], "complementary": [], "contradictory": [], "gaps": []},
            "resolved_conflicts": [],
            "draft_report": f"[{seed}] Draft report content.",
        }

    @patch("services.agent_debate.run_agent_graph")
    def test_single_agent_no_debate(self, mock_run):
        mock_run.side_effect = self._mock_run_agent_graph
        orchestrator = DebateOrchestrator(
            research_prompt=self.prompt, paper_ids=self.paper_ids,
            constraints=None, num_agents=1, max_debate_rounds=2)
        result = orchestrator.run_debate()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["agent_analyses"]), 1)
        self.assertEqual(len(result["debate_turns"]), 0)

    @patch("services.agent_debate.run_agent_graph")
    def test_three_agents_with_debate(self, mock_run):
        mock_run.side_effect = self._mock_run_agent_graph
        orchestrator = DebateOrchestrator(
            research_prompt=self.prompt, paper_ids=self.paper_ids,
            constraints=None, num_agents=3, max_debate_rounds=2)
        result = orchestrator.run_debate()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["agent_analyses"]), 3)
        self.assertGreater(len(result["debate_turns"]), 0)

    @patch("services.agent_debate.run_agent_graph")
    def test_agents_get_different_temperatures(self, mock_run):
        temperatures_seen = []
        def capture(prompt, paper_ids, temperature=None, **kwargs):
            temperatures_seen.append(temperature)
            return self._mock_run_agent_graph(prompt, paper_ids)
        mock_run.side_effect = capture
        orchestrator = DebateOrchestrator(
            research_prompt=self.prompt, paper_ids=self.paper_ids,
            constraints=None, num_agents=3, max_debate_rounds=2)
        orchestrator.run_debate()
        self.assertEqual(len(temperatures_seen), 3)
        for t in temperatures_seen:
            self.assertIsNotNone(t)
            self.assertGreaterEqual(t, 0.0)
            self.assertLessEqual(t, 1.5)

    @patch("services.agent_debate.run_agent_graph")
    def test_insufficient_papers_fallback(self, mock_run):
        mock_run.side_effect = self._mock_run_agent_graph
        orchestrator = DebateOrchestrator(
            research_prompt=self.prompt, paper_ids=["paper-1"],
            constraints=None, num_agents=3, max_debate_rounds=2)
        result = orchestrator.run_debate()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(mock_run.call_count, 3)

    @patch("services.agent_debate.run_agent_graph")
    def test_agent_failure_graceful_degradation(self, mock_run):
        call_count = [0]
        def fail_second(prompt, paper_ids, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 1:
                raise Exception("Simulated agent failure")
            return self._mock_run_agent_graph(prompt, paper_ids)
        mock_run.side_effect = fail_second
        orchestrator = DebateOrchestrator(
            research_prompt=self.prompt, paper_ids=self.paper_ids,
            constraints=None, num_agents=3, max_debate_rounds=2)
        result = orchestrator.run_debate()
        self.assertEqual(result["status"], "completed")
        successful = [a for a in result["agent_analyses"] if a.get("findings")]
        self.assertEqual(len(successful), 2)

    @patch("services.agent_debate.run_agent_graph")
    def test_jaccard_matrix_computed(self, mock_run):
        mock_run.side_effect = self._mock_run_agent_graph
        orchestrator = DebateOrchestrator(
            research_prompt=self.prompt, paper_ids=self.paper_ids,
            constraints=None, num_agents=3, max_debate_rounds=2)
        result = orchestrator.run_debate()
        matrix = result["jaccard_matrix"]
        self.assertEqual(len(matrix), 3)
        for i in range(3):
            self.assertAlmostEqual(matrix[i][i], 1.0)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(matrix[i][j], matrix[j][i])

    def test_debate_orchestrator_rejects_invalid_num_agents(self):
        with self.assertRaises(ValueError):
            DebateOrchestrator(research_prompt="test", paper_ids=["p1"], num_agents=0)


class TestSynthesizeConsensus(unittest.TestCase):
    def _make_analysis(self, agent_index, findings):
        return {
            "agent_index": agent_index,
            "temperature": 0.5,
            "paper_ids": ["p1"],
            "findings": findings,
            "evidence_items": [],
            "weighted_evidence": [],
            "cross_paper_insights": {},
            "resolved_conflicts": [],
            "draft_report": "",
            "credibility_mean": 0.7,
        }

    def _make_finding(self, finding_id, source_ids, summary, credibility=0.8):
        return {"finding_id": finding_id, "sourceIds": source_ids,
                "summary": summary, "credibility": credibility,
                "keywords": summary.lower().split()}

    def test_all_agents_agree_produces_consensus(self):
        f = self._make_finding("f1", ["s1", "s2"], "treatment effect significant positive result", 0.85)
        analyses = [self._make_analysis(0, [f]), self._make_analysis(1, [f]), self._make_analysis(2, [f])]
        result = synthesize_consensus(analyses)
        self.assertEqual(len(result["consensus_findings"]), 1)
        self.assertEqual(len(result["minority_dissent"]), 0)
        self.assertEqual(len(result["unresolved"]), 0)
        self.assertAlmostEqual(result["consensus_findings"][0]["confidence"], 0.85)

    def test_all_agents_disagree_produces_single_source(self):
        f0 = self._make_finding("f0", ["s1"], "treatment effective for adults")
        f1 = self._make_finding("f1", ["s2"], "climate change accelerating")
        f2 = self._make_finding("f2", ["s3"], "vaccine immunity duration varies")
        analyses = [self._make_analysis(0, [f0]), self._make_analysis(1, [f1]), self._make_analysis(2, [f2])]
        result = synthesize_consensus(analyses)
        self.assertEqual(len(result["consensus_findings"]), 0)
        self.assertEqual(len(result["minority_dissent"]), 3)
        self.assertEqual(len(result["unresolved"]), 0)
        # Confidence = 0.8 * 1/3 ≈ 0.267, which is below 0.4 threshold
        for d in result["minority_dissent"]:
            self.assertIn("Low confidence single-source finding", d["reason"])

    def test_mixed_agreement(self):
        shared = self._make_finding("shared", ["s1", "s2"], "treatment effective significant improvement", 0.85)
        only_a0 = self._make_finding("only0", ["s3"], "side effects rare in elderly", 0.6)
        only_a1 = self._make_finding("only1", ["s4"], "cost effectiveness unclear", 0.5)
        analyses = [
            self._make_analysis(0, [shared, only_a0]),
            self._make_analysis(1, [shared, only_a1]),
            self._make_analysis(2, [shared]),
        ]
        result = synthesize_consensus(analyses)
        self.assertGreaterEqual(len(result["consensus_findings"]), 1)
        # The two single-agent findings should be in minority_dissent
        self.assertGreaterEqual(len(result["minority_dissent"]), 2)

    def test_deterministic_output(self):
        f = self._make_finding("f1", ["s1", "s2"], "consistent finding across agents", 0.8)
        analyses = [self._make_analysis(i, [f]) for i in range(3)]
        result1 = synthesize_consensus(analyses)
        result2 = synthesize_consensus(analyses)
        self.assertEqual(result1["consensus_findings"], result2["consensus_findings"])
        self.assertEqual(result1["minority_dissent"], result2["minority_dissent"])
        self.assertEqual(result1["unresolved"], result2["unresolved"])
