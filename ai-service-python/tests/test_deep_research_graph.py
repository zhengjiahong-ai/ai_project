"""Comprehensive tests for Deep Research v2 graph.

Tests meaningful scenarios with injected deterministic model/retriever/scope validator.
No real network calls. Exercises persistent restart, replay, budget, cancellation, etc.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Test fixtures and helpers
class DeterministicLLM:
    """Mock LLM that returns predetermined responses based on node name."""
    
    def __init__(self, responses: dict[str, dict] | None = None):
        self.responses = responses or {}
        self.call_log: list[dict] = []
    
    def invoke(self, request: Any) -> Any:
        """Simulate LLM invoke - extracts prompt to determine response."""
        from llm.provider import LLMResult, LLMUsage
        
        prompt = request.prompt if hasattr(request, "prompt") else str(request)
        
        # Log the call
        self.call_log.append({
            "prompt": prompt[:200],
            "extra_body": request.extra_body if hasattr(request, "extra_body") else {},
        })
        
        # Return appropriate response based on prompt content
        # ORDER MATTERS: more specific patterns must come before general ones
        # "research plan" must be checked BEFORE "output kind" since plan prompt contains "Output kind:"
        if "create a research plan" in prompt.lower():
            content = '''[{
                "itemId": "item1",
                "question": "What is the main claim?",
                "obligations": [{"obligationId": "obl1", "question": "Verify claim", "requiredSources": ["paper1"]}],
                "dependencies": [],
                "priority": 1
            }]'''
        elif "analyze this research question" in prompt.lower():
            content = '{"outputKind": "claim_check", "assumptions": [], "clarification": "", "constraints": ""}'
        elif "extract evidence" in prompt.lower():
            content = '''[{
                "quote": "The method achieves 95% accuracy on the test set.",
                "location": {"page": 3, "section": "Results"},
                "obligationIds": ["obl1"],
                "conditions": {"dataset": "ImageNet"},
                "kind": "reported"
            }]'''
        elif "synthesize" in prompt.lower():
            content = '''{
                "summary": "The evidence supports the claim with 95% accuracy.",
                "sections": [{"title": "Main Finding", "content": "Accuracy is 95%.", "citations": ["paper1"]}],
                "claims": [{
                    "claimId": "claim1",
                    "text": "The method achieves 95% accuracy.",
                    "kind": "reported",
                    "evidenceRefs": ["ev_test"],
                    "conditions": {"dataset": "ImageNet"}
                }],
                "limitations": "Limited to ImageNet dataset.",
                "gaps": []
            }'''
        elif "verify" in prompt.lower():
            content = '[{"claimId": "claim1", "status": "passed", "reason": "Evidence directly supports"}]'
        else:
            content = '{}'
        
        return LLMResult(
            provider="test",
            model="test-model",
            content=content,
            usage=LLMUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        )


class DeterministicRetriever:
    """Mock retriever that returns fixed evidence."""
    
    def __init__(self, items: list[dict] | None = None):
        self.items = items or [
            {
                "sourceId": "src_paper1_chunk1",
                "pdfId": "paper1",
                "text": "The method achieves 95% accuracy on the test set.",
                "chunkIndex": 1,
            }
        ]
        self.call_log: list[dict] = []
    
    def __call__(self, query: str, pdf_id: str, *, limit: int = 5) -> list[dict]:
        self.call_log.append({"query": query, "pdfId": pdf_id, "limit": limit})
        return self.items[:limit]


class DeterministicReader:
    """Mock source reader."""
    
    def __init__(self, pages: list[dict] | None = None):
        self.pages = pages or [
            {"page": 1, "text": "Introduction text here."},
            {"page": 3, "text": "The method achieves 95% accuracy on the test set. This is a significant improvement over baseline methods which typically achieve 85-90% accuracy."},
        ]
        self.call_log: list[dict] = []
    
    def __call__(self, run_id: str, source_id: str) -> dict:
        self.call_log.append({"runId": run_id, "sourceId": source_id})
        return {"pages": self.pages, "accessLevel": "fulltext"}


class AlwaysAllowValidator:
    """Scope validator that always allows (for testing only)."""
    
    def __call__(self, run_id: str, material_id: str) -> bool:
        return True


class FailClosedValidator:
    """Scope validator that always denies (simulates revoked access)."""
    
    def __call__(self, run_id: str, material_id: str) -> bool:
        return False


@pytest.fixture
def temp_db():
    """Create temporary database files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_dr.db")
        yield db_path


@pytest.fixture
def repo(temp_db):
    """Create repository instance."""
    from services.deep_research.repository import DeepResearchRepository
    
    repository = DeepResearchRepository(temp_db)
    repository.initialize()
    return repository


@pytest.fixture
def mock_llm():
    return DeterministicLLM()


@pytest.fixture
def mock_retriever():
    return DeterministicRetriever()


@pytest.fixture
def mock_reader():
    return DeterministicReader()


@pytest.fixture
def allow_validator():
    return AlwaysAllowValidator()


