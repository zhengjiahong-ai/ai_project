"""Agent debate orchestrator — Jaccard similarity, finding clustering, and TypedDict definitions.

This module provides the foundational building blocks for multi-agent debate:
- TypedDict type definitions for debate data structures
- Jaccard similarity computation between sets
- Finding similarity and greedy clustering utilities
- DebateOrchestrator for multi-agent debate orchestration
- synthesize_consensus for deterministic consensus synthesis
"""

from __future__ import annotations

import logging
from typing import ClassVar, TypedDict

from services.agent_langgraph import run_agent_graph

logger = logging.getLogger(__name__)


# ── TypedDict type definitions ──────────────────────────────────────────────


class AgentAnalysis(TypedDict):
    """Analysis produced by a single agent during the debate."""

    agent_index: int
    temperature: float
    paper_ids: list
    findings: list
    evidence_items: list
    weighted_evidence: list
    cross_paper_insights: list
    resolved_conflicts: list
    draft_report: str
    credibility_mean: float


class DissentItem(TypedDict):
    """A dissenting opinion from an agent on a particular finding."""

    finding_id: str
    agent_index: int
    summary: str
    reason: str


class UnresolvedItem(TypedDict):
    """A topic that remains unresolved after debate."""

    topic: str
    positions: list


class ConsensusFinding(TypedDict):
    """A finding that achieved consensus among agents."""

    finding_id: str
    summary: str
    source_ids: list
    confidence: float
    supporting_agents: list
    level: str


class DebateTurn(TypedDict):
    """A single turn in the debate transcript."""

    round_index: int
    agent_index: int
    rebuttals: list
    supplements: list


class DebateResult(TypedDict):
    """Top-level container for a completed multi-agent debate."""

    run_id: str
    research_prompt: str
    paper_ids: list
    agent_analyses: list[AgentAnalysis]
    debate_turns: list[DebateTurn]
    consensus_findings: list[ConsensusFinding]
    minority_dissent: list[DissentItem]
    unresolved: list[UnresolvedItem]
    jaccard_matrix: list
    rounds: int
    duration_seconds: float
    status: str


# ── Utility functions ────────────────────────────────────────────────────────


def _compute_jaccard_similarity(set_a: set, set_b: set) -> float:
    """Compute the Jaccard similarity between two sets.

    Returns 0.0 when both sets are empty.
    """
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _extract_source_ids(findings: list) -> set:
    """Extract all unique source IDs from a list of findings."""
    source_ids: set = set()
    for finding in findings:
        for sid in finding.get("sourceIds", []):
            source_ids.add(sid)
    return source_ids


def _extract_keywords(finding: dict) -> set:
    """Extract keywords longer than 3 characters from a single finding.

    Strips common trailing punctuation from each keyword before filtering.
    """
    keywords = finding.get("keywords", []) or []
    return {k.strip(".,;:!?()[]{}") for k in keywords if len(k) > 3}


def _compute_finding_similarity(f1: dict, f2: dict) -> float:
    """Compute the average of sourceId Jaccard and keyword Jaccard.

    Returns a float in [0.0, 1.0] representing the similarity between
    two findings based on their shared source IDs and keywords.
    """
    source_a = set(f1.get("sourceIds", []))
    source_b = set(f2.get("sourceIds", []))
    kw_a = _extract_keywords(f1)
    kw_b = _extract_keywords(f2)

    source_jaccard = _compute_jaccard_similarity(source_a, source_b)
    keyword_jaccard = _compute_jaccard_similarity(kw_a, kw_b)

    return (source_jaccard + keyword_jaccard) / 2.0


