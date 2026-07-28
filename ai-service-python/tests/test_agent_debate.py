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
from services.agent_project_service import (
    create_debate_run,
    get_debate_result,
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


class TestDebateAPI(unittest.TestCase):
    """Tests for debate API endpoint and service layer."""

    def setUp(self):
        self.project_id = "test-project-debate-api"

    @patch("services.agent_debate.DebateOrchestrator.run_debate")
    @patch("services.agent_project_service.get_agent_project")
    def test_create_debate_run_success(self, mock_get_project, mock_run_debate):
        """create_debate_run returns debate result when project exists."""
        mock_get_project.return_value = {
            "id": self.project_id,
            "title": "Test Project",
            "paperIds": ["paper-1", "paper-2"],
        }
        mock_run_debate.return_value = {
            "run_id": "debate-run-1",
            "status": "completed",
            "agent_analyses": [],
            "debate_turns": [],
            "consensus_findings": [],
            "minority_dissent": [],
            "unresolved": [],
            "jaccard_matrix": [],
            "rounds": 0,
            "duration_seconds": 1.5,
            "research_prompt": "test",
            "paper_ids": ["paper-1", "paper-2"],
        }

        result = create_debate_run(
            self.project_id,
            research_prompt="test prompt",
            paper_ids=["paper-1", "paper-2"],
            num_agents=3,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["run_id"], "debate-run-1")
        mock_run_debate.assert_called_once()

    @patch("services.agent_project_service.get_agent_project")
    def test_create_debate_run_project_not_found(self, mock_get_project):
        """Raises ValueError when project does not exist."""
        mock_get_project.return_value = None

        with self.assertRaises(ValueError):
            create_debate_run(
                "nonexistent-project",
                research_prompt="test",
                paper_ids=["paper-1"],
            )

    @patch("services.agent_debate.DebateOrchestrator.run_debate")
    @patch("services.agent_project_service.get_agent_project")
    def test_create_debate_run_default_num_agents(self, mock_get_project, mock_run_debate):
        """Default num_agents=3 when not specified."""
        mock_get_project.return_value = {
            "id": self.project_id,
            "title": "Test",
            "paperIds": ["p1"],
        }
        mock_run_debate.return_value = {
            "run_id": "r1", "status": "completed",
            "agent_analyses": [], "debate_turns": [],
            "consensus_findings": [], "minority_dissent": [],
            "unresolved": [], "jaccard_matrix": [],
            "rounds": 0, "duration_seconds": 0.5,
            "research_prompt": "test", "paper_ids": ["p1"],
        }

        result = create_debate_run(
            self.project_id,
            research_prompt="test",
            paper_ids=["p1"],
        )
        self.assertEqual(result["status"], "completed")


class TestLLMDebateReview(unittest.TestCase):
    """24-1: LLM-driven debate rebuttal tests."""

    def setUp(self):
        self.agent_findings = [
            {"finding_id": "f1", "summary": "Method X outperforms Y on benchmark Z", "sourceIds": ["src-1"]},
            {"finding_id": "f2", "summary": "Dataset size is a limiting factor", "sourceIds": ["src-2"]},
        ]
        self.other_summary = (
            "[Agent 1] finding_id=g1: Method X fails on edge cases. "
            "[Agent 1] finding_id=g2: Data augmentation helps mitigate dataset size issues."
        )

    def test_llm_debate_review_returns_none_on_empty_input(self):
        """Returns None when inputs are empty."""
        from services.agent_debate import _llm_debate_review
        result = _llm_debate_review([], "")
        self.assertIsNone(result)
        result = _llm_debate_review(self.agent_findings, "")
        self.assertIsNone(result)

    def test_llm_debate_review_falls_back_on_llm_unavailable(self):
        """Returns None when LLM is unavailable, triggering deterministic fallback."""
        from unittest.mock import patch
        from services.agent_debate import _llm_debate_review
        with patch("llm.client.get_translation_llm", side_effect=ValueError("no key")):
            result = _llm_debate_review(self.agent_findings, self.other_summary)
        self.assertIsNone(result)

    def test_llm_debate_review_parses_valid_json_response(self):
        """Correctly parses a valid JSON response from the LLM."""
        from unittest.mock import MagicMock, patch
        from services.agent_debate import _llm_debate_review
        mock_llm = MagicMock()
        mock_llm._call.return_value = (
            '[{"finding_id": "f1", "type": "rebut", "reason": "Agent 1 finds X fails"},'
            ' {"finding_id": "f2", "type": "support", "reason": "Data augmentation aligns"}]'
        )
        with patch("llm.client.get_translation_llm", return_value=mock_llm):
            result = _llm_debate_review(self.agent_findings, self.other_summary)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["type"], "rebut")
        self.assertEqual(result[1]["type"], "support")

    def test_llm_debate_review_tolerates_markdown_fence(self):
        """Strips markdown code fences from the LLM response."""
        from unittest.mock import MagicMock, patch
        from services.agent_debate import _llm_debate_review
        mock_llm = MagicMock()
        mock_llm._call.return_value = (
            '```json\n[{"finding_id": "f1", "type": "unrelated", "reason": "No connection"}]\n```'
        )
        with patch("llm.client.get_translation_llm", return_value=mock_llm):
            result = _llm_debate_review(self.agent_findings, self.other_summary)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "unrelated")

    def test_run_single_debate_round_uses_llm_when_available(self):
        """Debate round uses LLM results when _llm_debate_review returns data."""
        from unittest.mock import patch
        from services.agent_debate import DebateOrchestrator
        llm_result = [
            {"finding_id": "f1", "type": "rebut", "reason": "Edge case failure"},
            {"finding_id": "f2", "type": "support", "reason": "Data augmentation aligns"},
        ]
        with patch("services.agent_debate._llm_debate_review", return_value=llm_result):
            orchestrator = DebateOrchestrator(
                research_prompt="test", paper_ids=["p1"], num_agents=2, max_debate_rounds=1
            )
            analyses = [
                {"agent_index": 0, "findings": [
                    {"finding_id": "f1", "summary": "X > Y", "sourceIds": ["s1"]},
                    {"finding_id": "f2", "summary": "data limit", "sourceIds": ["s2"]},
                ]},
                {"agent_index": 1, "findings": [
                    {"finding_id": "g1", "summary": "X fails", "sourceIds": ["s3"]},
                ]},
            ]
            turns = orchestrator._run_single_debate_round(0, analyses)
        self.assertEqual(len(turns), 2)
        agent0_turn = turns[0]
        self.assertTrue(len(agent0_turn["rebuttals"]) > 0 or len(agent0_turn["supplements"]) > 0)