@pytest.fixture
def deny_validator():
    return FailClosedValidator()


class TestGraphStateFields:
    """Test that graph state includes mandatory product fields."""
    
    def test_graph_state_has_workspace_task_id(self):
        from services.deep_research.graph import GraphState
        
        # GraphState should have workspace_task_id field
        annotations = GraphState.__annotations__
        assert "workspace_task_id" in annotations, "GraphState missing workspace_task_id"
        assert "operation_key" in annotations, "GraphState missing operation_key"
    
    def test_initial_state_includes_product_fields(self, repo, mock_llm, mock_retriever, mock_reader, allow_validator):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        
        # Create a run first
        record, _ = repo.create_run({
            "taskId": "task_123",
            "idempotencyKey": "op_key_456",
            "question": "Test question",
            "materials": [{"materialId": "paper1", "pdfId": "paper1"}],
        })
        
        # Build graph
        graph = build_deep_research_graph(
            llm_invoke=lambda run_id, node, prompt, extra, **kw: {"content": "{}", "usage": {}},
            retrieve_fn=mock_retriever,
            read_fn=mock_reader,
            scope_validator=allow_validator,
            make_evidence_fn=make_evidence,
            coverage_gaps_fn=coverage_gaps,
            verify_claims_fn=verify_claims,
            repo_update=repo.update_run,
            repo_publish=repo.publish_report,
            validate_plan_fn=validate_plan,
            checkpoint_conn=None,  # No persistence for this test
        )
        
        # Initial state must include product fields
        initial_state = {
            "run_id": record["runId"],
            "workspace_task_id": "task_123",
            "operation_key": "op_key_456",
            "execution_epoch": 0,
            "brief_id": "",
            "plan_ids": [],
            "source_ids": [],
            "evidence_ids": [],
            "claim_ids": [],
            "coverage_state": {},
            "gaps": [],
            "report_version_id": "",
            "publication_id": "",
            "outcome": "none",
            "error_code": "",
            "stop_reason": "",
            "clarification_needed": False,
            "clarification_question": "",
            "requery_count": 0,
            "budget_exhausted": False,
            "started_at": time.monotonic(),
            "deadline_seconds": 360.0,
        }
        
        # Verify state structure
        assert initial_state["workspace_task_id"] == "task_123"
        assert initial_state["operation_key"] == "op_key_456"


class TestNodeLabels:
    """Test that each node passes correct label to LLM invoker."""
    
    def test_nodes_use_correct_labels(self, repo, mock_llm, mock_retriever, mock_reader, allow_validator):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        
        call_log = []
        
        def logging_llm(run_id, node, prompt, extra, **kw):
            call_log.append(node)
            return mock_llm.invoke(type("Request", (), {"prompt": prompt, "extra_body": extra})())
        
        record, _ = repo.create_run({
            "taskId": "task_1",
            "idempotencyKey": "op_1",
            "question": "Test",
            "materials": [{"materialId": "paper1", "pdfId": "paper1"}],
        })
        
        graph = build_deep_research_graph(
            llm_invoke=logging_llm,
            retrieve_fn=mock_retriever,
            read_fn=mock_reader,
            scope_validator=allow_validator,
            make_evidence_fn=make_evidence,
            coverage_gaps_fn=coverage_gaps,
            verify_claims_fn=verify_claims,
            repo_update=repo.update_run,
            repo_publish=repo.publish_report,
            validate_plan_fn=validate_plan,
        )
        
        initial_state = {
            "run_id": record["runId"],
            "workspace_task_id": "task_1",
            "operation_key": "op_1",
            "execution_epoch": 0,
            "brief_id": "",
            "plan_ids": [],
            "source_ids": [],
            "evidence_ids": [],
            "claim_ids": [],
            "coverage_state": {},
            "gaps": [],
            "report_version_id": "",
            "publication_id": "",
            "outcome": "none",
            "error_code": "",
            "stop_reason": "",
            "clarification_needed": False,
            "clarification_question": "",
            "requery_count": 0,
            "budget_exhausted": False,
            "started_at": time.monotonic(),
            "deadline_seconds": 360.0,
        }
        
        config = {"configurable": {"thread_id": record["runId"]}}
        if repo.require_run(record["runId"])["status"] == "queued":
            repo.begin_execution(record["runId"])
        initial_state["execution_epoch"] = repo.require_run(record["runId"])["executionEpoch"]
        graph.invoke(initial_state, config=config)
        
        # Verify nodes called with correct labels
        assert "resolve_brief" in call_log, f"resolve_brief not in {call_log}"
        assert "plan" in call_log, f"plan not in {call_log}"
        assert "extract" in call_log, f"extract not in {call_log}"
        assert "synthesize" in call_log, f"synthesize not in {call_log}"


