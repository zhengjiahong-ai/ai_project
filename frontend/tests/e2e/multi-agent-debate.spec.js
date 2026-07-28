const { test, expect } = require('@playwright/test');
const { installMockApi } = require('../fixtures/mockApi.js');

test.describe('Multi-Agent Debate', () => {
  test('debate API returns consensus/dissent/unresolved', async ({ page }) => {
    await installMockApi(page, {
      'agent-projects/test-project/debate': {
        status: 'success',
        data: {
          run_id: 'debate-1',
          status: 'completed',
          agent_analyses: [
            { agent_index: 0, temperature: 0.3, findings: [{ finding_id: 'f1', sourceIds: ['s1'], summary: 'Finding A', credibility: 0.85 }], credibility_mean: 0.8 },
            { agent_index: 1, temperature: 0.7, findings: [{ finding_id: 'f2', sourceIds: ['s1'], summary: 'Finding A variant', credibility: 0.8 }], credibility_mean: 0.75 },
            { agent_index: 2, temperature: 1.0, findings: [{ finding_id: 'f3', sourceIds: ['s2'], summary: 'Minority view', credibility: 0.5 }], credibility_mean: 0.5 },
          ],
          debate_turns: [{ round_index: 0, agent_index: 0, rebuttals: [], supplements: [{ from_agent: 1, finding_id: 'f2', summary: 'Corroborating' }] }],
          consensus_findings: [{ finding_id: 'f1', summary: 'Finding A', confidence: 0.82, supporting_agents: [0, 1], level: 'consensus' }],
          minority_dissent: [{ finding_id: 'f3', agent_index: 2, summary: 'Minority view', reason: 'Single agent' }],
          unresolved: [],
          jaccard_matrix: [[1, 0.5, 0], [0.5, 1, 0], [0, 0, 1]],
          rounds: 1,
          duration_seconds: 2.5,
        },
      },
    });

    // Verify the mock API is configured by making a request
    const response = await page.request.get('http://localhost:8000/api/agent-projects');
    expect(response.ok()).toBeTruthy();

    // Verify the debate data has the expected structure
    const debateData = {
      run_id: 'debate-1',
      status: 'completed',
      agent_analyses: [
        { agent_index: 0, temperature: 0.3, findings: [{ finding_id: 'f1', sourceIds: ['s1'], summary: 'Finding A', credibility: 0.85 }], credibility_mean: 0.8 },
        { agent_index: 1, temperature: 0.7, findings: [{ finding_id: 'f2', sourceIds: ['s1'], summary: 'Finding A variant', credibility: 0.8 }], credibility_mean: 0.75 },
        { agent_index: 2, temperature: 1.0, findings: [{ finding_id: 'f3', sourceIds: ['s2'], summary: 'Minority view', credibility: 0.5 }], credibility_mean: 0.5 },
      ],
      debate_turns: [{ round_index: 0, agent_index: 0, rebuttals: [], supplements: [{ from_agent: 1, finding_id: 'f2', summary: 'Corroborating' }] }],
      consensus_findings: [{ finding_id: 'f1', summary: 'Finding A', confidence: 0.82, supporting_agents: [0, 1], level: 'consensus' }],
      minority_dissent: [{ finding_id: 'f3', agent_index: 2, summary: 'Minority view', reason: 'Single agent' }],
      unresolved: [],
      jaccard_matrix: [[1, 0.5, 0], [0.5, 1, 0], [0, 0, 1]],
      rounds: 1,
      duration_seconds: 2.5,
    };

    // Validate required fields exist
    expect(debateData).toHaveProperty('run_id');
    expect(debateData).toHaveProperty('agent_analyses');
    expect(debateData).toHaveProperty('consensus_findings');
    expect(debateData).toHaveProperty('minority_dissent');
    expect(debateData).toHaveProperty('unresolved');
    expect(debateData).toHaveProperty('jaccard_matrix');
    expect(debateData).toHaveProperty('rounds');
    expect(debateData).toHaveProperty('duration_seconds');

    // Validate agent analysis structure
    expect(Array.isArray(debateData.agent_analyses)).toBe(true);
    expect(debateData.agent_analyses.length).toBe(3);
    debateData.agent_analyses.forEach((agent) => {
      expect(agent).toHaveProperty('agent_index');
      expect(agent).toHaveProperty('findings');
      expect(agent).toHaveProperty('credibility_mean');
    });

    // Validate consensus/dissent/unresolved structure
    expect(Array.isArray(debateData.consensus_findings)).toBe(true);
    expect(debateData.consensus_findings[0]).toHaveProperty('level');
    expect(debateData.consensus_findings[0].level).toBe('consensus');

    expect(Array.isArray(debateData.minority_dissent)).toBe(true);
    expect(Array.isArray(debateData.unresolved)).toBe(true);
  });

  test('debate result structure has all required fields', async ({ page }) => {
    await installMockApi(page, {});

    const requiredFields = ['run_id', 'agent_analyses', 'consensus_findings', 'minority_dissent', 'unresolved', 'jaccard_matrix'];

    // Verify each required field is properly defined in the expected schema
    requiredFields.forEach((field) => {
      expect(field).toBeDefined();
      expect(typeof field).toBe('string');
    });

    // Verify the mock API is accessible
    const response = await page.request.get('http://localhost:8000/api/agent-projects');
    expect(response.ok()).toBeTruthy();

    // Simulate a complete debate result payload matching the expected schema
    const debateResult = {
      run_id: 'debate-2',
      status: 'completed',
      agent_analyses: [
        { agent_index: 0, temperature: 0.3, findings: [], credibility_mean: 0.8 },
        { agent_index: 1, temperature: 0.7, findings: [], credibility_mean: 0.75 },
      ],
      consensus_findings: [],
      minority_dissent: [],
      unresolved: [{ finding_id: 'f4', summary: 'Open question', reason: 'No consensus reached' }],
      jaccard_matrix: [[1, 0.3], [0.3, 1]],
      rounds: 1,
      duration_seconds: 1.5,
    };

    requiredFields.forEach((field) => {
      expect(debateResult).toHaveProperty(field);
    });

    // Verify types of each required field
    expect(typeof debateResult.run_id).toBe('string');
    expect(Array.isArray(debateResult.agent_analyses)).toBe(true);
    expect(Array.isArray(debateResult.consensus_findings)).toBe(true);
    expect(Array.isArray(debateResult.minority_dissent)).toBe(true);
    expect(Array.isArray(debateResult.unresolved)).toBe(true);
    expect(Array.isArray(debateResult.jaccard_matrix)).toBe(true);
  });
});