def _cluster_findings(
    all_findings: list,
    source_threshold: float = 0.4,
    keyword_threshold: float = 0.3,
) -> list:
    """Greedy cluster findings by similarity.

    Each finding joins the first cluster whose representative (the first
    element of that cluster) satisfies the similarity threshold. If no
    existing cluster qualifies, a new cluster is created.

    The effective threshold is the average of *source_threshold* and
    *keyword_threshold*.

    Args:
        all_findings: List of finding dicts.
        source_threshold: Weight for source-ID Jaccard (used in threshold
            averaging).
        keyword_threshold: Weight for keyword Jaccard (used in threshold
            averaging).

    Returns:
        A list of lists, where each inner list is a cluster of findings.
    """
    effective_threshold = (source_threshold + keyword_threshold) / 2.0
    clusters: list[list] = []

    for finding in all_findings:
        added = False
        for cluster in clusters:
            representative = cluster[0]
            similarity = _compute_finding_similarity(finding, representative)
            if similarity >= effective_threshold:
                cluster.append(finding)
                added = True
                break
        if not added:
            clusters.append([finding])

    return clusters


class DebateOrchestrator:
    """Orchestrates multi-agent debate research."""

    DEFAULT_TEMPERATURES: ClassVar[list[float]] = [0.3, 0.7, 1.0]

    def __init__(self, research_prompt, paper_ids, constraints=None,
                 num_agents=3, max_debate_rounds=2):
        if num_agents < 1:
            raise ValueError("num_agents must be >= 1")
        if max_debate_rounds < 0:
            raise ValueError("max_debate_rounds must be >= 0")
        self.research_prompt = research_prompt
        self.paper_ids = paper_ids
        self.constraints = constraints or {}
        self.num_agents = min(num_agents, 5)
        self.max_debate_rounds = min(max_debate_rounds, 3)
        import hashlib
        import json
        import time
        self._run_id = hashlib.sha256(
            f"{research_prompt}{json.dumps(paper_ids, sort_keys=True)}{time.time()}".encode()
        ).hexdigest()[:16]

    def run_debate(self):
        import time
        started_at = time.time()
        analyses = self._run_independent_analyses()
        debate_turns = []
        if self.num_agents > 1 and analyses:
            debate_turns = self._run_debate_rounds(analyses)
        return self._build_debate_result(analyses, debate_turns, started_at)

    def _get_agent_configs(self):
        configs = []
        for i in range(self.num_agents):
            temperature = self.DEFAULT_TEMPERATURES[i % len(self.DEFAULT_TEMPERATURES)]
            agent_paper_ids = self.paper_ids
            if len(self.paper_ids) >= 2 and self.num_agents > 1:
                offset = i % len(self.paper_ids)
                agent_paper_ids = self.paper_ids[offset:] + self.paper_ids[:offset]
            configs.append({"agent_index": i, "temperature": temperature, "paper_ids": agent_paper_ids})
        return configs

    def _run_independent_analyses(self):
        configs = self._get_agent_configs()
        analyses = []
        for config in configs:
            try:
                state = run_agent_graph(
                    prompt=self.research_prompt, paper_ids=config["paper_ids"],
                    constraints=self.constraints, temperature=config["temperature"])
                analyses.append(self._extract_analysis_from_state(state, config))
            except Exception as e:
                logger.error("Agent %d failed: %s", config["agent_index"], str(e))
                analyses.append({
                    "agent_index": config["agent_index"], "temperature": config["temperature"],
                    "paper_ids": config["paper_ids"], "findings": [], "evidence_items": [],
                    "weighted_evidence": [], "cross_paper_insights": {}, "resolved_conflicts": [],
                    "draft_report": "", "credibility_mean": 0.0})
        return analyses

    def _extract_analysis_from_state(self, state, config):
        findings = state.get("findings") or []
        credibility_values = [float(f.get("credibility", 0)) for f in findings if isinstance(f.get("credibility", 0), (int, float))]
        credibility_mean = sum(credibility_values) / len(credibility_values) if credibility_values else 0.0
        return {
            "agent_index": config["agent_index"], "temperature": config["temperature"],
            "paper_ids": config["paper_ids"], "findings": findings,
            "evidence_items": state.get("evidence_items") or [],
            "weighted_evidence": state.get("weighted_evidence") or [],
            "cross_paper_insights": state.get("cross_paper_insights") or {},
            "resolved_conflicts": state.get("resolved_conflicts") or [],
            "draft_report": state.get("draft_report") or "",
            "credibility_mean": credibility_mean}

    def _run_debate_rounds(self, analyses):
        all_turns = []
        for round_idx in range(self.max_debate_rounds):
            round_turns = self._run_single_debate_round(round_idx, analyses)
            all_turns.extend(round_turns)
            if self._has_converged(analyses):
                break
        return all_turns

    def _run_single_debate_round(self, round_idx, analyses):
        turns = []
        for agent_a in analyses:
            if not agent_a.get("findings"):
                continue
            rebuttals, supplements = [], []

            # 24-1: Try LLM-driven review first, fall back to deterministic Jaccard.
            other_summaries: list[str] = []
            for agent_b in analyses:
                if agent_b["agent_index"] == agent_a["agent_index"] or not agent_b.get("findings"):
                    continue
                for f_b in agent_b["findings"][:5]:
                    other_summaries.append(
                        f'[Agent {agent_b["agent_index"]}] finding_id={f_b.get("finding_id", "")}: '
                        f'{(f_b.get("summary", "") or "")[:200]}'
                    )
            other_block = "\n".join(other_summaries)
            llm_results = _llm_debate_review(agent_a["findings"], other_block) if other_block else None

            if llm_results:
                for item in llm_results:
                    if item["type"] == "rebut":
                        rebuttals.append({
                            "from_agent": "llm", "finding_id": item["finding_id"],
                            "summary": "", "reason": item["reason"]})
                    elif item["type"] == "support":
                        supplements.append({
                            "from_agent": "llm", "finding_id": item["finding_id"],
                            "summary": "", "reason": item["reason"]})
            else:
                # Deterministic Jaccard fallback (original logic).
                for agent_b in analyses:
                    if agent_b["agent_index"] == agent_a["agent_index"] or not agent_b.get("findings"):
                        continue
                    for f_b in agent_b["findings"]:
                        for f_a in agent_a["findings"]:
                            sim = _compute_finding_similarity(f_a, f_b)
                            sources_a = set(f_a.get("sourceIds", []) or [])
                            sources_b = set(f_b.get("sourceIds", []) or [])
                            if sim >= 0.5 and sources_a != sources_b:
                                supplements.append({
                                    "from_agent": agent_b["agent_index"],
                                    "finding_id": f_b.get("finding_id", ""),
                                    "summary": (f_b.get("summary", "") or "")[:200],
                                    "reason": "Corroborating evidence from different sources"})
                            elif sim < 0.2 and sources_a & sources_b:
                                rebuttals.append({
                                    "from_agent": agent_b["agent_index"],
                                    "finding_id": f_b.get("finding_id", ""),
                                    "summary": (f_b.get("summary", "") or "")[:200],
                                    "reason": "Conflicting interpretation of shared sources"})

            turns.append({"round_index": round_idx, "agent_index": agent_a["agent_index"],
                          "rebuttals": rebuttals[:10], "supplements": supplements[:10]})
        return turns

    def _has_converged(self, analyses):
        if len(analyses) < 2:
            return True
        for i in range(len(analyses)):
            for j in range(i + 1, len(analyses)):
                sources_i = _extract_source_ids(analyses[i].get("findings", []))
                sources_j = _extract_source_ids(analyses[j].get("findings", []))
                if _compute_jaccard_similarity(sources_i, sources_j) < 0.7:
                    return False
        return True

    def _build_debate_result(self, analyses, debate_turns, started_at):
        import time
        n = len(analyses)
        jaccard_matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                si = _extract_source_ids(analyses[i].get("findings", []))
                sj = _extract_source_ids(analyses[j].get("findings", []))
                sim = _compute_jaccard_similarity(si, sj)
                jaccard_matrix[i][j] = sim
                jaccard_matrix[j][i] = sim
        consensus_result = synthesize_consensus(analyses)
        duration = time.time() - started_at
        return {
            "run_id": self._run_id, "research_prompt": self.research_prompt,
            "paper_ids": self.paper_ids, "agent_analyses": analyses,
            "debate_turns": debate_turns,
            "consensus_findings": consensus_result["consensus_findings"],
            "minority_dissent": consensus_result["minority_dissent"],
            "unresolved": consensus_result["unresolved"],
            "jaccard_matrix": jaccard_matrix,
            "rounds": max((t["round_index"] for t in debate_turns), default=-1) + 1 if debate_turns else 0,
            "duration_seconds": round(duration, 2),
            "status": "completed" if analyses else "failed"}