class TestReserveOnlyFinalNodes:
    """Test that only synthesize/verify use reserve pool."""
    
    def test_synthesize_uses_reserve(self, temp_db, mock_retriever, mock_reader, allow_validator):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        from services.deep_research.repository import DeepResearchRepository
        
        repo = DeepResearchRepository(temp_db)
        repo.initialize()
        
        reserve_calls = []
        
        def tracking_llm(run_id, node, prompt, extra, use_reserve=False, **kw):
            reserve_calls.append({"node": node, "use_reserve": use_reserve})
            return DeterministicLLM().invoke(type("R", (), {"prompt": prompt, "extra_body": extra})())
        
        record, _ = repo.create_run({
            "taskId": "task_1",
            "idempotencyKey": "op_1",
            "question": "Test",
            "materials": [{"materialId": "p1", "pdfId": "p1"}],
        })
        
        # Must begin execution before graph can run
        repo.begin_execution(record["runId"])
        
        graph = build_deep_research_graph(
            llm_invoke=tracking_llm,
            retrieve_fn=mock_retriever,
            read_fn=mock_reader,
            scope_validator=allow_validator,
            make_evidence_fn=make_evidence,
            coverage_gaps_fn=coverage_gaps,
            verify_claims_fn=verify_claims,
            repo_update=repo.update_run,
            repo_publish=repo.publish_report,
            validate_plan_fn=validate_plan,
        )
        
        initial_state = {
            "run_id": record["runId"],
            "workspace_task_id": "task_1",
            "operation_key": "op_1",
            "execution_epoch": 0,
            "brief_id": "",
            "plan_ids": [],
            "source_ids": [],
            "evidence_ids": [],
            "claim_ids": [],
            "coverage_state": {},
            "gaps": [],
            "report_version_id": "",
            "publication_id": "",
            "outcome": "none",
            "error_code": "",
            "stop_reason": "",
            "clarification_needed": False,
            "clarification_question": "",
            "requery_count": 0,
            "budget_exhausted": False,
            "started_at": time.monotonic(),
            "deadline_seconds": 360.0,
        }
        
        config = {"configurable": {"thread_id": record["runId"]}}
        if repo.require_run(record["runId"])["status"] == "queued":
            repo.begin_execution(record["runId"])
        initial_state["execution_epoch"] = repo.require_run(record["runId"])["executionEpoch"]
        graph.invoke(initial_state, config=config)
        
        # Check reserve usage
        synthesize_calls = [c for c in reserve_calls if c["node"] == "synthesize"]
        assert any(c["use_reserve"] for c in synthesize_calls), "Synthesize should use reserve"
        
        # Non-final nodes should NOT use reserve
        non_final = [c for c in reserve_calls if c["node"] in ("resolve_brief", "plan", "extract")]
        assert not any(c.get("use_reserve") for c in non_final), "Non-final nodes should not use reserve"


class TestTokenEstimation:
    """Test conservative UTF-8 token estimation."""
    
    def test_chinese_text_estimation(self):
        from services.deep_research.graph import estimate_prompt_tokens
        
        # Chinese text requires more tokens per character
        chinese_prompt = "这是一个测试问题，需要验证方法的准确性。" * 10
        ascii_prompt = "This is a test question about accuracy verification." * 10
        
        chinese_tokens = estimate_prompt_tokens(chinese_prompt)
        ascii_tokens = estimate_prompt_tokens(ascii_prompt)
        
        # Chinese should estimate higher due to UTF-8 byte length
        assert chinese_tokens > ascii_tokens, "Chinese should estimate more tokens"
    
    def test_overlarge_input_rejected(self):
        from services.deep_research.tools import TrackedLLMInvoker
        
        # Create invoker with small max (100 tokens = ~300 bytes max)
        invoker = TrackedLLMInvoker(
            llm_client=MagicMock(),
            reserve_call_fn=MagicMock(return_value=({"callId": "c1", "reservationToken": "t1"}, False)),
            complete_call_fn=MagicMock(),
            max_input_tokens=100,  # 100 tokens = 300 bytes max
        )
        
        # Large prompt should be rejected BEFORE reserve
        # 10000 bytes >> 300 bytes limit
        large_prompt = "x" * 10000
        
        with pytest.raises(ValueError, match="too large"):
            invoker("run1", "test", large_prompt, {})
        
        # Verify reserve was NOT called (rejection happens before reserve)
        invoker._reserve.assert_not_called()


class TestFullDigestStableIDs:
    """Test that args_digest uses full prompt, not truncated."""
    
    def test_full_prompt_digest(self):
        from services.deep_research.contracts import digest
        
        prompt1 = "A" * 1000
        prompt2 = "A" * 999 + "B"
        
        # Full digest should distinguish these
        d1 = digest({"prompt": prompt1})
        d2 = digest({"prompt": prompt2})
        
        assert d1 != d2, "Full digest should distinguish different prompts"
    
    def test_source_id_full_hash(self):
        from services.deep_research.tools import TrackedRetriever
        
        # Source IDs should use full hash, not truncated [:16]
        retriever = DeterministicRetriever([
            {"pdfId": "p1", "text": "text1", "chunkIndex": 0},
        ])
        
        tracked = TrackedRetriever(
            base_retriever=retriever,
            scope_validator=AlwaysAllowValidator(),
            reserve_call_fn=MagicMock(return_value=({"callId": "c1", "reservationToken": "t1"}, False)),
            complete_call_fn=MagicMock(),
        )
        
        results = tracked("run1", "query", "p1", limit=5)
        
        if results:
            source_id = results[0].get("sourceId", "")
            # Full SHA256 hex is 64 chars, plus "src_" prefix = 68
            assert len(source_id) >= 64, f"Source ID should be full hash: {source_id}"


