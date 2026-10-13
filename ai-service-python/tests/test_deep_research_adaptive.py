"""Focused tests for DR3 adaptive retrieval, evidence union, coverage, and verified-only rendering.

Tests: relevance judgment via LLM, changed query content, evidence merge across rounds,
unsupported coverage rejection, condition preservation, external acquire integration,
incremental child dedup, verified-only section rendering, malformed-plan stop,
no-new-evidence stopping. No real network calls. Parent owns execution.
"""
from __future__ import annotations

import json
import time
from typing import Any

import pytest


# ── Test Helpers ────────────────────────────────────────────────────────────────

class TrackingRetriever:
    def __init__(self, items_by_query: dict[str, list[dict]] | None = None):
        self.items_by_query = items_by_query or {}
        self.default_items = [{
            "sourceId": "src_paper1_chunk1",
            "pdfId": "paper1",
            "sourceWorkId": "paper1",
            "text": "The method achieves 95% accuracy on the test set.",
            "chunkIndex": 1,
        }]
        self.call_log: list[dict] = []

    def __call__(self, query: str, pdf_id: str, *, limit: int = 5) -> list[dict]:
        self.call_log.append({"query": query, "pdfId": pdf_id, "limit": limit})
        return self.items_by_query.get(query, self.default_items)[:limit]


class AlwaysAllowValidator:
    def __call__(self, run_id: str, material_id: str) -> bool:
        return True


def _make_plan(items: list[dict] | None = None) -> list[dict]:
    if items is None:
        return [{
            "itemId": "item1",
            "question": "What is the main claim?",
            "obligations": [{
                "obligationId": "obl1",
                "question": "Verify accuracy claim",
                "requiredSources": ["paper1"],
            }],
            "dependencies": [],
            "priority": 1,
        }]
    return items


def _make_evidence(
    evidence_id: str = "ev_1",
    source_work_id: str = "paper1",
    obligation_ids: list[str] | None = None,
    conditions: dict | None = None,
    literal: str = "passed",
    content_hash: str = "abc123",
) -> dict:
    return {
        "evidenceId": evidence_id,
        "sourceWorkId": source_work_id,
        "sourceVersionId": "v1",
        "contentHash": content_hash,
        "accessLevel": "fulltext",
        "quote": "The method achieves 95% accuracy on the test set.",
        "location": {"page": 3},
        "obligationIds": obligation_ids or ["obl1"],
        "conditions": conditions or {"dataset": "ImageNet"},
        "verification": {"literal": literal, "semantic": "unchecked"},
    }


# ── Relevance Judgment Tests ───────────────────────────────────────────────────

