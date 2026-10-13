"""Injectable domain tools for Deep Research v2.

All retrieval and model calls are tracked via repository call ledger.
Scope validation happens BEFORE every retrieval/model send.
No hidden retries or untracked helper calls.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Protocol

from services.deep_research.contracts import (
    CALL_STATUS_FAILED,
    CALL_STATUS_SUCCEEDED,
    DeepResearchError,
    digest,
)

logger = logging.getLogger(__name__)


# ── Protocols for Injectable Dependencies ──────────────────────────────────────

class ScopeValidator(Protocol):
    """Validates material authorization before EVERY retrieval/model send.
    
    Production facade needs authoritative Java callback or validated scope
    revision endpoint. Default validator cannot silently authorize revoked
    sources - fail closed if unavailable.
    """
    def __call__(self, run_id: str, material_id: str) -> bool: ...


class Retriever(Protocol):
    """Local retrieval interface matching research_executor.retrieve_current_paper_evidence.
    
    Uses keyword limit parameter (not positional) for clarity.
    """
    def __call__(self, query: str, pdf_id: str, *, limit: int = 5) -> list[dict[str, Any]]: ...


class SourceReader(Protocol):
    """Read source content from trusted snapshot."""
    def __call__(self, run_id: str, source_id: str) -> dict[str, Any]: ...


class LLMInvoker(Protocol):
    """Direct structured LLM call with budget tracking."""
    def __call__(self, prompt: str, extra_body: dict[str, Any]) -> dict[str, Any]: ...


# ── Default Implementations ────────────────────────────────────────────────────

class DefaultScopeValidator:
    """Fail-closed validator that checks material against snapshot.
    
    In production, this MUST be replaced with authoritative Java callback
    or validated scope revision endpoint. This default implementation only
    checks against the initial material snapshot and cannot detect revocations.
    """
    
    def __init__(self, get_run_fn: Callable[[str], dict | None]):
        self._get_run = get_run_fn
    
    def __call__(self, run_id: str, material_id: str) -> bool:
        record = self._get_run(run_id)
        if not record:
            return False
        
        materials = record.get("materials", [])
        allowed_ids = {m.get("materialId") for m in materials}
        
        # Fail closed: material must be explicitly in snapshot
        return material_id in allowed_ids


class TrackedRetriever:
    """Wraps retrieval with call ledger tracking and scope validation."""
    
    def __init__(
        self,
        base_retriever: Retriever,
        scope_validator: ScopeValidator,
        reserve_call_fn: Callable[..., tuple],
        complete_call_fn: Callable[..., dict],
    ):
        self._retrieve = base_retriever
        self._validate = scope_validator
        self._reserve = reserve_call_fn
        self._complete = complete_call_fn
    
    def __call__(self, run_id: str, query: str, pdf_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        # Validate scope BEFORE retrieval
        if not self._validate(run_id, pdf_id):
            logger.warning("Scope validation failed for %s in run %s", pdf_id, run_id)
            return []
        
        args_digest = digest({"query": query, "pdfId": pdf_id, "limit": limit})
        
        # Reserve call BEFORE network
        try:
            call_record, reused = self._reserve(
                run_id=run_id,
                node="acquire",
                tool="retrieve",
                args_digest=args_digest,
                budget_delta={"modelCalls": 0, "tokens": 0},  # Retrieval doesn't count as model call
            )
            
            if reused:
                result = call_record.get("result") or {}
                return result.get("items", []) if isinstance(result, dict) else []
            
        except Exception as exc:
            logger.exception("Failed to reserve retrieve call for run %s", run_id)
            return []
        
        # Execute retrieval
        try:
            items = self._retrieve(query, pdf_id, limit=limit)
            
            # Normalize source IDs via full hash (not truncated)
            normalized = []
            for item in items:
                source_id = item.get("sourceId", "")
                if not source_id:
                    # Generate stable ID from content - FULL hash, not [:16]
                    content_key = f"{item.get('pdfId', '')}:{item.get('chunkIndex', 0)}:{item.get('text', '')}"
                    source_id = "src_" + hashlib.sha256(content_key.encode()).hexdigest()
                
                normalized.append({
                    **item,
                    "sourceId": source_id,
                    "sourceWorkId": item.get("pdfId", pdf_id),
                    "contentHash": item.get("contentHash") or hashlib.sha256(item.get("text", "").encode()).hexdigest(),
                })
            
            # Complete call with result
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_SUCCEEDED,
                result={"items": normalized},
                reservation_token=call_record.get("reservationToken"),
            )
            
            return normalized
            
        except Exception as exc:
            logger.exception("Retrieval failed for run %s", run_id)
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_FAILED,
                error={"message": str(exc)},
                reservation_token=call_record.get("reservationToken"),
            )
            return []


class TrackedSourceReader:
    """Read source content with scope validation and ledger tracking.
    
    Note: Scope validation here uses source_id directly. The graph node
    does authoritative validation using work_id (materialId) before calling
    this reader, so this is a secondary check.
    """
    
    def __init__(
        self,
        base_reader: SourceReader,
        scope_validator: ScopeValidator,
        reserve_call_fn: Callable[..., tuple],
        complete_call_fn: Callable[..., dict],
    ):
        self._read = base_reader
        self._validate = scope_validator
        self._reserve = reserve_call_fn
        self._complete = complete_call_fn
    
    def __call__(self, run_id: str, source_id: str, work_id: str | None = None) -> dict[str, Any]:
        # Validate scope BEFORE read
        # Use work_id if provided (for material-based validation), else source_id
        validate_id = work_id if work_id else source_id
        if not self._validate(run_id, validate_id):
            logger.warning("Scope validation failed for source %s (work %s) in run %s", source_id, validate_id, run_id)
            return {}
        
        args_digest = digest({"sourceId": source_id})
        
        try:
            call_record, reused = self._reserve(
                run_id=run_id,
                node="read",
                tool="read_source",
                args_digest=args_digest,
                budget_delta={"modelCalls": 0, "tokens": 0},
            )
            
            if reused:
                return call_record.get("result") or {}
            
        except Exception as exc:
            logger.exception("Failed to reserve read call for source %s", source_id)
            return {}
        
        try:
            content = self._read(run_id, source_id)
            
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_SUCCEEDED,
                result=content,
                reservation_token=call_record.get("reservationToken"),
            )
            
            return content
            
        except Exception as exc:
            logger.exception("Read failed for source %s", source_id)
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_FAILED,
                error={"message": str(exc)},
                reservation_token=call_record.get("reservationToken"),
            )
            return {}


class TrackedLLMInvoker:
    """Direct LLM calls with reservation BEFORE network and usage tracking.
    
    All model calls use get_structured_llm().invoke(LLMRequest(...)).
    No hidden calls/retries. Ambiguous timeout = unknown, do not auto retry.
    Send-only try separate from settlement; never catch completion exception
    then overwrite as failed.
    """
    
    def __init__(
        self,
        llm_client: Any,  # LLM provider instance
        reserve_call_fn: Callable[..., tuple],
        complete_call_fn: Callable[..., dict],
        max_input_tokens: int = 24000,
        request_options: Callable | None = None,
    ):
        self._client = llm_client
        self._reserve = reserve_call_fn
        self._complete = complete_call_fn
        self._max_input = max_input_tokens
        self._request_options = request_options
    
    def __call__(
        self,
        run_id: str,
        node: str,
        prompt: str,
        extra_body: dict[str, Any] | None = None,
        use_reserve: bool = False,
    ) -> dict[str, Any]:
        from llm.provider import LLMRequest, LLMProviderError

        if self._request_options:
            extra_body = self._request_options(node, dict(extra_body or {}))
        
        # Full prompt digest for stable IDs - NOT truncated
        args_digest = digest({"prompt": prompt, "extra": extra_body or {}})
        
        # Reserve a conservative UTF-8 byte bound, then settle measured usage.
        prompt_byte_length = len(prompt.encode("utf-8"))
        estimated_input = prompt_byte_length + 1024  # Bound the fixed system message and framing too.
        max_output = (extra_body or {}).get("max_tokens", 2000)
        
        # Reject overlarge input BEFORE reserve - enforce UTF-8 byte size limit
        # Reject instead of silently clipping evidence or under-reserving it.
        max_byte_length = self._max_input
        if prompt_byte_length > max_byte_length:
            raise ValueError(
                f"Prompt too large: {prompt_byte_length} bytes (~{estimated_input} tokens) "
                f"exceeds max {max_byte_length} bytes (~{self._max_input} tokens)"
            )
        
        # Reserve BEFORE network
        call_record, reused = self._reserve(
            run_id=run_id,
            node=node,
            tool="llm_invoke",
            args_digest=args_digest,
            budget_delta={
                "modelCalls": 1,
                "tokens": estimated_input + max_output,
            },
            use_reserve=use_reserve,
        )
        
        if reused:
            return call_record.get("result", {"content": "", "usage": {}})
        
        # Execute LLM call - send-only try
        request = LLMRequest(
            prompt=prompt,
            extra_body=extra_body or {},
            timeout_seconds=(extra_body or {}).get("timeout_seconds"),
        )
        
        try:
            client = self._client.for_node(node) if callable(getattr(type(self._client), "for_node", None)) else self._client
            result = client.invoke(request)
        except LLMProviderError as exc:
            # LLMProviderError with no status_code means unknown (timeout/connection)
            # Rejected HTTP status means failed
            is_unknown = exc.status_code is None or exc.retryable
            self._complete(
                call_record["callId"],
                status="unknown" if is_unknown else CALL_STATUS_FAILED,
                error={"message": str(exc), "type": "provider_error", "status_code": exc.status_code},
                reservation_token=call_record.get("reservationToken"),
            )
            raise
        except Exception as exc:
            # Timeout/connection errors = unknown, do not auto retry
            error_msg = str(exc).lower()
            is_timeout = "timeout" in error_msg or "timed out" in error_msg or "connection" in error_msg
            
            self._complete(
                call_record["callId"],
                status="unknown" if is_timeout else CALL_STATUS_FAILED,
                error={"message": str(exc), "type": "timeout" if is_timeout else "error"},
                reservation_token=call_record.get("reservationToken"),
            )
            raise
        
        # Settlement - separate from send try
        actual_tokens = estimated_input + max_output
        if hasattr(result, "usage") and result.usage and not result.usage.estimated:
            actual_tokens = result.usage.total_tokens
        
        response = {
            "content": result.content if hasattr(result, "content") else "",
            "provider": getattr(result, "provider", ""),
            "model": getattr(result, "model", ""),
            "finishReason": getattr(result, "finish_reason", None),
            "usage": {
                "total_tokens": actual_tokens,
                "input_tokens": result.usage.input_tokens if hasattr(result.usage, "input_tokens") else 0,
                "output_tokens": result.usage.output_tokens if hasattr(result.usage, "output_tokens") else 0,
            },
        }
        
        # Settle with actual usage delta
        token_delta = actual_tokens - (estimated_input + max_output)
        settlement_delta = {"tokens": token_delta} if token_delta != 0 else {}
        
        self._complete(
            call_record["callId"],
            status=CALL_STATUS_SUCCEEDED,
            result=response,
            reservation_token=call_record.get("reservationToken"),
            budget_delta=settlement_delta,
        )
        
        return response


# ── External Academic Integration ──────────────────────────────────────────────

class ExternalAcademicAdapter:
    """Integrates AcademicSourceClient with call ledger.
    
    Each network call (discover/fulltext) is separately ledgered.
    Abstract vs fulltext distinction preserved.
    """
    
    def __init__(
        self,
        academic_client: Any,  # AcademicSourceClient instance
        reserve_call_fn: Callable[..., tuple],
        complete_call_fn: Callable[..., dict],
    ):
        self._client = academic_client
        self._reserve = reserve_call_fn
        self._complete = complete_call_fn
    
    def discover(self, run_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
        args_digest = digest({"query": query, "limit": limit, "type": "discover"})
        
        try:
            call_record, reused = self._reserve(
                run_id=run_id,
                node="acquire",
                tool="external_discover",
                args_digest=args_digest,
                budget_delta={"externalSearches": 1},
            )
            
            if reused:
                return (call_record.get("result") or {}).get("items", [])
            
        except Exception as exc:
            logger.exception("Failed to reserve external discover call")
            return []
        
        try:
            results = self._client.discover(query, limit)
            
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_SUCCEEDED,
                result={"items": results},
                reservation_token=call_record.get("reservationToken"),
            )
            
            return results
            
        except Exception as exc:
            logger.exception("External discover failed")
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_FAILED,
                error={"message": str(exc)},
                reservation_token=call_record.get("reservationToken"),
            )
            return []
    
    def fetch_fulltext(self, run_id: str, arxiv_id: str) -> dict[str, Any]:
        args_digest = digest({"arxivId": arxiv_id, "type": "fulltext"})
        
        try:
            call_record, reused = self._reserve(
                run_id=run_id,
                node="read",
                tool="external_fulltext",
                args_digest=args_digest,
                budget_delta={"fulltextFetches": 1},
            )
            
            if reused:
                return call_record.get("result") or {}
            
        except Exception as exc:
            logger.exception("Failed to reserve external fulltext call")
            return {}
        
        try:
            result = self._client.fetch_fulltext(arxiv_id)
            
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_SUCCEEDED,
                result=result,
                reservation_token=call_record.get("reservationToken"),
            )
            
            return result
            
        except Exception as exc:
            logger.exception("External fulltext fetch failed")
            self._complete(
                call_record["callId"],
                status=CALL_STATUS_FAILED,
                error={"message": str(exc)},
                reservation_token=call_record.get("reservationToken"),
            )
            return {}


# ── Semantic Check Adapter ─────────────────────────────────────────────────────

class BudgetedSemanticChecker:
    """Semantic verification using reserved model calls.
    
    Checks factual support and the logic of proposed experiments separately.
    Uses reserve pool explicitly.
    """
    
    def __init__(
        self,
        llm_invoker: TrackedLLMInvoker,
        run_id: str,
        metric_domains=None,
    ):
        self._invoke = llm_invoker
        self._run_id = run_id
        self._metric_domains = metric_domains
    
    def __call__(self, claims: list[dict], evidence: list[dict]) -> list[dict]:
        return self._check(claims, evidence, [], 'verify')

    def check_revisions(self, claims, evidence, accepted_context):
        """Retain design definitions without rechecking or promoting context facts."""
        targets = {c['claimId'] for c in claims}
        context = [c for c in accepted_context if c.get('claimId') not in targets
                   and c.get('kind') in {'proposal', 'suggestion', 'hypothesis'}]
        return self._check(claims, evidence, context, 'verify_repair')

    def _check(self, claims, evidence, accepted_context, node):
        if not claims:
            return []
        # Separate concrete configuration from scientific interpretation while
        # sharing all definitions. A repair stays one bounded verification call.
        proposals = [c for c in claims if c.get('kind') in {'proposal', 'suggestion', 'hypothesis'}]
        facts = [c for c in claims if c.get('kind') not in {'proposal', 'suggestion', 'hypothesis'}]
        config_roles = {'groups', 'controls', 'data', 'budget', 'steps', 'metrics'}
        config = [c for c in proposals if c.get('designRole') in config_roles] if node == 'verify' else []
        science = [c for c in proposals if c not in config]
        science_node = 'verify_design_science' if node == 'verify' else 'verify_repair_design_science'
        proposal_batches = ([(config, 'verify_design_config')] if config else []) + ([(science, science_node)] if science else [])
        fact_slots = max(1, 3 - len(proposal_batches))
        # Keep small answers in one request, leaving reserve for the final
        # coverage audit after a revision. Per-claim evidenceRefs remain binding.
        size = max(3, (len(facts) + fact_slots - 1) // fact_slots)
        batches = proposal_batches + [(facts[i:i + size], node) for i in range(0, len(facts), size)]
        verdicts = []
        for batch, batch_node in batches:
            targets = {c['claimId'] for c in batch}
            context = [{'claimId': c.get('claimId'), 'text': c.get('text'), 'kind': c.get('kind'),
                        'conditions': c.get('conditions', {}), 'designRole': c.get('designRole'),
                        'executionSpec': c.get('executionSpec'), 'designContractVersion': c.get('designContractVersion')}
                       for c in [*accepted_context, *proposals] if c['claimId'] not in targets]
            verdicts.extend(self._check_batch(batch, evidence, context, node=batch_node))
        by_id = {v['claimId']: v for v in verdicts}
        return [by_id[c['claimId']] for c in claims]

    def _check_batch(self, claims: list[dict], evidence: list[dict], proposal_context: list[dict], *, node='verify') -> list[dict]:
        from services.deep_research.selection import surrounding_context
        metric_domains = self._metric_domains() if callable(self._metric_domains) else self._metric_domains
        from services.deep_research.verification_aliases import (
            encode_verification_inputs, restore_visible_evidence, restore_verdict_evidence)
        wire_claims, wire_evidence, reverse_aliases = encode_verification_inputs(claims, evidence)
        from services.deep_research.execution_materialization import verification_claim_view
        wire_claims = [verification_claim_view(c) for c in wire_claims]
        wire_context = [verification_claim_view(c) for c in proposal_context]
        # Format claims and evidence for checking
        claims_text = json.dumps([{
            "claimId": c.get("claimId"),
            "text": c.get("text", ""),
            "kind": c.get("kind"),
            "evidenceRefs": c.get("evidenceRefs", []),
            "conditions": c.get("conditions", {}),
            "tableBindings": c.get("tableBindings", []),
            "designRole": c.get("designRole"),
            "executionSpec": c.get("executionSpec"),
            "designContractVersion": c.get("designContractVersion"),
        } for c in wire_claims], ensure_ascii=False, separators=(',', ':'))
        
        referenced = {ref for claim in wire_claims for ref in claim.get("evidenceRefs", [])}
        evidence_map = {e["evidenceId"]: {"quote": e.get("quote", ""), "conditions": e.get("conditions", {}),
                        "sourceContext": surrounding_context(e), "location": e.get("location", {}),
                        "sourceTitle": e.get("sourceTitle", ""),
                        "tableData": e.get("tableData"),
                        "workId": e.get("sourceWorkId"), "versionId": e.get("sourceVersionId"),
                        "accessLevel": e.get("accessLevel")} for e in wire_evidence if e["evidenceId"] in referenced}
        from uuid import uuid4
        from services.deep_research.prompt_budget import fit_evidence_prompt
        evidence_text = uuid4().hex
        
        prompt = f"""Verify these claims against the evidence. For each claim, determine if the evidence supports it.

