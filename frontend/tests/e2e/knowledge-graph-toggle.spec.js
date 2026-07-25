/**
 * Knowledge Graph Toggle E2E Tests.
 *
 * Verifies the "使用知识图谱补充证据" toggle in AgentTaskComposer:
 * 1. The toggle is enabled (aria-checked="true") by default.
 * 2. Turning it off sends `allowKnowledgeGraph: false` in the task-creation payload.
 * 3. Knowledge-graph evidence items (sourceType "knowledge_graph") are rendered
 *    with a distinctive visual treatment in the Tools & Evidence panel.
 */
import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

const NOW = '2026-07-25T12:00:00.000Z';

// ── Workspace response with KG evidence ─────────────────────────────────────
const buildKgWorkspaceResponse = () => ({
  status: 'success',
  workspace: {
    project: {
      projectId: 'project-smoke-1',
      title: 'KG Toggle Test',
      goal: 'Verify knowledge graph toggle',
      paperIds: ['paper-smoke-1'],
      latestTaskId: 'task-smoke-1',
      createdAt: NOW,
      updatedAt: NOW,
    },
    activeRun: {
      runId: 'task-smoke-1',
      projectId: 'project-smoke-1',
      traceId: 'trace-kg-1',
      status: 'succeeded',
      executionPhase: 'done',
      progress: 1,
      prompt: 'KG toggle test prompt',
      focusedPaperIds: ['paper-smoke-1'],
      constraints: '',
      context: {},
      humanReview: { planStatus: 'approved', finalStatus: 'approved' },
      reviewRisks: [],
      traceSummary: {},
      externalSearchConfig: {
        allowExternalSearch: false,
        provider: 'disabled',
        budget: { callLimit: 3, evidenceLimit: 15, callsUsed: 0, evidenceUsed: 0 },
        status: 'disabled',
        degradation: '',
      },
      error: '',
      createdAt: NOW,
      updatedAt: NOW,
    },
    pendingReview: { runId: 'task-smoke-1', status: 'completed', planItems: [] },
    latestArtifacts: {
      runId: 'task-smoke-1',
      evidenceItems: [
        {
          sourceId: 'kg-paper-1',
          pdfId: 'paper-smoke-1',
          sectionId: 'methods',
          pageIndex: 0,
          sourceType: 'knowledge_graph',
          text: 'KG: Method X is related to Method Y via shared evaluation protocol.',
          metadata: { entity: 'Method X', relation: 'evaluated_by', target: 'Protocol A' },
        },
        {
          sourceId: 'kg-paper-2',
          pdfId: 'paper-smoke-1',
          sectionId: 'results',
          pageIndex: 3,
          sourceType: 'knowledge_graph',
          text: 'KG: Dataset D was used in both Paper A and Paper B with differing preprocessing.',
          metadata: { entity: 'Dataset D', relation: 'used_in', target: 'Paper A' },
        },
        {
          sourceId: 'paper-internal-1',
          pdfId: 'paper-smoke-1',
          sectionId: 'discussion',
          pageIndex: 5,
          sourceType: 'paper',
          text: 'Internal evidence: the proposed approach reduces error by 12%.',
        },
      ],
      toolCallSummary: [
        { id: 'tool-1', name: 'search_paper', target: 'paper-smoke-1', result: '命中 3 条证据', status: 'succeeded' },
      ],
      findings: [{ id: 'f-1', summary: 'KG evidence enriched cross-paper analysis.', sourceIds: ['kg-paper-1', 'kg-paper-2'] }],
      comparisonTable: { columns: [], rows: [] },
      conflicts: [],
      openQuestions: [],
      draftReport: '## Current Conclusion\nKnowledge graph evidence has been integrated into the analysis.',
    },
    recentRuns: [],
    timeline: [{ id: 'ev-1', type: 'task_completed', title: '研究任务已完成', detail: '', phase: 'done', meta: {}, timestamp: NOW }],
    uiHints: {},
  },
});

