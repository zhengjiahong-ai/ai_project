import { describe, expect, it } from 'vitest';
import { buildTaskFromRunWorkspace, mergeAgentRunFallback } from './agentWorkspaceModel';

const run = { runId: 'run-1', projectId: 'project-1', status: 'running' };
const previousTask = buildTaskFromRunWorkspace({
  run: { ...run, researchTimeline: [{ node: 'retrieve', summary: 'Read papers' }] },
  latestArtifacts: {
    evidenceItems: [{ sourceId: 'e1', text: 'Evidence text', pageIndex: 0 }],
    findings: [{ summary: 'Finding', sourceIds: ['e1'] }],
    comparisonTable: { columns: ['Method'], rows: [['CoT']] },
    conflicts: [{ summary: 'Conflict', sourceIds: ['e1'] }],
    openQuestions: ['Unresolved question'],
    draftReport: 'Report', toolCallSummary: [{ tool: 'retrieve' }],
    llmSynthesis: 'Synthesis', advancedAnalysis: { limitations: ['Small sample'] },
  },
  timeline: [{ id: 'event-1', phase: 'researching', detail: 'Read evidence', type: 'progress' }],
})!;

describe('run polling fallback', () => {
  it('preserves all existing artifacts and event fields when supplemental requests fail', () => {
    const task = mergeAgentRunFallback({ previousTask, run: { ...run, status: 'failed', error: 'Timeout', progress: 0.8 } })!;
    for (const key of ['evidenceItems', 'findings', 'comparisonTable', 'conflicts', 'openQuestions',
      'draftReport', 'events', 'toolCalls', 'researchTimeline', 'llmSynthesis', 'advancedAnalysis', 'reportSources'] as const) {
      expect(task[key], key).toEqual(previousTask[key]);
    }
    expect(task).toMatchObject({ status: 'failed', error: 'Timeout', progress: 0.8 });
  });

  it('updates supplied fields and retains fields omitted from partial artifacts', () => {
    const task = mergeAgentRunFallback({ previousTask, run, artifacts: { draftReport: 'New report' } })!;
    expect(task.draftReport).toBe('New report');
    expect(task.evidenceItems).toEqual(previousTask.evidenceItems);
    expect(task.llmSynthesis).toBe('Synthesis');
    expect(task.events).toEqual(previousTask.events);
  });

  it('honors explicitly empty artifacts, timeline and research timeline', () => {
    const task = mergeAgentRunFallback({ previousTask, run: { ...run, researchTimeline: [] },
      artifacts: { evidenceItems: [], findings: [], draftReport: '', advancedAnalysis: null }, timeline: [] })!;
    expect(task).toMatchObject({ evidenceItems: [], findings: [], draftReport: '', advancedAnalysis: null, events: [], researchTimeline: [] });
  });

  it('normalizes fresh timeline entries and does not borrow artifacts from another run', () => {
    const task = mergeAgentRunFallback({ previousTask, run: { ...run, runId: 'run-2' },
      timeline: [{ id: 'new-event', phase: 'writing', title: 'Write report' }] })!;
    expect(task.events[0]).toMatchObject({ eventId: 'new-event', stage: 'writing', summary: 'Write report' });
    expect(task.evidenceItems).toEqual([]);
    expect(task.draftReport).toBe('');
  });
});
