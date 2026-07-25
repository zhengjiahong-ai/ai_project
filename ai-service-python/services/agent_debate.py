"""Agent debate orchestrator — Jaccard similarity, finding clustering, and TypedDict definitions.

This module provides the foundational building blocks for multi-agent debate:
- TypedDict type definitions for debate data structures
- Jaccard similarity computation between sets
- Finding similarity and greedy clustering utilities
"""

from __future__ import annotations

from typing import TypedDict


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


def _extract_keywords(findings: list) -> set:
    """Extract keywords longer than 3 characters from a list of findings."""
    keywords: set = set()
    for finding in findings:
        for kw in finding.get("keywords", []):
            if len(kw) > 3:
                keywords.add(kw)
    return keywords


def _compute_finding_similarity(f1: dict, f2: dict) -> float:
    """Compute the average of sourceId Jaccard and keyword Jaccard.

    Returns a float in [0.0, 1.0] representing the similarity between
    two findings based on their shared source IDs and keywords.
    """
    source_a = set(f1.get("sourceIds", []))
    source_b = set(f2.get("sourceIds", []))
    kw_a = set(f1.get("keywords", []))
    kw_b = set(f2.get("keywords", []))

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