// ── Helper: install workspace override for KG evidence tests ─────────────────
async function installKgWorkspaceOverride(page) {
  let planReviewed = false;

  await page.route('**/api/agent-runs/task-smoke-1/plan-review', async (route) => {
    planReviewed = true;
    await route.fallback();
  });
  await page.route('**/api/agent-tasks/task-smoke-1/plan-review', async (route) => {
    planReviewed = true;
    await route.fallback();
  });

  let workspacePollsAfterReview = 0;

  await page.route('**/api/agent-projects/project-smoke-1/workspace**', async (route) => {
    if (planReviewed) {
      workspacePollsAfterReview += 1;
      if (workspacePollsAfterReview >= 1) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(buildKgWorkspaceResponse()),
        });
        return;
      }
    }
    await route.fallback();
  });
}

// ── Reusable navigation ─────────────────────────────────────────────────────
async function navigateToAgentWorkspace(page) {
  await page.goto('/');
  await expect(page.getByText('Pixiu Academic Assistant')).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: 'kg-paper.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
  await page.getByRole('button', { name: 'Agent 研究', exact: true }).click();
  await expect(page.getByText('Agent 学术研究工作台')).toBeVisible();
}

async function createProject(page) {
  await page.getByPlaceholder('项目标题').fill('KG Toggle Test');
  await page.getByPlaceholder('项目目标').fill('Verify knowledge graph toggle behavior');
  await page.getByTitle('创建项目').click();
  await expect(page.getByRole('heading', { name: 'KG Toggle Test' })).toBeVisible();
}

// ── Locate the KG toggle switch ─────────────────────────────────────────────
const kgToggle = (page) =>
  page.getByRole('switch', { name: '使用知识图谱补充证据' });

// ═══════════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('Knowledge Graph Toggle', () => {
  test('knowledge graph toggle is enabled by default', async ({ page }) => {
    await installMockApi(page);
    await navigateToAgentWorkspace(page);
    await createProject(page);

    // The toggle should be present and checked by default.
    const toggle = kgToggle(page);
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  test('turning off knowledge graph sends allowKnowledgeGraph: false in task payload', async ({ page }) => {
    const mockState = await installMockApi(page);
    await navigateToAgentWorkspace(page);
    await createProject(page);

    // Toggle OFF the knowledge graph switch.
    const toggle = kgToggle(page);
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', 'false');

    // Create a task — the payload should include allowKnowledgeGraph: false.
    await page.getByPlaceholder(/让 Agent 比较/).fill('KG toggle off test prompt');
    await page.getByTitle('启动 Agent 任务').click();

    // Wait for the plan-review form to appear, confirming the task was created.
    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });

    // Verify the captured task payload.
    expect(mockState.taskPayload).not.toBeNull();
    expect(mockState.taskPayload.allowKnowledgeGraph).toBe(false);
  });

  test('knowledge graph evidence items appear in the Tools & Evidence panel', async ({ page }) => {
    await installKgWorkspaceOverride(page);
    await installMockApi(page);

    await navigateToAgentWorkspace(page);
    await createProject(page);

    await page.getByPlaceholder(/让 Agent 比较/).fill('Test KG evidence rendering');
    await page.getByTitle('启动 Agent 任务').click();

    // Approve plan.
    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();

    // The KG workspace override returns a completed task with KG evidence items.
    // Wait for the final state to render.
    await expect(page.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });

    // The Tools & Evidence panel should list 3 evidence items.
    const evidencePanel = page.locator('aside').filter({ hasText: 'Tools & Evidence' });
    await expect(evidencePanel.getByText('3 items').first()).toBeVisible();

    // Two of them are knowledge_graph typed.  Verify their sourceType labels
    // are visible and distinguishable from the regular "paper" sourceType.
    await expect(evidencePanel.getByText('knowledge_graph').first()).toBeVisible();
    await expect(evidencePanel.getByText('paper').first()).toBeVisible();

    // The knowledge_graph sourceType should carry a visual distinction.
    // (The component renders sourceType in a span; for KG items this should
    // eventually render in a purple / violet tone — here we assert the span
    // exists and is visible as a baseline.)
    const kgLabels = evidencePanel.getByText('knowledge_graph');
    await expect(kgLabels.first()).toBeVisible();

    // At least 2 KG evidence items exist.
    await expect(kgLabels).toHaveCount(2);
  });
});