Claims:
{claims_text}

Evidence:
{evidence_text}

Return JSON array of verdicts:
[{{"claimId": "...", "status": "passed" or "failed", "reason": "..."}}]

Be strict: evidence must directly support EVERY clause and condition of the specific claim.
For each claim use ONLY its own evidenceRefs; evidence cited by another claim is not its support.
Resolve the subject of EVERY cited clause from its preceding and following sentences.
In contrasts (however, in contrast, on the contrary), distinguish the baseline from
the proposed method. An "it" or "this" is not automatically the paper's own method.
A passage criticizing a baseline cannot support a limitation assigned to the proposed
method. If the subject is unresolved in the supplied context, fail that assertion.
For each verdict's reason, briefly identify the asserted subject, the source subject,
and any mismatch before judging support; do not merely restate the claimed sentence.
Check each number's method, dataset, metric, unit and experimental setting, not just its presence.
SourceContext is the original passage around the exact quote, not additional permission to invent facts.
Use it to detect lost experimental scope. A numeric comparison must identify its dataset/protocol
or explicitly say that those conditions are unknown in the available passage. Reject an isolated
supplemental or ablation result presented as the paper's general outcome. If necessary, remove
the numerical example rather than approving it without its scope.
Reject claims that confuse a similar PSNR with unchanged image quality, or infer universal/exclusive
conditions from a limited tested range. Missing passages do not prove the authors never tested it.
For inference, verify the stated premises and reasoning; reject invented calculations or generalization.
For proposal/suggestion/hypothesis, do not demand that an unexecuted experiment already has results.
Instead verify that it is clearly prospective, contains no disguised established fact, and is logically valid.
Check formulas, metric direction, conditional versus averaged factorial effects, and sign interpretations.
An interaction formula must define whether larger values mean better quality or greater loss; never use
one sign interpretation for PSNR/SSIM and LPIPS together. Non-significance does not prove no effect.
Truncating coefficients is a proposed intervention, not automatically the paper's distillation procedure.
Do not accept vague connections. A partly supported claim must fail until its wording is narrowed."""

        if all(c.get('kind') in {'proposal', 'suggestion', 'hypothesis'} for c in claims):
            # Do not inherit factual-entailment instructions for unexecuted choices.
            prompt = f'''Verify these claims as a prospective experimental design. These targets are suggestions,
not claims that the papers already performed this experiment. A proposed seed, split,
factor level, recovery budget or measurement protocol needs NO quotation proving that
the authors used it. Judge whether it is explicit, executable and coherent. Never fail
a clearly labeled proposed choice merely because it is absent from the paper.
Check scientific validity as well as completeness. A role can share definitions and
protocol details with other target/context proposals; do not demand needless repetition.
If a target also asserts an existing paper fact, check only that factual clause against
its own evidenceRefs; shared context is not factual evidence. Reject invented paper facts.

Claims:
{claims_text}

Evidence:
{evidence_text}

Return only a JSON array, one verdict per target:
[{{"claimId":"ID","status":"passed" or "failed","reason":"brief specific finding","designAudit":{{}}}}]
Missing configuration, contradictory choices and invalid parameter syntax fail.
Do not require an unexecuted experiment to have results. Do not judge context claims as targets.'''
        
        if any(c.get('designContractVersion') == 2 for c in [*claims, *proposal_context]):
            prompt += ('\nFor groups, every necessary numeric threshold, rate and degree must appear as '
                       'a numeric parameter with an actual value. Audit each action against its parameters: '
                       'an omitted required parameter or numeric threshold disguised as a categorical choice '
                       'fails. A named symbol in an operation is not a chosen value. Check consistency with '
                       'the rendered control/treatment values and shared definitions.')
            prompt += '\nexecutionSpec is proposed configuration, not paper evidence. The application renders ' \
                      'its exact values into the published protocol; that deterministic suffix is not repeated here. ' \
                      'Check EVERY field and original claim text for concrete meaning and consistency: dataset, ' \
                      'scene selection, split, seeds, replication, formulas and uncertainty. Original prose must ' \
                      'not contradict fields; do not require duplicate prose for an explicit typed choice. Structural validation ' \
                      'does not certify meaningful choices. A scene-seed pair is not automatically independent ' \
                      'of another seed from the same scene; fixed checkpoints with no retraining do not produce ' \
                      'independent training replicates. Require paired groups within units and resample actual ' \
                      'independent clusters. Quoting a vague choice does not make it concrete.'

        if any(c.get('designContractVersion') == 2 and c.get('designRole') == 'data' for c in claims):
            prompt += '''
For each v2 data target, distinguish freely proposed parameters from existing data availability.
An inherited subset is NOT the entire parent dataset. Resolve the exact dataset/subset,
unit and membership from that target's own fulltext evidenceRefs. "Same scenes as [reference]"
alone establishes neither count nor names. Unknown availability must fail, not be guessed.
A passed data verdict MUST additionally include dataAvailability:
{"evidenceId":"own fulltext ID","quote":"exact passage from its quote",
 "scopeQuote":"exact words within that passage identifying the relevant data/subset",
 "availableCount":2,"countQuote":"two","availableNames":[]}
This is schema, not evidence. For sorted_first, bind the actual available unit count using
its exact numeric token (plain decimal digits or English one..twenty), and ensure requested
count does not exceed it. Never quote a count of views, methods, or another dataset as scenes.
For all mode, the proposed count must equal the entire count of that EXACT dataset/subset.
Full-set selection needs no invented ordering or per-unit name list when the quoted complete
benchmark scope is unambiguous. An inherited subset whose identity remains unresolved fails.
For named mode, instead provide availableNames with actual selected names explicitly present
in the quoted passage; count fields may be omitted. Verify name membership and subset identity.
Do not infer dataset existence/capacity from a proposed choice or another proposal. Missing
fulltext support or unresolved subset identity fails even when every setting is concrete.
The dataAvailability object is an internal audit, not new experimental results.
'''

        if any(c.get("kind") in {"proposal", "suggestion", "hypothesis"} for c in claims):
            from services.deep_research.experimental_reasoning import FACTORIAL_REFERENCE, design_requirements
            if node == 'verify_design_config':
                prompt += '\nCheck that the target configurations are executable and mutually consistent. ' \
                          'Check parameter syntax, explicit intervention levels, split/seed rules, budgets ' \
                          'and measurement procedures. Reject a placeholder such as "pre-register a value". ' \
                          'Use the shared scientific definitions for consistency, but do not rederive their ' \
                          'formulas or issue verdicts for context statements.'
            else:
                prompt += '\nCheck target scientific assertions against the complete proposed configuration. ' \
                          'Reject incompatible sampling units, insufficient independent replication, invalid ' \
                          'metric signs and decision rules. Explain a failure concisely; no full derivation ' \
                          'is needed in the returned reason. Shared context is not itself verified by this call.\n' \
                          + FACTORIAL_REFERENCE
            prompt += '\nOther proposed statements, for consistency only (not evidence and not verdict targets):\n' + json.dumps(wire_context, ensure_ascii=False, separators=(',', ':'))
            if any(c.get('designRole') for c in claims):
                prompt += '\nFor every designRole, verify BOTH logical correctness AND fulfillment of its entire ' \
                          'requirement below. A role label, heading or vague promise is not fulfillment. Fail the ' \
                          'specific claim if its budget, split, procedure or decision criterion is unspecified. ' \
                          'Use the other target claims for shared definitions but not as factual evidence.\n' + design_requirements(metric_domains)
                from services.deep_research.design_audit import required_design_slots
                prompt += ('\nPassed verdicts require FLAT designAudit with these slot keys: '
                           + json.dumps(required_design_slots(metric_domains), separators=(',', ':'))
                           + '. Each slot is {"claimId":"target/context proposal ID","quote":"exact concrete choice"}. '
                           'Missing/vague choices use null and fail. Paper facts cannot supply configuration. '
                           'Check that each choice fulfills the entire slot, not mere keyword presence. '
                           'Promises such as "fixed split", "same seed", "measure FPS" or "predeclare a tolerance" fail. '
                           'For discontinuous text use {"quotes":[{"claimId":"ID","quote":"exact substring"}]} '
                           'with 1 to 32 segments. Copy punctuation exactly; never join, summarize or rewrite. '
                           'Every segment must match its source and together cover the whole slot. No mixed forms.')
                prompt += ('\nFor typed executionSpec choices prefer {"fields":[{"claimId":"target/context ID",'
                           '"path":["executionSpec","factors",0,"treatment","parameters",0,"value"],"value":0.5}]}. '
                           'Copy the exact existing typed value; path elements are object keys or zero-based list indices. '
                           'Use 1-32 bindings. Allowed slot roots: intervention_levels=factors (groups); '
                           'scenes=dataset/scenes, split=split, seeds=seeds, sampling_unit=independentUnit (data); '
                           'effects=effects, uncertainty=uncertainty, decision_rule=decision (analysis). '
                           'Other slots require quotes. Do not mix fields with quote/quotes. All bindings together '
                           'must substantiate the entire slot; valid fields do not prove scientific correctness.')
                required_slots = required_design_slots(metric_domains)
                skeleton = [{'claimId': c['claimId'], 'status': 'failed',
                    'reason': 'replace with a concise concrete finding',
                    'designAudit': {slot: None for slot in required_slots.get(c.get('designRole'), ())}}
                    for c in claims]
                prompt += '\nFill this exact per-target response skeleton. Change status only after checking. ' \
                          'Replace a null slot with a supported quote, quotes or fields binding ' \
                          'only if such a choice is already written; otherwise keep null and fail. ' \
                          'Do not replace slot keys with role names or arrays. Symbolic placeholders such as ' \
                          'an unspecified threshold or degree do not define actual intervention levels.\n' \
                          + json.dumps(skeleton, ensure_ascii=False)
        template = prompt
        prompt, visible_evidence = fit_evidence_prompt(
            [{"evidenceId": key, **value} for key, value in evidence_map.items()],
            lambda rows: template.replace(evidence_text, json.dumps({
                row["evidenceId"]: {key: value for key, value in row.items() if key != "evidenceId"}
                for row in rows}, ensure_ascii=False, separators=(',', ':')), 1))
        visible_evidence = restore_visible_evidence(visible_evidence, reverse_aliases)
        try:
            result = self._invoke(
                run_id=self._run_id,
                node=node,
                prompt=prompt,
                extra_body={"max_tokens": 4000, "temperature": 0.0},
                use_reserve=True,  # Use reserve pool for verification
            )
            
            content = result.get("content", "[]")
            from services.deep_research.graph import _safe_parse_json
            parsed = _safe_parse_json(content)
            
            expected = {claim['claimId'] for claim in claims}
            if (result.get('finishReason') == 'length' or not isinstance(parsed, list)
                    or len(parsed) != len(expected)
                    or any(not isinstance(v, dict) or v.get('status') not in {'passed', 'failed'}
                           for v in parsed)
                    or {v.get('claimId') for v in parsed} != expected):
                raise DeepResearchError('invalid_verification_response',
                                        '声明核验未完整返回；不能据此判断材料不足。')
            from services.deep_research.design_audit import validate_design_audit
            parsed = [restore_verdict_evidence(v, reverse_aliases) for v in parsed]
            by_id = {c['claimId']: c for c in claims}
            visible_ids = {row["evidenceId"] for row in visible_evidence}
            for verdict in parsed:
                if verdict['status'] != 'passed':
                    continue
                target = by_id[verdict['claimId']]
                if set(target.get('evidenceRefs', [])) - visible_ids:
                    verdict['status'] = 'failed'
                    verdict['reason'] = '请求容量限制导致引用证据未完整提供，不能确认该声明。'
                    continue
                missing = validate_design_audit(by_id[verdict['claimId']], verdict, [*claims, *proposal_context], metric_domains)
                if missing:
                    verdict['status'] = 'failed'
                    verdict['reason'] = '实验方案缺少可核对的具体配置：' + ', '.join(missing)
                    continue
                from services.deep_research.data_availability import validate_data_availability
                availability_errors = validate_data_availability(target, verdict, visible_evidence)
                if availability_errors:
                    verdict['status'] = 'failed'
                    verdict['reason'] = '所选数据范围或可用数量尚未核实：' + ', '.join(availability_errors)
            return parsed
            
        except DeepResearchError:
            # Preserve budget, authorization and unknown-call recovery semantics.
            # A missing verdict is an execution failure, not evidence of insufficiency.
            raise
        except Exception as exc:
            logger.exception("Semantic check failed for run %s", self._run_id)
            raise DeepResearchError('invalid_verification_response',
                                    '声明核验未完成；已取得的资料仍保留。') from exc