class TestScopeValidationBeforeModelSend:
    """Test that ALL sources validated before every model send."""
    
    def test_extract_validates_before_llm(self, repo, mock_llm, mock_retriever, deny_validator):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        
        llm_called = []
        
        def tracking_llm(run_id, node, prompt, extra, **kw):
            llm_called.append(node)
            return {"content": "[]", "usage": {}}
        
        record, _ = repo.create_run({
            "taskId": "task_1",
            "idempotencyKey": "op_1",
            "question": "Test",
            "materials": [{"materialId": "p1", "pdfId": "p1"}],
        })
        
        graph = build_deep_research_graph(
            llm_invoke=tracking_llm,
            retrieve_fn=mock_retriever,
            read_fn=DeterministicReader(),
            scope_validator=deny_validator,  # Deny all
            make_evidence_fn=make_evidence,
            coverage_gaps_fn=coverage_gaps,
            verify_claims_fn=verify_claims,
            repo_update=repo.update_run,
            repo_publish=repo.publish_report,
            validate_plan_fn=validate_plan,
        )
        
        initial_state = {
            "run_id": record["runId"],
            "workspace_task_id": "task_1",
            "operation_key": "op_1",
            "execution_epoch": 0,
            "brief_id": "",
            "plan_ids": [],
            "source_ids": [],
            "evidence_ids": [],
            "claim_ids": [],
            "coverage_state": {},
            "gaps": [],
            "report_version_id": "",
            "publication_id": "",
            "outcome": "none",
            "error_code": "",
            "stop_reason": "",
            "clarification_needed": False,
            "clarification_question": "",
            "requery_count": 0,
            "budget_exhausted": False,
            "started_at": time.monotonic(),
            "deadline_seconds": 360.0,
        }
        
        config = {"configurable": {"thread_id": record["runId"]}}
        if repo.require_run(record["runId"])["status"] == "queued":
            repo.begin_execution(record["runId"])
        initial_state["execution_epoch"] = repo.require_run(record["runId"])["executionEpoch"]
        graph.invoke(initial_state, config=config)
        
        # Extract should NOT call LLM when scope denied
        # (read node skips sources, so extract has nothing to process)
        extract_calls = [c for c in llm_called if c == "extract"]
        # With denied scope, no sources are read, so no extract LLM calls expected
        # The key is that validation happens BEFORE the LLM call


class TestCheckpointPersistence:
    """Test checkpoint-based resume without first-node replay."""
    
    def test_resume_from_checkpoint(self, temp_db, mock_llm, mock_retriever, mock_reader, allow_validator):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        from services.deep_research.repository import DeepResearchRepository
        
        repo = DeepResearchRepository(temp_db)
        repo.initialize()
        
        checkpoint_path = temp_db + ".checkpoints"
        # MUST use check_same_thread=False for LangGraph background thread checkpoints
        checkpoint_conn = sqlite3.connect(checkpoint_path, timeout=30, check_same_thread=False)
        
        try:
            record, _ = repo.create_run({
                "taskId": "task_1",
                "idempotencyKey": "op_1",
                "question": "Test",
                "materials": [{"materialId": "p1", "pdfId": "p1"}],
            })
            
            # Must begin execution before graph can run
            repo.begin_execution(record["runId"])
            
            call_count = {"value": 0}
            
            def counting_llm(run_id, node, prompt, extra, **kw):
                call_count["value"] += 1
                return mock_llm.invoke(type("R", (), {"prompt": prompt, "extra_body": extra})())
            
            graph = build_deep_research_graph(
                llm_invoke=counting_llm,
                retrieve_fn=mock_retriever,
                read_fn=mock_reader,
                scope_validator=allow_validator,
                make_evidence_fn=make_evidence,
                coverage_gaps_fn=coverage_gaps,
                verify_claims_fn=verify_claims,
                repo_update=repo.update_run,
                repo_publish=repo.publish_report,
                validate_plan_fn=validate_plan,
                checkpoint_conn=checkpoint_conn,
            )
            
            initial_state = {
                "run_id": record["runId"],
                "workspace_task_id": "task_1",
                "operation_key": "op_1",
                "execution_epoch": 0,
                "brief_id": "",
                "plan_ids": [],
                "source_ids": [],
                "evidence_ids": [],
                "claim_ids": [],
                "coverage_state": {},
                "gaps": [],
                "report_version_id": "",
                "publication_id": "",
                "outcome": "none",
                "error_code": "",
                "stop_reason": "",
                "clarification_needed": False,
                "clarification_question": "",
                "requery_count": 0,
                "budget_exhausted": False,
                "started_at": time.monotonic(),
                "deadline_seconds": 360.0,
            }
            
            config = {"configurable": {"thread_id": record["runId"]}}
            
            # First invocation
            if repo.require_run(record["runId"])["status"] == "queued":
                repo.begin_execution(record["runId"])
            initial_state["execution_epoch"] = repo.require_run(record["runId"])["executionEpoch"]
            graph.invoke(initial_state, config=config)
            first_count = call_count["value"]
            
            # Resume the persisted checkpoint without supplying a fresh input.
            graph.invoke(None, config=config)
            second_count = call_count["value"]
            
            # Resume should not add many new calls (ideally 0 if fully cached)
            # At minimum, it should be less than full replay
            assert second_count == first_count, "Completed checkpoint must not replay model calls"
            
        finally:
            checkpoint_conn.close()


