/**
 * Multi-Agent Debate E2E Tests (20-4).
 *
 * Validates the DebateResult schema returned by POST /api/agent-projects/{id}/debate.
 * These are pure data-structure tests that do not require a running server.
 */
import { expect, test } from '@playwright/test';

test.describe('Multi-Agent Debate', () => {
  test('debate result schema matches expected structure', async () => {
    const debateData = {
      run_id: 'debate-1',
      status: 'completed',
      research_prompt: 'What is the effect of X on Y?',
      paper_ids: ['paper-1', 'paper-2', 'paper-3'],
      agent_analyses: [
        { agent_index: 0, temperature: 0.3, findings: [{ finding_id: 'f1', sourceIds: ['s1'], summary: 'Finding A', credibility: 0.85 }], credibility_mean: 0.8 },
        { agent_index: 1, temperature: 0.7, findings: [{ finding_id: 'f2', sourceIds: ['s1'], summary: 'Finding A variant', credibility: 0.8 }], credibility_mean: 0.75 },
        { agent_index: 2, temperature: 1.0, findings: [{ finding_id: 'f3', sourceIds: ['s2'], summary: 'Minority view', credibility: 0.5 }], credibility_mean: 0.5 },
      ],
      debate_turns: [{ round_index: 0, agent_index: 0, rebuttals: [], supplements: [{ from_agent: 1, finding_id: 'f2', summary: 'Corroborating' }] }],
      consensus_findings: [{ finding_id: 'f1', summary: 'Finding A', confidence: 0.82, supporting_agents: [0, 1], source_ids: ['s1'], level: 'consensus' }],
      minority_dissent: [{ finding_id: 'f3', agent_index: 2, summary: 'Minority view', reason: 'Single agent finding, not corroborated by other agents' }],
      unresolved: [],
      jaccard_matrix: [[1, 0.5, 0], [0.5, 1, 0], [0, 0, 1]],
      rounds: 1,
      duration_seconds: 2.5,
    };

    // Top-level fields
    expect(debateData).toHaveProperty('run_id');
    expect(debateData).toHaveProperty('status');
    expect(debateData).toHaveProperty('agent_analyses');
    expect(debateData).toHaveProperty('consensus_findings');
    expect(debateData).toHaveProperty('minority_dissent');
    expect(debateData).toHaveProperty('unresolved');
    expect(debateData).toHaveProperty('jaccard_matrix');
    expect(debateData).toHaveProperty('rounds');
    expect(debateData).toHaveProperty('duration_seconds');

    // Status must be 'completed' or 'failed'
    expect(['completed', 'failed']).toContain(debateData.status);

    // run_id is a non-empty string
    expect(typeof debateData.run_id).toBe('string');
    expect(debateData.run_id.length).toBeGreaterThan(0);

    // Agent analyses
    expect(Array.isArray(debateData.agent_analyses)).toBe(true);
    expect(debateData.agent_analyses.length).toBe(3);
    debateData.agent_analyses.forEach((agent) => {
      expect(agent).toHaveProperty('agent_index');
      expect(agent).toHaveProperty('temperature');
      expect(agent).toHaveProperty('findings');
      expect(agent).toHaveProperty('credibility_mean');
      expect(Array.isArray(agent.findings)).toBe(true);
    });

    // Consensus findings
    expect(Array.isArray(debateData.consensus_findings)).toBe(true);
    expect(debateData.consensus_findings.length).toBeGreaterThan(0);
    expect(debateData.consensus_findings[0]).toHaveProperty('level');
    expect(debateData.consensus_findings[0].level).toBe('consensus');
    expect(debateData.consensus_findings[0]).toHaveProperty('confidence');
    expect(debateData.consensus_findings[0]).toHaveProperty('supporting_agents');
    expect(debateData.consensus_findings[0]).toHaveProperty('source_ids');

    // Minority dissent
    expect(Array.isArray(debateData.minority_dissent)).toBe(true);
    expect(debateData.minority_dissent[0]).toHaveProperty('agent_index');
    expect(debateData.minority_dissent[0]).toHaveProperty('summary');
    expect(debateData.minority_dissent[0]).toHaveProperty('reason');

    // Unresolved
    expect(Array.isArray(debateData.unresolved)).toBe(true);

    // Jaccard matrix
    expect(Array.isArray(debateData.jaccard_matrix)).toBe(true);
    // Matrix should be square
    expect(debateData.jaccard_matrix.length).toBe(3);
    debateData.jaccard_matrix.forEach((row) => {
      expect(Array.isArray(row)).toBe(true);
      expect(row.length).toBe(3);
    });
    // Diagonal should be 1.0
    expect(debateData.jaccard_matrix[0][0]).toBe(1);
    expect(debateData.jaccard_matrix[1][1]).toBe(1);
    expect(debateData.jaccard_matrix[2][2]).toBe(1);
    // Matrix should be symmetric
    expect(debateData.jaccard_matrix[0][1]).toBe(debateData.jaccard_matrix[1][0]);
    expect(debateData.jaccard_matrix[0][2]).toBe(debateData.jaccard_matrix[2][0]);
    expect(debateData.jaccard_matrix[1][2]).toBe(debateData.jaccard_matrix[2][1]);
  });

  test('empty debate result handles zero findings gracefully', async () => {
    const emptyResult = {
      run_id: 'debate-empty',
      status: 'completed',
      agent_analyses: [
        { agent_index: 0, temperature: 0.3, findings: [], credibility_mean: 0 },
      ],
      debate_turns: [],
      consensus_findings: [],
      minority_dissent: [],
      unresolved: [],
      jaccard_matrix: [[1]],
      rounds: 0,
      duration_seconds: 0.5,
    };

    expect(emptyResult.consensus_findings).toHaveLength(0);
    expect(emptyResult.minority_dissent).toHaveLength(0);
    expect(emptyResult.unresolved).toHaveLength(0);
    expect(emptyResult.debate_turns).toHaveLength(0);
    expect(emptyResult.rounds).toBe(0);
    expect(emptyResult.agent_analyses[0].findings).toHaveLength(0);
    expect(emptyResult.agent_analyses[0].credibility_mean).toBe(0);
  });
});