def synthesize_consensus(analyses):
    """Deterministic consensus synthesis from multiple agent analyses."""
    if not analyses:
        return {"consensus_findings": [], "minority_dissent": [], "unresolved": []}

    all_findings = []
    for analysis in analyses:
        for finding in analysis.get("findings", []):
            all_findings.append({**finding, "_agent_index": analysis["agent_index"],
                                 "_credibility": finding.get("credibility", 0.5)})

    if not all_findings:
        return {"consensus_findings": [], "minority_dissent": [], "unresolved": []}

    clusters = _cluster_findings(all_findings)

    consensus_findings, minority_dissent, unresolved = [], [], []
    num_agents = len(analyses)

    for cluster in clusters:
        agent_indices = set()
        credibilities = []
        source_ids = set()
        for f in cluster:
            agent_indices.add(f["_agent_index"])
            credibilities.append(float(f.get("_credibility", 0.5)))
            for sid in (f.get("sourceIds") or []):
                source_ids.add(sid)

        num_supporting = len(agent_indices)
        agent_ratio = num_supporting / max(num_agents, 1)
        avg_credibility = sum(credibilities) / len(credibilities)
        confidence = avg_credibility * agent_ratio
        summary = (cluster[0].get("summary", "") or "")[:200]

        if confidence >= 0.7 and num_supporting >= 2:
            consensus_findings.append({
                "finding_id": cluster[0].get("finding_id", ""),
                "summary": summary, "source_ids": sorted(source_ids),
                "confidence": round(confidence, 3),
                "supporting_agents": sorted(agent_indices),
                "level": "consensus"})
        elif confidence >= 0.4:
            if num_supporting == 1:
                agent_idx = next(iter(agent_indices))
                minority_dissent.append({
                    "finding_id": cluster[0].get("finding_id", ""),
                    "agent_index": agent_idx, "summary": summary,
                    "reason": f"Single agent finding (confidence={confidence:.2f}), not corroborated by other agents"})
            else:
                unresolved.append({
                    "topic": summary[:100],
                    "positions": [{"agent_index": f["_agent_index"],
                                   "summary": (f.get("summary", "") or "")[:150]} for f in cluster]})
        else:
            if num_supporting == 1:
                agent_idx = next(iter(agent_indices))
                minority_dissent.append({
                    "finding_id": cluster[0].get("finding_id", ""),
                    "agent_index": agent_idx, "summary": summary,
                    "reason": f"Low confidence single-source finding (confidence={confidence:.2f})"})

    return {"consensus_findings": consensus_findings, "minority_dissent": minority_dissent, "unresolved": unresolved}