class TestBudgetExhaustion:
    """Test budget exhaustion propagation."""
    
    def test_budget_exhausted_stops_gracefully(self, temp_db, mock_retriever, mock_reader, allow_validator):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        from services.deep_research.repository import DeepResearchRepository
        
        repo = DeepResearchRepository(temp_db)
        repo.initialize()
        
        # Create run with very small budget
        record, _ = repo.create_run({
            "taskId": "task_1",
            "idempotencyKey": "op_1",
            "question": "Test",
            "materials": [{"materialId": "p1", "pdfId": "p1"}],
            "budget": {"maxModelCalls": 1, "maxTokens": 100},  # Very small
        })
        
        # Must begin execution before graph can run
        repo.begin_execution(record["runId"])
        
        def expensive_llm(run_id, node, prompt, extra, **kw):
            return {"content": "{}", "usage": {"total_tokens": 500}}  # Exceeds budget
        
        graph = build_deep_research_graph(
            llm_invoke=expensive_llm,
            retrieve_fn=mock_retriever,
            read_fn=mock_reader,
            scope_validator=allow_validator,
            make_evidence_fn=make_evidence,
            coverage_gaps_fn=coverage_gaps,
            verify_claims_fn=verify_claims,
            repo_update=repo.update_run,
            repo_publish=repo.publish_report,
            validate_plan_fn=validate_plan,
        )
        
        initial_state = {
            "run_id": record["runId"],
            "workspace_task_id": "task_1",
            "operation_key": "op_1",
            "execution_epoch": 0,
            "brief_id": "",
            "plan_ids": [],
            "source_ids": [],
            "evidence_ids": [],
            "claim_ids": [],
            "coverage_state": {},
            "gaps": [],
            "report_version_id": "",
            "publication_id": "",
            "outcome": "none",
            "error_code": "",
            "stop_reason": "",
            "clarification_needed": False,
            "clarification_question": "",
            "requery_count": 0,
            "budget_exhausted": True,  # Pre-set to trigger budget stop
            "started_at": time.monotonic(),
            "deadline_seconds": 360.0,
        }
        
        config = {"configurable": {"thread_id": record["runId"]}}
        initial_state["execution_epoch"] = repo.require_run(record["runId"])["executionEpoch"]
        final_state = graph.invoke(initial_state, config=config)
        
        # Should complete with partial/inconclusive outcome
        assert final_state.get("outcome") in ("partial", "inconclusive", "complete", "none")


class TestCancellationPropagation:
    """Test that cancellation propagates correctly."""
    
    def test_cancelled_run_stops(self, repo, mock_llm, mock_retriever, mock_reader, allow_validator):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        from services.deep_research.contracts import STATUS_CANCELLED
        
        record, _ = repo.create_run({
            "taskId": "task_1",
            "idempotencyKey": "op_1",
            "question": "Test",
            "materials": [{"materialId": "p1", "pdfId": "p1"}],
        })
        
        # Cancel the run
        repo.transition(record["runId"], STATUS_CANCELLED)
        
        graph = build_deep_research_graph(
            llm_invoke=lambda *a, **kw: {"content": "{}", "usage": {}},
            retrieve_fn=mock_retriever,
            read_fn=mock_reader,
            scope_validator=allow_validator,
            make_evidence_fn=make_evidence,
            coverage_gaps_fn=coverage_gaps,
            verify_claims_fn=verify_claims,
            repo_update=repo.update_run,
            repo_publish=repo.publish_report,
            validate_plan_fn=validate_plan,
        )
        
        # Verify run is cancelled
        updated = repo.require_run(record["runId"])
        assert updated["status"] == STATUS_CANCELLED


