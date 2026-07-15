"""Unit tests for paper_writer — covers draft generation with and without inputs."""

import pytest
from services.paper_writer import generate_paper_draft


class TestPaperDraftGeneration:
    def test_empty_question_returns_error(self):
        result = generate_paper_draft("")
        assert result["status"] == "error"
        assert result["error"]

    def test_whitespace_question_returns_error(self):
        result = generate_paper_draft("   ")
        assert result["status"] == "error"

    def test_minimal_question_generates_draft(self):
        result = generate_paper_draft("What is retrieval augmented generation?")
        assert result["status"] == "success"
        assert result["title"]
        assert len(result["sections"]) >= 6
        assert result["markdown"]
        assert result["latex"]
        assert result["referenceCount"] >= 0
        heading_names = [s["heading"] for s in result["sections"]]
        assert "Abstract" in heading_names
        assert "Introduction" in heading_names
        assert "Methodology" in heading_names
        assert "Results" in heading_names

    def test_with_findings_includes_result_details(self):
        findings = [
            {"subQuestion": "How does RAG work?", "summary": "RAG retrieves then generates.", "verdict": "CORRECT", "judgeScore": 85},
            {"subQuestion": "What are limitations?", "summary": "Retrieval quality limits output.", "verdict": "AMBIGUOUS", "judgeScore": 60},
        ]
        result = generate_paper_draft("RAG analysis", findings=findings)
        assert result["status"] == "success"
        assert "RAG retrieves" in result["markdown"]
        assert "85" in result["markdown"]

    def test_with_evidence_generates_references(self):
        evidence = [
            {"title": "Original RAG Paper", "authors": ["Lewis, Patrick"], "year": 2020, "doi": "10.1234/rag"},
            {"title": "Self-RAG", "authors": ["Asai, Akari"], "year": 2023},
        ]
        result = generate_paper_draft("RAG review", evidence_items=evidence)
        assert result["status"] == "success"
        assert result["referenceCount"] >= 1
        ref_section = result["markdown"]
        assert "References" in ref_section

    def test_with_conflicts_adds_discussion(self):
        conflicts = [
            {"claim": "RAG outperforms fine-tuning", "summary": "Some studies show RAG is better, others show fine-tuning wins."},
        ]
        result = generate_paper_draft("RAG vs Fine-tuning", conflicts=conflicts)
        assert result["status"] == "success"
        assert "Conflicts Identified" in result["markdown"] or "Discussion" in result["markdown"]

    def test_custom_title_is_used(self):
        result = generate_paper_draft("Some research question", title="My Custom Paper Title")
        assert result["title"] == "My Custom Paper Title"

    def test_long_question_uses_truncated_title(self):
        long_q = "How does " + "very " * 50 + "long question work?"
        result = generate_paper_draft(long_q)
        assert result["status"] == "success"
        assert len(result["title"]) <= 200

    def test_output_has_all_required_fields(self):
        result = generate_paper_draft("Test question")
        required = ["status", "title", "sections", "referenceCount", "outputPath", "markdown", "latex", "error"]
        for key in required:
            assert key in result, f"Missing required key: {key}"

    def test_sections_have_heading_and_word_count(self):
        result = generate_paper_draft("Test question")
        for section in result["sections"]:
            assert "heading" in section
            assert "wordCount" in section
            assert section["wordCount"] >= 0