# ── LLM-driven debate review (24-1) ─────────────────────────────────────────


def _llm_debate_review(
    agent_findings: list[dict],
    other_findings_summary: str,
    timeout_seconds: float = 10.0,
) -> list[dict] | None:
    """Use the flash LLM to classify each agent finding as rebut, support, or unrelated.

    Args:
        agent_findings: List of findings from the current agent.
        other_findings_summary: Concise summary of other agents' findings.
        timeout_seconds: Maximum seconds to wait for the LLM response.

    Returns:
        List of dicts with keys ``finding_id``, ``type`` (rebut/support/unrelated),
        and ``reason``, or ``None`` when the LLM is unavailable or times out.
    """
    if not agent_findings or not other_findings_summary.strip():
        return None

    findings_json_lines: list[str] = []
    for f in agent_findings[:8]:
        fid = f.get("finding_id", "")
        summary = (f.get("summary", "") or "")[:300]
        findings_json_lines.append(f'{{"finding_id": "{fid}", "summary": "{summary}"}}')
    findings_block = "[\n" + ",\n".join(findings_json_lines) + "\n]"

    prompt = f"""你是严谨的学术审稿人。阅读以下两个 Agent 的研究发现，对于 Agent A 的每条发现，判断 Agent B 的发现是反驳（rebut）、补充支撑（support）、还是无关（unrelated）。

Agent A 的发现：
{findings_block}

Agent B 的发现摘要：
{other_findings_summary}

仅返回 JSON 数组，每条格式为：
{{"finding_id": "...", "type": "rebut|support|unrelated", "reason": "简要中文理由"}}
"""

    try:
        import json as _json
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FutureTimeoutError

        from llm.client import get_translation_llm

        llm = get_translation_llm()

        def _call_llm():
            return llm._call(prompt)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_llm)
            try:
                raw = future.result(timeout=timeout_seconds)
            except FutureTimeoutError:
                logger.warning("LLM debate review timed out after %.1fs", timeout_seconds)
                return None

        raw = (raw or "").strip()
        if not raw:
            return None

        # Tolerate markdown code fences.
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.removesuffix("```")
        parsed = _json.loads(raw) if raw else []
        if not isinstance(parsed, list):
            return None

        results: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            t = str(item.get("type") or "").lower()
            if t not in {"rebut", "support", "unrelated"}:
                t = "unrelated"
            results.append({
                "finding_id": str(item.get("finding_id") or ""),
                "type": t,
                "reason": str(item.get("reason") or "")[:200],
            })
        return results if results else None
    except Exception:
        logger.warning("LLM debate review failed, falling back to deterministic logic", exc_info=True)
        return None