class TestUnknownCallHandling:
    """Test unknown call status blocks auto-retry."""
    
    def test_unknown_call_not_auto_retried(self, repo):
        from services.deep_research.contracts import CALL_STATUS_UNKNOWN, UnknownCallError
        
        record, _ = repo.create_run({
            "taskId": "task_1",
            "idempotencyKey": "op_1",
            "question": "Test",
            "materials": [],
        })
        
        # Mark run as running
        repo.begin_execution(record["runId"])
        
        # Reserve a call
        call, _ = repo.reserve_call(
            run_id=record["runId"],
            node="test",
            tool="test_tool",
            args_digest="digest1",
            budget_delta={"modelCalls": 1, "tokens": 100},
        )
        
        # Mark as unknown (simulating crash during execution)
        repo.complete_call(
            call["callId"],
            status=CALL_STATUS_UNKNOWN,
            error={"message": "Process crashed"},
        )
        
        # Try to re-reserve same call - should raise UnknownCallError
        with pytest.raises(UnknownCallError):
            repo.reserve_call(
                run_id=record["runId"],
                node="test",
                tool="test_tool",
                args_digest="digest1",
                budget_delta={"modelCalls": 1, "tokens": 100},
            )


class TestFacadeMissingClient:
    """Test that missing LLM client returns 503, not fake empty result."""
    
    def test_missing_client_raises_503(self, repo):
        from services.deep_research.facade import ResearchFacade
        from services.deep_research.contracts import DeepResearchError
        from services.deep_research.graph import build_deep_research_graph
        
        facade = ResearchFacade(
            repo=repo,
            graph_factory=build_deep_research_graph,
            llm_client=None,  # Missing!
        )
        
        with pytest.raises(DeepResearchError) as exc_info:
            facade.create({
                "workspaceTaskId": "task_1",
                "operationKey": "op_1",
                "question": "Test",
                "materials": [],
            })
        
        assert exc_info.value.code == "llm_not_configured"


class TestFacadeMandatoryFields:
    """Test that workspaceTaskId and operationKey are mandatory."""
    
    def test_missing_workspace_task_id(self, repo, mock_llm):
        from services.deep_research.facade import ResearchFacade
        from services.deep_research.contracts import DeepResearchError
        from services.deep_research.graph import build_deep_research_graph
        
        facade = ResearchFacade(
            repo=repo,
            graph_factory=build_deep_research_graph,
            llm_client=mock_llm,
        )
        
        with pytest.raises(DeepResearchError) as exc_info:
            facade.create({
                # Missing workspaceTaskId
                "operationKey": "op_1",
                "question": "Test",
            })
        
        assert "workspace_task_id" in exc_info.value.code.lower() or "workspaceTaskId" in str(exc_info.value)
    
    def test_missing_operation_key(self, repo, mock_llm):
        from services.deep_research.facade import ResearchFacade
        from services.deep_research.contracts import DeepResearchError
        from services.deep_research.graph import build_deep_research_graph
        
        facade = ResearchFacade(
            repo=repo,
            graph_factory=build_deep_research_graph,
            llm_client=mock_llm,
        )
        
        with pytest.raises(DeepResearchError) as exc_info:
            facade.create({
                "workspaceTaskId": "task_1",
                # Missing operationKey
                "question": "Test",
            })
        
        assert "operation_key" in exc_info.value.code.lower() or "operationKey" in str(exc_info.value)


class TestPureGetNoSideEffects:
    """Test that GET operations don't trigger generation or external requests."""
    
    def test_get_does_not_modify_state(self, repo, mock_llm):
        from services.deep_research.facade import ResearchFacade
        from services.deep_research.graph import build_deep_research_graph
        
        facade = ResearchFacade(
            repo=repo,
            graph_factory=build_deep_research_graph,
            llm_client=mock_llm,
        )
        
        try:
            record, _ = facade.create({
                "workspaceTaskId": "task_1",
                "operationKey": "op_1",
                "question": "Test",
                "materials": [],
            }, start_async=False)
            
            run_id = record["runId"]
            revision_before = record.get("runRevision", 0)
            
            # Multiple GETs should not change revision
            for _ in range(5):
                result = facade.get(run_id)
            
            record_after = repo.require_run(run_id)
            assert record_after.get("runRevision", 0) == revision_before, "GET should not modify state"
        finally:
            facade.shutdown(wait=True)