class TestRelevanceJudgment:
    """Assess node must use LLM to judge obligation/evidence binding.
    Literal=='passed' plus obligation ID alone is NOT sufficient."""

    def test_llm_relevance_call_made(self):
        from services.deep_research.graph import make_assess_node

        ev = _make_evidence("ev_rel")
        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [ev], "sources": [{"sourceId": "s1"}]},
            "materials": [{"materialId": "paper1"}],
        }
        llm_calls = []

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_llm_invoke(run_id, node, prompt, extra, **kw):
            llm_calls.append({"node": node, "prompt": prompt})
            return {"content": json.dumps([{
                "evidenceId": "ev_rel",
                "obligationId": "obl1",
                "relevant": True,
                "reason": "directly addresses accuracy",
            }])}

        def mock_coverage_gaps(plan, coverage, required_sources):
            supported = [c for c in coverage if c["state"] == "supported"]
            if supported:
                return []
            return [{"obligationId": "obl1", "sourceWorkId": "paper1",
                      "question": "Verify accuracy claim", "checked": True, "missingEvidence": ""}]

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update, llm_invoke=mock_llm_invoke)
        state = {"run_id": "run_test", "requery_count": 0, "prev_source_count": 0}
        result = assess_node(state)

        assert any(c["node"] == "assess_relevance" for c in llm_calls)
        assert result["stop_reason"] == "covered"

    def test_irrelevant_evidence_does_not_close_gap(self):
        from services.deep_research.graph import make_assess_node

        ev = _make_evidence("ev_irrel")
        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [ev], "sources": [{"sourceId": "s1"}]},
            "materials": [{"materialId": "paper1"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_llm_invoke(run_id, node, prompt, extra, **kw):
            return {"content": json.dumps([{
                "evidenceId": "ev_irrel",
                "obligationId": "obl1",
                "relevant": False,
                "reason": "quote is about unrelated topic",
            }])}

        def mock_coverage_gaps(plan, coverage, required_sources):
            supported = [c for c in coverage if c["state"] == "supported"]
            if not supported:
                return [{"obligationId": "obl1", "sourceWorkId": "paper1",
                          "question": "Verify accuracy claim", "checked": True, "missingEvidence": "irrelevant"}]
            return []

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update, llm_invoke=mock_llm_invoke)
        state = {"run_id": "run_test", "requery_count": 0, "prev_source_count": 0}
        result = assess_node(state)

        assert result["stop_reason"] != "covered"
        assert len(result["gaps"]) > 0

    def test_no_llm_means_no_relevance_confirmed(self):
        from services.deep_research.graph import make_assess_node

        ev = _make_evidence("ev_nollm")
        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [ev], "sources": [{"sourceId": "s1"}]},
            "materials": [{"materialId": "paper1"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_coverage_gaps(plan, coverage, required_sources):
            supported = [c for c in coverage if c["state"] == "supported"]
            if not supported:
                return [{"obligationId": "obl1", "sourceWorkId": "paper1",
                          "question": "Verify", "checked": True, "missingEvidence": ""}]
            return []

        # No LLM invoke passed
        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update, llm_invoke=None)
        state = {"run_id": "run_test", "requery_count": 0, "prev_source_count": 0}
        result = assess_node(state)

        # Without LLM, nothing is confirmed relevant
        assert result["stop_reason"] != "covered"


# ── Changed Query Content Tests ────────────────────────────────────────────────

class TestChangedQueryContent:
    """Changed queries must have meaningful gap-focused content, not just round markers."""

    def test_query_includes_missing_source_and_obligation(self):
        from services.deep_research.graph import make_assess_node

        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [], "sources": []},
            "materials": [{"materialId": "paper1"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_coverage_gaps(plan, coverage, required_sources):
            return [{
                "obligationId": "obl1",
                "sourceWorkId": "paper1",
                "question": "Verify accuracy claim",
                "checked": False,
                "missingEvidence": "尚未核实",
            }]

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update)
        state = {"run_id": "run_test", "requery_count": 0, "prev_source_count": 0}
        result = assess_node(state)

        queries = result["requery_queries"]
        assert len(queries) > 0
        q = queries[0]
        assert q["obligationId"] == "obl1"
        assert "Verify accuracy claim" in q["query"]
        assert q["query"] != "Verify accuracy claim"
        assert q.get("missingSource") == "paper1"

    def test_query_targets_only_missing_pairs(self):
        from services.deep_research.graph import make_assess_node

        plan = _make_plan([{
            "itemId": "item1",
            "question": "Q1",
            "obligations": [
                {"obligationId": "obl1", "question": "Check A", "requiredSources": ["paper1"]},
                {"obligationId": "obl2", "question": "Check B", "requiredSources": ["paper2"]},
            ],
            "dependencies": [],
            "priority": 1,
        }])
        repo_state = {
            "state": {"plan": plan, "evidence": [], "sources": []},
            "materials": [{"materialId": "paper1"}, {"materialId": "paper2"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_coverage_gaps(plan, coverage, required_sources):
            return [
                {"obligationId": "obl2", "sourceWorkId": "paper2",
                 "question": "Check B", "checked": False, "missingEvidence": ""},
            ]

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update)
        state = {"run_id": "run_test", "requery_count": 0, "prev_source_count": 0}
        result = assess_node(state)

        queries = result["requery_queries"]
        assert len(queries) == 1
        assert queries[0]["obligationId"] == "obl2"
        assert queries[0].get("missingSource") == "paper2"


# ── No New Evidence Stopping Tests ─────────────────────────────────────────────

class TestNoNewEvidenceStop:
    """Must stop when requery produces no new sources."""

    def test_stops_when_source_count_unchanged(self):
        from services.deep_research.graph import make_assess_node

        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [], "sources": [{"sourceId": "s1"}]},
            "materials": [{"materialId": "paper1"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_coverage_gaps(plan, coverage, required_sources):
            return [{"obligationId": "obl1", "sourceWorkId": "paper1",
                      "question": "Verify", "checked": False, "missingEvidence": ""}]

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update)
        # prev_source_count == current (1), requery_count > 0
        state = {"run_id": "run_test", "requery_count": 1, "prev_source_count": 1}
        result = assess_node(state)

        assert result["stop_reason"] == "no_new_evidence"
        assert result.get("requery_queries", []) == []

    def test_continues_when_new_sources_found(self):
        from services.deep_research.graph import make_assess_node

        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [],
                       "sources": [{"sourceId": "s1"}, {"sourceId": "s2"}]},
            "materials": [{"materialId": "paper1"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_coverage_gaps(plan, coverage, required_sources):
            return [{"obligationId": "obl1", "sourceWorkId": "paper1",
                      "question": "Verify", "checked": False, "missingEvidence": ""}]

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update)
        # prev was 1, now 2 → new evidence found
        state = {"run_id": "run_test", "requery_count": 1, "prev_source_count": 1}
        result = assess_node(state)

        assert result["stop_reason"] != "no_new_evidence"


# ── Evidence Union Across Rounds ───────────────────────────────────────────────

class TestEvidenceUnion:
    """Evidence must merge across requery rounds without duplication."""

    def test_extract_merges_evidence_by_id(self):
        from services.deep_research.graph import make_extract_node

        existing_evidence = [_make_evidence("ev_existing")]
        repo_state = {
            "state": {
                "readResults": [{
                    "sourceId": "src_new", "workId": "paper1", "versionId": "v1",
                    "contentHash": "hash_new", "accessLevel": "fulltext",
                    "pages": [{"page": 1, "text": "New evidence text that is long enough to pass the minimum length threshold for extraction processing."}],
                    "obligationIds": ["obl1"], "sourceKind": "local", "title": "", "url": "",
                }],
                "plan": _make_plan(),
                "evidence": existing_evidence,
            },
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_llm_invoke(run_id, node, prompt, extra, **kw):
            return {"content": json.dumps([{
                "quote": "New evidence text that is long enough to pass the minimum length threshold for extraction processing.",
                "location": {"page": 1}, "obligationIds": ["obl1"], "conditions": {}, "kind": "reported",
            }])}

        def mock_make_evidence(source, quote, original, *, location, obligation_ids, conditions=None):
            eid = "ev_new" if quote.startswith("New") else f"ev_{hash(quote) % 10000}"
            return {
                "evidenceId": eid, "sourceWorkId": source["workId"],
                "sourceVersionId": source["versionId"], "contentHash": source["contentHash"],
                "accessLevel": source["accessLevel"], "quote": quote, "location": location,
                "obligationIds": obligation_ids, "conditions": {},
                "verification": {"literal": "passed", "semantic": "unchecked"},
            }

        extract_node = make_extract_node(mock_llm_invoke, mock_make_evidence, AlwaysAllowValidator(), mock_repo_update)
        state = {"run_id": "run_test", "previous_evidence_hashes": []}
        result = extract_node(state)

        assert "ev_existing" in result["evidence_ids"]
        assert "ev_new" in result["evidence_ids"]
        assert len(result["evidence_ids"]) == 2

    def test_extract_skips_duplicate_evidence_id(self):
        from services.deep_research.graph import make_extract_node

        existing = _make_evidence("ev_dup")
        repo_state = {
            "state": {
                "readResults": [{
                    "sourceId": "src1", "workId": "paper1", "versionId": "v1",
                    "contentHash": "h1", "accessLevel": "fulltext",
                    "pages": [{"page": 1, "text": "Duplicate evidence text that is long enough to pass the minimum length threshold for extraction."}],
                    "obligationIds": ["obl1"], "sourceKind": "local", "title": "", "url": "",
                }],
                "plan": _make_plan(), "evidence": [existing],
            },
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_llm_invoke(run_id, node, prompt, extra, **kw):
            return {"content": json.dumps([{
                "quote": "Duplicate evidence text that is long enough to pass the minimum length threshold for extraction.",
                "location": {"page": 1}, "obligationIds": ["obl1"], "conditions": {}, "kind": "reported",
            }])}

        def mock_make_evidence(source, quote, original, *, location, obligation_ids, conditions=None):
            return {**existing}

        extract_node = make_extract_node(mock_llm_invoke, mock_make_evidence, AlwaysAllowValidator(), mock_repo_update)
        state = {"run_id": "run_test", "previous_evidence_hashes": []}
        result = extract_node(state)

        assert len(result["evidence_ids"]) == 1


# ── Incremental Child Dedup Tests ──────────────────────────────────────────────

class TestIncrementalChildDedup:
    """Inherited sources/evidence must not be re-extracted."""

    def test_skips_already_extracted_content_hash(self):
        from services.deep_research.graph import make_extract_node

        existing = _make_evidence("ev_inherited", content_hash="hash_inherited")
        existing["sourceId"] = "src_inh"
        repo_state = {
            "state": {
                "readResults": [{
                    "sourceId": "src_inh", "workId": "paper1", "versionId": "v1",
                    "contentHash": "hash_inherited", "accessLevel": "fulltext",
                    "pages": [{"page": 1, "text": "This text should be skipped because the hash was already extracted previously."}],
                    "obligationIds": ["obl1"], "sourceKind": "local", "title": "", "url": "",
                }],
                "plan": _make_plan(), "evidence": [existing],
            },
        }
        llm_calls = []

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_llm_invoke(run_id, node, prompt, extra, **kw):
            llm_calls.append(node)
            return {"content": "[]"}

        def mock_make_evidence(source, quote, original, *, location, obligation_ids, conditions=None):
            return {"evidenceId": "ev_new", **source, "quote": quote, "location": location,
                    "obligationIds": obligation_ids, "conditions": {},
                    "verification": {"literal": "passed"}}

        extract_node = make_extract_node(mock_llm_invoke, mock_make_evidence, AlwaysAllowValidator(), mock_repo_update)
        state = {"run_id": "run_test", "previous_evidence_hashes": ["hash_inherited"]}
        result = extract_node(state)

        # Should not have called LLM for extraction since hash already seen
        assert len(llm_calls) == 0
        assert len(result["evidence_ids"]) == 1


# ── External Acquire Integration Tests ─────────────────────────────────────────

class TestExternalAcquire:
    """External acquisition only when policy permits; sources merged correctly."""

    def test_external_acquire_called_for_external_policy(self):
        from services.deep_research.graph import make_acquire_node

        repo_state = {"sourcePolicy": {"mode": "academic_external"},
            "materials": [],
            "state": {"plan": _make_plan(), "sources": []},
        }
        updated_state = {}
        ext_calls = []

        def mock_repo_update(run_id, updater, expected_revision):
            result = updater(repo_state)
            updated_state.update(result.get("state", {}))
            return result

        def mock_external_acquire(run_id, query_targets):
            ext_calls.append(query_targets)
            return [{
                "sourceId": "ext_arxiv_1",
                "workId": "arxiv_2401.00001",
                "versionId": "v1",
                "contentHash": "ext_hash_1",
                "accessLevel": "fulltext",
                "text": "External paper abstract text.",
                "location": {"page": 0},
                "obligationIds": ["obl1"],
                "sourceKind": "arxiv",
                "title": "External Paper Title",
                "arxivId": "2401.00001",
                "url": "https://arxiv.org/abs/2401.00001",
            }]

        acquire_node = make_acquire_node(
            TrackingRetriever(), AlwaysAllowValidator(), mock_repo_update,
            external_acquire=mock_external_acquire,
        )
        state = {
            "run_id": "run_test",
            "requery_queries": [{"obligationId": "obl1", "query": "test query"}],
            "source_policy_mode": "external_only",
        }
        acquire_node(state)

        assert len(ext_calls) == 1
        sources = updated_state.get("sources", [])
        ext_src = next((s for s in sources if s["sourceId"] == "ext_arxiv_1"), None)
        assert ext_src is not None
        assert ext_src["sourceKind"] == "arxiv"
        assert ext_src["title"] == "External Paper Title"

    def test_external_acquire_not_called_for_task_only(self):
        from services.deep_research.graph import make_acquire_node

        repo_state = {"sourcePolicy": {"mode": "task_only"},
            "materials": [{"materialId": "paper1", "pdfId": "paper1"}],
            "state": {"plan": _make_plan(), "sources": []},
        }
        ext_calls = []

        def mock_repo_update(run_id, updater, expected_revision):
            return updater(repo_state)

        def mock_external_acquire(run_id, query_targets):
            ext_calls.append(True)
            return []

        acquire_node = make_acquire_node(
            TrackingRetriever(), AlwaysAllowValidator(), mock_repo_update,
            external_acquire=mock_external_acquire,
        )
        state = {
            "run_id": "run_test",
            "requery_queries": [],
            "source_policy_mode": "task_only",
        }
        acquire_node(state)

        assert len(ext_calls) == 0

    def test_external_sources_merged_with_local(self):
        from services.deep_research.graph import make_acquire_node

        local_source = {
            "sourceId": "local_1", "workId": "paper1", "ownerMaterialId": "paper1",
            "versionId": "v1", "contentHash": "lh", "accessLevel": "fulltext",
            "text": "local", "location": {}, "obligationIds": ["obl1"],
            "sourceKind": "local", "title": "", "url": "",
        }
        repo_state = {"sourcePolicy": {"mode": "academic_external"},
            "materials": [{"materialId": "paper1", "pdfId": "paper1"}],
            "state": {"plan": _make_plan(), "sources": [local_source]},
        }
        updated_state = {}

        def mock_repo_update(run_id, updater, expected_revision):
            result = updater(repo_state)
            updated_state.update(result.get("state", {}))
            return result

        def mock_external_acquire(run_id, query_targets):
            return [{
                "sourceId": "ext_1", "workId": "arxiv_x", "versionId": "v1",
                "contentHash": "eh", "accessLevel": "abstract", "text": "ext",
                "location": {}, "obligationIds": ["obl1"], "sourceKind": "arxiv",
                "title": "Ext", "arxivId": "x", "url": "",
            }]

        acquire_node = make_acquire_node(
            TrackingRetriever(), AlwaysAllowValidator(), mock_repo_update,
            external_acquire=mock_external_acquire,
        )
        state = {
            "run_id": "run_test", "requery_queries": [],
            "source_policy_mode": "academic_external",
        }
        acquire_node(state)

        sources = updated_state.get("sources", [])
        ids = [s["sourceId"] for s in sources]
        assert "local_1" in ids
        assert "ext_1" in ids


# ── Unsupported Coverage Tests ─────────────────────────────────────────────────

class TestUnsupportedCoverage:
    """Coverage requires LLM-confirmed relevance, not just literal quote."""

    def test_evidence_without_obligation_ids_not_counted(self):
        from services.deep_research.graph import make_assess_node

        ev_no_obl = _make_evidence("ev_no_obl", obligation_ids=[])
        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [ev_no_obl], "sources": [{"sourceId": "s1"}]},
            "materials": [{"materialId": "paper1"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_coverage_gaps(plan, coverage, required_sources):
            return [{"obligationId": "obl1", "sourceWorkId": "paper1",
                      "question": "Verify accuracy claim", "checked": False, "missingEvidence": ""}]

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update)
        state = {"run_id": "run_test", "requery_count": 0, "prev_source_count": 0}
        result = assess_node(state)

        assert len(result["gaps"]) > 0
        assert result["stop_reason"] != "covered"

    def test_failed_literal_verification_not_supported(self):
        from services.deep_research.graph import make_assess_node

        ev_failed = _make_evidence("ev_fail", literal="failed")
        repo_state = {
            "state": {"plan": _make_plan(), "evidence": [ev_failed], "sources": [{"sourceId": "s1"}]},
            "materials": [{"materialId": "paper1"}],
        }

        def mock_repo_update(run_id, updater, expected_revision):
            return repo_state

        def mock_coverage_gaps(plan, coverage, required_sources):
            return [{"obligationId": "obl1", "sourceWorkId": "paper1",
                      "question": "Verify", "checked": True, "missingEvidence": "literal failed"}]

        assess_node = make_assess_node(mock_coverage_gaps, mock_repo_update)
        state = {"run_id": "run_test", "requery_count": 0, "prev_source_count": 0}
        result = assess_node(state)

        assert result["stop_reason"] != "covered"


# ── Condition Preservation Tests ───────────────────────────────────────────────

class TestConditionPreservation:
    """Source identity and condition fields must be preserved exactly."""

    def test_acquire_preserves_source_identity_and_kind(self):
        from services.deep_research.graph import make_acquire_node

        repo_state = {
            "materials": [{"materialId": "paper1", "pdfId": "paper1", "versionId": "v1"}],
            "state": {"plan": _make_plan(), "sources": []},
        }
        updated_state = {}

        def mock_repo_update(run_id, updater, expected_revision):
            result = updater(repo_state)
            updated_state.update(result.get("state", {}))
            return result

        retriever = TrackingRetriever()
        acquire_node = make_acquire_node(retriever, AlwaysAllowValidator(), mock_repo_update)
        state = {"run_id": "run_test", "requery_queries": [], "source_policy_mode": "task_only"}
        acquire_node(state)

        sources = updated_state.get("sources", [])
        assert len(sources) > 0
        src = sources[0]
        assert src["workId"] == "paper1"
        assert src["versionId"] == "v1"
        assert "contentHash" in src
        assert "obligationIds" in src
        assert "sourceKind" in src

    def test_acquire_merges_obligation_ids_on_requery(self):
        from services.deep_research.graph import make_acquire_node

        existing_source = {
            "sourceId": "src_paper1_chunk1", "workId": "paper1", "ownerMaterialId": "paper1",
            "versionId": "v1", "contentHash": "abc", "accessLevel": "fulltext",
            "text": "existing text", "location": {"chunkIndex": 1}, "obligationIds": ["obl1"],
            "sourceKind": "local", "title": "", "url": "",
        }
        repo_state = {
            "materials": [{"materialId": "paper1", "pdfId": "paper1"}],
            "state": {"plan": _make_plan(), "sources": [existing_source]},
        }
        updated_state = {}

        def mock_repo_update(run_id, updater, expected_revision):
            result = updater(repo_state)
            updated_state.update(result.get("state", {}))
            return result

        acquire_node = make_acquire_node(TrackingRetriever(), AlwaysAllowValidator(), mock_repo_update)
        state = {
            "run_id": "run_test",
            "requery_queries": [{"obligationId": "obl2", "query": "changed query"}],
            "source_policy_mode": "task_only",
        }
        acquire_node(state)

        sources = updated_state.get("sources", [])
        merged = next((s for s in sources if s["sourceId"] == "src_paper1_chunk1"), None)
        assert merged is not None
        assert "obl1" in merged["obligationIds"]
        assert "obl2" in merged["obligationIds"]


# ── Verified-Only Section Rendering Tests ──────────────────────────────────────

class TestVerifiedOnlyRendering:
    """Report body must contain only verified claims or labeled proposals."""

    def test_build_verified_sections_uses_claim_ids(self):
        from services.deep_research.graph import _build_verified_sections

        claims = [
            {"claimId": "c1", "text": "Accuracy is 95%.", "kind": "reported",
             "evidenceRefs": ["ev1"], "obligationIds": ["obl1"], "conditions": {"dataset": "ImageNet"}},
            {"claimId": "c2", "text": "Method uses pruning.", "kind": "inference",
             "evidenceRefs": ["ev2"], "obligationIds": ["obl1"], "conditions": {}},
        ]
        sections = _build_verified_sections(claims, "claim_verification")

        assert len(sections) > 0
        all_claim_ids = set()
        for section in sections:
            for cid in section.get("claimIds", []):
                all_claim_ids.add(cid)
        assert all_claim_ids <= {"c1", "c2"}

    def test_sections_exclude_unverified_claim_ids(self):
        from services.deep_research.synthesis import _validate_section_claim_binding

        sections = [{"title": "Test", "content": "Some content",
                      "claimIds": ["c_valid", "c_invalid"], "citations": []}]
        verified_claims = [{"claimId": "c_valid", "text": "Valid"}]
        result = _validate_section_claim_binding(sections, verified_claims)

        assert len(result) == 1
        assert result[0]["claimIds"] == ["c_valid"]

    def test_proposals_are_labeled(self):
        from services.deep_research.synthesis import _validate_proposals

        raw = [
            {"text": "Try approach X", "kind": "hypothesis"},
            {"text": "Consider Y", "kind": "unknown_kind"},
            "Plain string proposal",
        ]
        result = _validate_proposals(raw)

        assert len(result) == 3
        assert result[0]["kind"] == "hypothesis"
        assert result[1]["kind"] == "proposal"
        assert result[2]["kind"] == "proposal"


# ── Malformed Plan Stop Tests ──────────────────────────────────────────────────

class TestMalformedPlanStop:
    """Malformed plans must not proceed to retrieval."""

    def test_non_list_plan_response_stops(self):
        from services.deep_research.graph import make_plan_node

        repo_state = {"question": "Test", "state": {"outputKind": "direction_survey"},
                       "materials": [{"materialId": "paper1"}]}

        plan_node = make_plan_node(
            lambda *a, **kw: {"content": '{"not": "a list"}'},
            lambda rid, up, expected_revision=None: repo_state,
            lambda items: items,
        )
        result = plan_node({"run_id": "run_test"})

        assert result.get("error_code") == "invalid_plan_response"
        assert result.get("plan_ids") == []

    def test_validation_failure_stops_before_retrieval(self):
        from services.deep_research.graph import make_plan_node

        repo_state = {"question": "Test", "state": {"outputKind": "direction_survey"},
                       "materials": [{"materialId": "paper1"}]}

        def bad_validate(items):
            raise ValueError("Plan must state research obligations")

        plan_node = make_plan_node(
            lambda *a, **kw: {"content": '[{"itemId":"i1","question":"Q","obligations":[],"dependencies":[],"priority":1}]'},
            lambda rid, up, expected_revision=None: repo_state,
            bad_validate,
        )
        result = plan_node({"run_id": "run_test"})

        assert result.get("error_code") == "invalid_plan_response"
        assert result.get("plan_ids") == []

    def test_empty_validated_plan_stops(self):
        from services.deep_research.graph import make_plan_node

        repo_state = {"question": "Test", "state": {"outputKind": "direction_survey"},
                       "materials": [{"materialId": "paper1"}]}

        plan_node = make_plan_node(
            lambda *a, **kw: {"content": '[]'},
            lambda rid, up, expected_revision=None: repo_state,
            lambda items: [],
        )
        result = plan_node({"run_id": "run_test"})

        assert result.get("error_code") == "invalid_plan_response"
        assert result.get("plan_ids") == []


# ── Output Kind Alignment Tests ────────────────────────────────────────────────

class TestOutputKindAlignment:
    def test_resolve_output_kind_aliases(self):
        from services.deep_research.synthesis import resolve_output_kind

        assert resolve_output_kind("claim_check") == "claim_verification"
        assert resolve_output_kind("research_opportunity") == "research_entry"
        assert resolve_output_kind("direction_survey") == "direction_survey"
        assert resolve_output_kind("paper_comparison") == "paper_comparison"
        assert resolve_output_kind("experiment_design") == "experiment_design"

    def test_output_kind_sections_has_five_kinds(self):
        from services.deep_research.synthesis import OUTPUT_KIND_SECTIONS

        expected = {"direction_survey", "paper_comparison", "claim_verification",
                    "experiment_design", "research_entry"}
        assert set(OUTPUT_KIND_SECTIONS.keys()) == expected


# ── Extract Prompt Obligation ID Tests ─────────────────────────────────────────

class TestExtractPromptObligationIds:
    def test_extract_prompt_contains_obligation_ids(self):
        from services.deep_research.graph import make_extract_node

        captured_prompts = []
        repo_state = {
            "state": {
                "readResults": [{
                    "sourceId": "src1", "workId": "paper1", "versionId": "v1",
                    "contentHash": "h1", "accessLevel": "fulltext",
                    "pages": [{"page": 1, "text": "Long enough text for extraction that contains sufficient content to pass minimum length validation checks."}],
                    "obligationIds": ["obl1"], "sourceKind": "local", "title": "", "url": "",
                }],
                "plan": _make_plan(), "evidence": [],
            },
        }

        def mock_llm_invoke(run_id, node, prompt, extra, **kw):
            captured_prompts.append(prompt)
            return {"content": "[]"}

        def mock_make_evidence(source, quote, original, *, location, obligation_ids, conditions=None):
            return {"evidenceId": "ev1", **source, "quote": quote, "location": location,
                    "obligationIds": obligation_ids, "conditions": {},
                    "verification": {"literal": "passed"}}

        extract_node = make_extract_node(mock_llm_invoke, mock_make_evidence, AlwaysAllowValidator(),
                                          lambda rid, up, expected_revision=None: repo_state)
        extract_node({"run_id": "run_test", "previous_evidence_hashes": []})

        assert len(captured_prompts) > 0
        assert "obligationId" in captured_prompts[0]
        assert "obl1" in captured_prompts[0]


# ── Route After Assess Tests ───────────────────────────────────────────────────

class TestRouteAfterAssess:
    def test_routes_to_acquire_with_requery_queries(self):
        from services.deep_research.graph import route_after_assess

        state = {"stop_reason": "", "gaps": [{"obligationId": "obl1"}], "requery_count": 1,
                 "budget_exhausted": False, "error_code": "",
                 "requery_queries": [{"obligationId": "obl1", "query": "changed"}]}
        assert route_after_assess(state) == "acquire"

    def test_routes_to_synthesize_without_requery_queries(self):
        from services.deep_research.graph import route_after_assess

        state = {"stop_reason": "", "gaps": [{"obligationId": "obl1"}], "requery_count": 1,
                 "budget_exhausted": False, "error_code": "", "requery_queries": []}
        assert route_after_assess(state) == "synthesize"

    def test_routes_to_synthesize_at_max_requery(self):
        from services.deep_research.graph import route_after_assess

        state = {"stop_reason": "max_requery", "gaps": [{"obligationId": "obl1"}], "requery_count": 2,
                 "budget_exhausted": False, "error_code": "", "requery_queries": []}
        assert route_after_assess(state) == "synthesize"

    def test_routes_to_synthesize_on_no_new_evidence(self):
        from services.deep_research.graph import route_after_assess

        state = {"stop_reason": "no_new_evidence", "gaps": [{"obligationId": "obl1"}], "requery_count": 1,
                 "budget_exhausted": False, "error_code": "", "requery_queries": []}
        assert route_after_assess(state) == "synthesize"

    def test_routes_to_fail_on_error(self):
        from services.deep_research.graph import route_after_assess

        state = {"stop_reason": "", "gaps": [], "requery_count": 0,
                 "budget_exhausted": False, "error_code": "invalid_plan_response", "requery_queries": []}
        assert route_after_assess(state) == "fail"


# ── Read Node Metadata Retention Tests ─────────────────────────────────────────

class TestReadNodeMetadataRetention:
    """Read node must retain sourceKind/title/url from source metadata."""

    def test_read_preserves_source_kind_title_url(self):
        from services.deep_research.graph import make_read_node

        source_meta = {
            "sourceId": "src_ext", "workId": "arxiv_x", "ownerMaterialId": "arxiv_x",
            "versionId": "v1", "contentHash": "h1", "accessLevel": "fulltext",
            "text": "External paper text content here.", "location": {},
            "sourceKind": "arxiv", "title": "My ArXiv Paper", "url": "https://arxiv.org/abs/x",
            "obligationIds": ["obl1"],
        }
        repo_state = {"state": {"sources": [source_meta]}}
        updated_state = {}

        def mock_repo_update(run_id, updater, expected_revision):
            result = updater(repo_state)
            updated_state.update(result.get("state", {}))
            return result

        def mock_read_fn(run_id, source_id):
            return {"pages": [{"page": 1, "text": "External paper text content here."}], "accessLevel": "fulltext"}

        read_node = make_read_node(mock_read_fn, AlwaysAllowValidator(), mock_repo_update)
        read_node({"run_id": "run_test", "source_ids": ["src_ext"]})

        read_results = updated_state.get("readResults", [])
        assert len(read_results) == 1
        rr = read_results[0]
        assert rr["sourceKind"] == "arxiv"
        assert rr["title"] == "My ArXiv Paper"
        assert rr["url"] == "https://arxiv.org/abs/x"
        assert rr["obligationIds"] == ["obl1"]