# ── Debate run API (moved from agent_project_service.py for 23-3) ──────────


def create_debate_run(
    project_id: str,
    research_prompt: str,
    paper_ids: list,
    constraints: dict | None = None,
    num_agents: int = 3,
):
    """Create and execute a multi-agent debate run.

    The result is persisted to SQLite so it survives process restarts (24-2).
    """
    from services.agent_project_service import get_agent_project, _get_agent_state_repository

    project = get_agent_project(project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")

    orchestrator = DebateOrchestrator(
        research_prompt=research_prompt,
        paper_ids=paper_ids,
        constraints=constraints,
        num_agents=num_agents,
        max_debate_rounds=2,
    )

    result = orchestrator.run_debate()

    # Persist to SQLite (24-2).
    try:
        repo = _get_agent_state_repository()
        repo.initialize()
        repo.save_debate_result(result["run_id"], project_id, result)
    except Exception:
        logger.warning("Failed to persist debate result, keeping in-memory only", exc_info=True)
        # Keep in-memory fallback for backward compatibility.
        _debate_results: dict = getattr(create_debate_run, "_results", {})
        _debate_results[result["run_id"]] = result
        create_debate_run._results = _debate_results

    return result


def get_debate_result(project_id: str, run_id: str):
    """Retrieve a stored debate result by run_id.

    Queries SQLite first; falls back to in-memory storage (24-2).
    """
    from services.agent_project_service import _get_agent_state_repository

    # Try SQLite first (24-2 persistence).
    try:
        repo = _get_agent_state_repository()
        repo.initialize()
        db_result = repo.get_debate_result(run_id)
        if db_result is not None:
            return db_result
    except Exception:
        pass

    # Fallback to in-memory for backward compatibility.
    _debate_results: dict = getattr(create_debate_run, "_results", {})
    return _debate_results.get(run_id)