class TestDebatePersistence(unittest.TestCase):
    """24-2: Debate result persistence tests."""

    def setUp(self):
        import tempfile
        from services.agent_state_repository import AgentStateRepository
        self.tmpdir = tempfile.mkdtemp()
        db_path = f"{self.tmpdir}/test_debate.db"
        self.repo = AgentStateRepository(db_path)
        self.repo.initialize()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_retrieve_debate_result(self):
        """Debate result can be saved and retrieved from SQLite."""
        run_id = "debate-run-1"
        project_id = "proj-1"
        result = {
            "run_id": run_id, "status": "completed", "rounds": 2,
            "consensus_findings": [{"finding_id": "f1", "summary": "Test finding"}],
            "agent_analyses": [], "debate_turns": [], "minority_dissent": [],
            "unresolved": [], "jaccard_matrix": [], "duration_seconds": 1.5,
            "research_prompt": "test", "paper_ids": ["p1"],
        }
        self.repo.save_debate_result(run_id, project_id, result)
        retrieved = self.repo.get_debate_result(run_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["run_id"], run_id)
        self.assertEqual(retrieved["status"], "completed")
        self.assertEqual(len(retrieved["consensus_findings"]), 1)

    def test_get_nonexistent_debate_result_returns_none(self):
        """Returns None for a non-existent debate run_id."""
        result = self.repo.get_debate_result("nonexistent-run")
        self.assertIsNone(result)

    def test_list_debate_results_by_project(self):
        """Can list all debate results for a project, newest first."""
        self.repo.save_debate_result("run-1", "proj-a", {"run_id": "run-1", "status": "completed"})
        self.repo.save_debate_result("run-2", "proj-a", {"run_id": "run-2", "status": "completed"})
        self.repo.save_debate_result("run-3", "proj-b", {"run_id": "run-3", "status": "completed"})

        proj_a_results = self.repo.list_debate_results("proj-a")
        self.assertEqual(len(proj_a_results), 2)
        # Newest first
        self.assertIn("run_id", proj_a_results[0])

        proj_b_results = self.repo.list_debate_results("proj-b")
        self.assertEqual(len(proj_b_results), 1)