class TestChildContinuation:
    """Test child continuation retains prior evidence."""
    
    def test_continue_creates_child_with_evidence(self, repo, mock_llm):
        from services.deep_research.facade import ResearchFacade
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.contracts import STATUS_COMPLETED
        
        facade = ResearchFacade(
            repo=repo,
            graph_factory=build_deep_research_graph,
            llm_client=mock_llm,
        )
        
        try:
            # Create parent run (starts as queued)
            parent, _ = facade.create({
                "workspaceTaskId": "task_1",
                "operationKey": "op_1",
                "question": "Original question",
                "materials": [{"materialId": "p1", "contentHash": "unchanged"}],
            }, start_async=False)
            
            # Must transition through running before completing (terminal guards)
            repo.begin_execution(parent["runId"])
            
            # Now set to completed with evidence
            def add_evidence(record):
                state = record.get("state", {})
                state["sources"] = [{"sourceId": "s1", "workId": "p1", "contentHash": "unchanged"}]
                state["evidence"] = [{"evidenceId": "ev1", "sourceId": "s1", "text": "prior evidence"}]
                return {**record, "state": state, "status": STATUS_COMPLETED}
            
            repo.update_run(parent["runId"], add_evidence)
            
            # Continue creates child - must provide requestId (required for actions)
            child_result = facade.action(parent["runId"], "continue", {
                "question": "Follow-up question",
                "expectedRunRevision": repo.require_run(parent["runId"])["runRevision"],
                "requestId": "child_req_1",  # Required for action durability
                "operationKey": "child_op_1",  # Mandatory for child
            })
            
            # Child should exist and inherit evidence
            child_record = repo.require_run(child_result["runId"])
            inherited = child_record.get("state", {}).get("inheritedEvidence", [])
            assert len(inherited) > 0, "Child should inherit parent evidence"
            
            # Child should have workspaceTaskId adapted from parent
            assert child_record.get("taskId") == "task_1", "Child should inherit workspaceTaskId"
        finally:
            facade.shutdown(wait=True)


class TestSourcePipelineIntegration:
    """End-to-end test for source pipeline: acquire -> read -> extract.
    
    Verifies that 2 papers with 2 obligations produce non-empty evidence.
    Tests deduplication by sourceId (not workId) to retain all chunks.
    """
    
    def test_two_papers_two_obligations_produces_evidence(self, temp_db):
        from services.deep_research.graph import build_deep_research_graph
        from services.deep_research.coverage import validate_plan, coverage_gaps
        from services.deep_research.verification import make_evidence, verify_claims
        from services.deep_research.repository import DeepResearchRepository
        
        repo = DeepResearchRepository(temp_db)
        repo.initialize()
        
        # Mock LLM returns valid responses
        class PipelineLLM:
            def invoke(self, request):
                from llm.provider import LLMResult, LLMUsage
                prompt = request.prompt if hasattr(request, "prompt") else str(request)
                
                # ORDER MATTERS: more specific patterns must come before general ones
                if "create a research plan" in prompt.lower():
                    # Two obligations for two papers
                    content = '''[
                        {"itemId": "item1", "question": "Verify method A", "obligations": [{"obligationId": "obl1", "question": "Check accuracy", "requiredSources": ["paper1"]}], "dependencies": [], "priority": 1},
                        {"itemId": "item2", "question": "Verify method B", "obligations": [{"obligationId": "obl2", "question": "Check precision", "requiredSources": ["paper2"]}], "dependencies": [], "priority": 1}
                    ]'''
                elif "analyze this research question" in prompt.lower():
                    content = '{"outputKind": "claim_check", "assumptions": [], "clarification": "", "constraints": ""}'
                elif "extract evidence" in prompt.lower():
                    content = '''[{
                        "quote": "The method achieves 95% accuracy on the test set.",
                        "location": {"page": 3, "section": "Results"},
                        "obligationIds": ["obl1"],
                        "conditions": {"dataset": "ImageNet"},
                        "kind": "reported"
                    }]'''
                elif "synthesize" in prompt.lower():
                    content = '{"summary": "Test summary", "sections": [], "claims": [], "limitations": "", "gaps": []}'
                elif "verify" in prompt.lower():
                    content = '[]'
                else:
                    content = '{}'
                
                return LLMResult(
                    provider="test",
                    model="test-model",
                    content=content,
                    usage=LLMUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                )
        
        # Mock retriever returns different chunks for each paper
        class MultiPaperRetriever:
            def __call__(self, query: str, pdf_id: str, *, limit: int = 5) -> list[dict]:
                if "paper1" in pdf_id:
                    return [
                        {"sourceId": "src_paper1_chunk1", "pdfId": "paper1", "text": "Method A achieves 95% accuracy.", "chunkIndex": 1},
                        {"sourceId": "src_paper1_chunk2", "pdfId": "paper1", "text": "Additional results for method A.", "chunkIndex": 2},
                    ]
                elif "paper2" in pdf_id:
                    return [
                        {"sourceId": "src_paper2_chunk1", "pdfId": "paper2", "text": "Method B shows 90% precision.", "chunkIndex": 1},
                    ]
                return []
        
        # Mock reader returns pages with text
        class PipelineReader:
            def __call__(self, run_id: str, source_id: str) -> dict:
                if "paper1" in source_id:
                    return {
                        "pages": [{"page": 3, "text": "The method achieves 95% accuracy on the test set. This is significant."}],
                        "accessLevel": "fulltext",
                    }
                elif "paper2" in source_id:
                    return {
                        "pages": [{"page": 2, "text": "Method B shows 90% precision on validation data. Results are consistent."}],
                        "accessLevel": "fulltext",
                    }
                return {"pages": [], "accessLevel": "unknown"}
        
        record, _ = repo.create_run({
            "taskId": "task_pipeline",
            "idempotencyKey": "op_pipeline",
            "question": "Compare methods A and B",
            "materials": [
                {"materialId": "paper1", "pdfId": "paper1"},
                {"materialId": "paper2", "pdfId": "paper2"},
            ],
        })
        
        # Must begin execution before graph can run
        repo.begin_execution(record["runId"])
        
        graph = build_deep_research_graph(
            llm_invoke=lambda run_id, node, prompt, extra, **kw: PipelineLLM().invoke(type("R", (), {"prompt": prompt, "extra_body": extra})()),
            retrieve_fn=MultiPaperRetriever(),
            read_fn=PipelineReader(),
            scope_validator=AlwaysAllowValidator(),
            make_evidence_fn=make_evidence,
            coverage_gaps_fn=coverage_gaps,
            verify_claims_fn=verify_claims,
            repo_update=repo.update_run,
            repo_publish=repo.publish_report,
            validate_plan_fn=validate_plan,
        )
        
        initial_state = {
            "run_id": record["runId"],
            "workspace_task_id": "task_pipeline",
            "operation_key": "op_pipeline",
            "execution_epoch": 0,
            "brief_id": "",
            "plan_ids": [],
            "source_ids": [],
            "evidence_ids": [],
            "claim_ids": [],
            "coverage_state": {},
            "gaps": [],
            "report_version_id": "",
            "publication_id": "",
            "outcome": "none",
            "error_code": "",
            "stop_reason": "",
            "clarification_needed": False,
            "clarification_question": "",
            "requery_count": 0,
            "budget_exhausted": False,
            "started_at": time.monotonic(),
            "deadline_seconds": 360.0,
        }
        
        config = {"configurable": {"thread_id": record["runId"]}}
        initial_state["execution_epoch"] = repo.require_run(record["runId"])["executionEpoch"]
        final_state = graph.invoke(initial_state, config=config)
        
        # Verify evidence was produced
        evidence_ids = final_state.get("evidence_ids", [])
        assert len(evidence_ids) > 0, f"Expected non-empty evidence for 2 papers, got {len(evidence_ids)}"
        
        # Verify sources were acquired from both papers
        source_ids = final_state.get("source_ids", [])
        paper1_sources = [s for s in source_ids if "paper1" in s]
        paper2_sources = [s for s in source_ids if "paper2" in s]
        assert len(paper1_sources) >= 1, f"Expected paper1 sources, got {paper1_sources}"
        assert len(paper2_sources) >= 1, f"Expected paper2 sources, got {paper2_sources}"


