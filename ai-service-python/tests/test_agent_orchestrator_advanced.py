"""Unit tests for run_advanced_analysis in agent_orchestrator — covers
integration with adversarial review, hypothesis engine, conflict adjudication,
meta-analysis, and cross-lingual search."""

from services.agent_advanced_analysis import run_advanced_analysis, _extract_study_items


class TestExtractStudyItems:
    def test_extracts_from_evidence_with_effect_size(self):
        evidence = [
            {"sourceId": "s1", "metadata": {"effectSize": 0.42, "standardError": 0.12, "sampleSize": 120}},
            {"sourceId": "s2", "effectSize": 0.35},
        ]
        studies = _extract_study_items(evidence, [])
        assert len(studies) == 2
        assert studies[0]["effectSize"] == 0.42
        assert studies[0]["standardError"] == 0.12
        assert studies[0]["sampleSize"] == 120
        assert studies[1]["effectSize"] == 0.35

    def test_extracts_from_findings(self):
        findings = [
            {"id": "f1", "effectSize": 0.55, "summary": "Finding 1"},
        ]
        studies = _extract_study_items([], findings)
        assert len(studies) == 1
        assert studies[0]["effectSize"] == 0.55

    def test_ignores_items_without_effect_size(self):
        evidence = [
            {"sourceId": "s1", "text": "no effect size here"},
        ]
        studies = _extract_study_items(evidence, [])
        assert len(studies) == 0

    def test_combines_evidence_and_findings(self):
        evidence = [{"sourceId": "s1", "effectSize": 0.3}]
        findings = [{"id": "f1", "effectSize": 0.7}]
        studies = _extract_study_items(evidence, findings)
        assert len(studies) == 2


class TestRunAdvancedAnalysis:
    def test_empty_inputs_returns_empty_dict(self):
        result = run_advanced_analysis(
            prompt="",
            paper_ids=[],
            evidence_items=[],
            findings=[],
            conflicts=[],
            open_questions=[],
        )
        assert result == {}

    def test_with_findings_runs_adversarial_review(self):
        findings = [{"id": "f1", "summary": "Test finding."}]
        evidence = [{"sourceId": "s1", "text": "Test evidence."}]
        result = run_advanced_analysis(
            prompt="Test question",
            paper_ids=["paper-1"],
            evidence_items=evidence,
            findings=findings,
            conflicts=[],
            open_questions=[],
        )
        assert isinstance(result, dict)
        # adversarial review should be present when findings exist
        assert "adversarialReview" in result

    def test_with_findings_runs_hypothesis_engine(self):
        findings = [{"id": "f1", "summary": "Test finding."}]
        result = run_advanced_analysis(
            prompt="Test question",
            paper_ids=["paper-1"],
            evidence_items=[{"sourceId": "s1"}],
            findings=findings,
            conflicts=[],
            open_questions=["gap 1"],
        )
        assert isinstance(result, dict)
        assert "hypotheses" in result

    def test_with_conflicts_attempts_adjudication(self):
        """Conflict adjudication runs but may fail gracefully with incomplete inputs."""
        conflicts = [
            {
                "id": "conflict-1",
                "conflictType": "numeric_mismatch",
                "claim": "Effect sizes differ across studies.",
                "summary": "Two studies report different effect sizes.",
                "papers": ["paper-1", "paper-2"],
            }
        ]
        evidence = [
            {"sourceId": "s1", "pdfId": "paper-1", "text": "Effect size 0.5"},
            {"sourceId": "s2", "pdfId": "paper-2", "text": "Effect size 0.3"},
        ]
        result = run_advanced_analysis(
            prompt="Compare effect sizes",
            paper_ids=["paper-1", "paper-2"],
            evidence_items=evidence,
            findings=[{"id": "f1", "summary": "Test"}],
            conflicts=conflicts,
            open_questions=[],
        )
        assert isinstance(result, dict)
        # Adversarial review and hypotheses should still succeed
        assert "adversarialReview" in result
        assert "hypotheses" in result

    def test_no_major_conflict_skips_adjudication(self):
        conflicts = [{"id": "no-conflict", "conflictType": "no-major-conflict", "claim": "ok"}]
        result = run_advanced_analysis(
            prompt="Test",
            paper_ids=["paper-1"],
            evidence_items=[{"sourceId": "s1"}],
            findings=[{"id": "f1", "summary": "Test"}],
            conflicts=conflicts,
            open_questions=[],
        )
        assert "conflictAdjudications" not in result

    def test_with_study_evidence_runs_meta_analysis(self):
        evidence = [
            {"sourceId": "s1", "effectSize": 0.42, "standardError": 0.12, "sampleSize": 100, "title": "Study A", "year": 2020},
            {"sourceId": "s2", "effectSize": 0.38, "standardError": 0.10, "sampleSize": 200, "title": "Study B", "year": 2021},
        ]
        result = run_advanced_analysis(
            prompt="Meta analysis test",
            paper_ids=["p1"],
            evidence_items=evidence,
            findings=[],
            conflicts=[],
            open_questions=[],
        )
        assert isinstance(result, dict)
        assert "metaAnalysis" in result

    def test_sparse_evidence_attempts_cross_lingual(self):
        """Cross-lingual search runs but may fail gracefully without configured providers."""
        result = run_advanced_analysis(
            prompt="Test cross-lingual search",
            paper_ids=["paper-1"],
            evidence_items=[{"sourceId": "s1"}],  # Only 1 item = sparse
            findings=[{"id": "f1", "summary": "Test"}],
            conflicts=[],
            open_questions=[],
        )
        assert isinstance(result, dict)
        # At minimum the in-process analyses should succeed
        assert "adversarialReview" in result
        assert "hypotheses" in result

    def test_handles_exceptions_gracefully(self):
        """All analysis steps should catch exceptions and not propagate."""
        result = run_advanced_analysis(
            prompt="Test",
            paper_ids=[],
            evidence_items=[{"malformed": True}],
            findings=[{"broken": True}],
            conflicts=[{"bad": True, "conflictType": "unknown"}],
            open_questions=["test"],
        )
        # Should still return a dict without raising
        assert isinstance(result, dict)