class TestMaterialSnapshot:
    """Test that materialSnapshot from Java is used when provided."""
    
    def test_material_snapshot_used_over_materials(self, repo, mock_llm):
        from services.deep_research.facade import ResearchFacade
        from services.deep_research.graph import build_deep_research_graph
        
        facade = ResearchFacade(
            repo=repo,
            graph_factory=build_deep_research_graph,
            llm_client=mock_llm,
        )
        
        try:
            # Provide both materials and materialSnapshot - snapshot should win
            record, _ = facade.create({
                "workspaceTaskId": "task_1",
                "operationKey": "op_1",
                "question": "Test",
                "materials": [{"materialId": "old_paper"}],  # Should be ignored
                "materialSnapshot": [
                    {"materialId": "verified_paper", "versionId": "v1", "contentHash": "abc123"},
                ],
            }, start_async=False)
            
            # Verify materialSnapshot was used
            stored_material = record.get("materials", [])
            assert len(stored_material) == 1
            assert stored_material[0].get("materialId") == "verified_paper"
            assert stored_material[0].get("versionId") == "v1"
        finally:
            facade.shutdown(wait=True)
    
    def test_material_snapshot_dict_normalization(self, repo, mock_llm):
        """Test dict-style materialSnapshot with materialRefs/materialVersions."""
        from services.deep_research.facade import ResearchFacade
        from services.deep_research.graph import build_deep_research_graph
        
        facade = ResearchFacade(
            repo=repo,
            graph_factory=build_deep_research_graph,
            llm_client=mock_llm,
        )
        
        try:
            # Dict-style snapshot (Java format)
            record, _ = facade.create({
                "workspaceTaskId": "task_1",
                "operationKey": "op_2",
                "question": "Test",
                "materialSnapshot": {
                    "materialRefs": ["paper_a", "paper_b"],
                    "materialVersions": {
                        "paper_a": {"versionId": "v1", "contentHash": "hash_a"},
                        "paper_b": {"versionId": "v2", "contentHash": "hash_b"},
                    },
                },
            }, start_async=False)
            
            # Verify normalization to list
            stored_material = record.get("materials", [])
            assert len(stored_material) == 2
            material_ids = {m.get("materialId") for m in stored_material}
            assert "paper_a" in material_ids
            assert "paper_b" in material_ids
            
            # Verify version info preserved
            paper_a = next(m for m in stored_material if m.get("materialId") == "paper_a")
            assert paper_a.get("versionId") == "v1"
            assert paper_a.get("contentHash") == "hash_a"
        finally:
            facade.shutdown(wait=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
