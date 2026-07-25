/**
 * Agent Report Confidence E2E Tests (17-1).
 *
 * Verifies that the AgentDraftReportSection renders:
 * 1. Confidence badges (high=green, medium=yellow, low=amber, insufficient=gray)
 *    when the draftReport contains `(avg credibility N.NN, level: **level**)` patterns.
 * 2. Consensus / Contested / Single-Source Findings sub-headings with
 *    distinct left-border colors.
 * 3. Old-style reports (no `### ... Findings` sub-headings) render without
 *    badges or errors.
 */
import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

const NOW = '2026-07-25T10:00:00.000Z';

// ── Structured report with all three confidence levels ──────────────────────
const STRUCTURED_REPORT = [
  '### Consensus Findings',
  'Method X consistently outperforms all baselines across every benchmark suite. (avg credibility 0.92, level: **high**)',
  '### Contested Findings',
  'The reported effect size varies substantially between Study A and Study B. (avg credibility 0.55, level: **medium**)',
  '### Single-Source Findings',
  'Only one preprint reports this outlier result without replication. (avg credibility 0.32, level: **low**)',
].join('\n');

// ── Old-style report (no structured sub-headings, no confidence pattern) ────
const OLD_REPORT = [
  '## Current Conclusion',
  'Smoke Agent 已完成证据检索并生成可追踪结论。整体方法论较为稳健，但存在若干未解决的开放问题。',
].join('\n');

// ── Helpers ─────────────────────────────────────────────────────────────────
const buildWorkspaceResponse = (draftReport, status = 'awaiting_final_review') => ({
  status: 'success',
  workspace: {
    project: {
      projectId: 'project-smoke-1',
      title: 'Confidence Test Project',
      goal: 'Verify report confidence rendering',
      paperIds: ['paper-smoke-1'],
      latestTaskId: 'task-smoke-1',
      createdAt: NOW,
      updatedAt: NOW,
    },
    activeRun: {
      runId: 'task-smoke-1',
      projectId: 'project-smoke-1',
      traceId: 'trace-confidence-1',
      status,
      executionPhase: status === 'awaiting_final_review' ? 'synthesizing' : 'done',
      progress: status === 'succeeded' ? 1 : 0.95,
      prompt: 'Verify confidence badge rendering',
      focusedPaperIds: ['paper-smoke-1'],
      constraints: '',
      context: {},
      humanReview: status === 'awaiting_final_review'
        ? { planStatus: 'approved', finalStatus: 'pending' }
        : { planStatus: 'approved', finalStatus: 'approved' },
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
    pendingReview: {
      runId: 'task-smoke-1',
      status: status === 'awaiting_final_review' ? 'final_pending' : 'completed',
      planItems: [{ id: 'retrieve', label: '检索证据', detail: '已完成', status: 'done' }],
    },
    latestArtifacts: {
      runId: 'task-smoke-1',
      evidenceItems: [],
      toolCallSummary: [],
      findings: [{ id: 'f-1', summary: 'Test finding for confidence report.', sourceIds: [] }],
      comparisonTable: { columns: [], rows: [] },
      conflicts: [],
      openQuestions: [],
      draftReport,
    },
    recentRuns: [],
    timeline: [{ id: 'ev-1', type: 'task_completed', title: '研究任务已完成', detail: '', phase: 'done', meta: {}, timestamp: NOW }],
    uiHints: {},
  },
});

/**
 * Install a workspace route override that returns a custom draftReport once
 * the task reaches the final stage.  Falls through to the normal mock for
 * earlier phases so the full workflow (create project → plan review → …)
 * still works.
 */
async function installConfidenceWorkspaceOverride(page, draftReport, { status = 'awaiting_final_review' } = {}) {
  let planReviewed = false;

  // Track plan-review so we know when to switch to the custom report.
  await page.route('**/api/agent-runs/task-smoke-1/plan-review', async (route) => {
    planReviewed = true;
    await route.fallback();
  });
  await page.route('**/api/agent-tasks/task-smoke-1/plan-review', async (route) => {
    planReviewed = true;
    await route.fallback();
  });

  // Also track the legacy run path
  await page.route('**/api/agent-projects/project-smoke-1/runs', async (route) => {
    planReviewed = false; // reset when a new run is created
    await route.fallback();
  });
  await page.route('**/api/agent-projects/project-smoke-1/tasks', async (route) => {
    planReviewed = false;
    await route.fallback();
  });

  let workspacePollAfterReview = 0;

  await page.route('**/api/agent-projects/project-smoke-1/workspace**', async (route) => {
    if (planReviewed) {
      workspacePollAfterReview += 1;
      // After plan review + 1 poll, deliver the custom report so the
      // AgentDraftReportSection appears with our structured content.
      if (workspacePollAfterReview >= 1) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(buildWorkspaceResponse(draftReport, status)),
        });
        return;
      }
    }
    await route.fallback();
  });
}

// ── Reusable navigation helper ──────────────────────────────────────────────
async function navigateToAgentWorkspace(page) {
  await page.goto('/');
  await expect(page.getByText('Pixiu Academic Assistant')).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: 'confidence-test.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
  await page.getByRole('button', { name: 'Agent 研究', exact: true }).click();
  await expect(page.getByText('Agent 学术研究工作台')).toBeVisible();
}

async function createProjectAndTask(page, prompt = 'Verify confidence badges') {
  await page.getByPlaceholder('项目标题').fill('Confidence Test Project');
  await page.getByPlaceholder('项目目标').fill('Verify report confidence rendering');
  await page.getByTitle('创建项目').click();
  await expect(page.getByRole('heading', { name: 'Confidence Test Project' })).toBeVisible();

  await page.getByPlaceholder(/让 Agent 比较/).fill(prompt);
  await page.getByTitle('启动 Agent 任务').click();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('Agent Report Confidence Badges', () => {
  test('structured report renders confidence badges with correct colors', async ({ page }) => {
    // Register workspace override FIRST so it takes priority over the broad mock.
    await installConfidenceWorkspaceOverride(page, STRUCTURED_REPORT, { status: 'awaiting_final_review' });
    await installMockApi(page);

    await navigateToAgentWorkspace(page);
    await createProjectAndTask(page);

    // Approve the plan (this triggers planReviewed=true in our override).
    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();

    // The workspace override now returns the structured report.
    await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });

    // Verify the "最终结果草稿" section is visible.
    await expect(page.getByText('最终结果草稿')).toBeVisible();

    // Confidence badges should appear for high / medium / low levels.
    // The badge labels are: 高置信度 (high), 中等置信度 (medium), 低置信度 (low).
    await expect(page.getByText('高置信度')).toBeVisible();
    await expect(page.getByText('中等置信度')).toBeVisible();
    await expect(page.getByText('低置信度')).toBeVisible();

    // Verify the Consensus / Contested / Single-Source section headings.
    await expect(page.getByText('Consensus Findings')).toBeVisible();
    await expect(page.getByText('Contested Findings')).toBeVisible();
    await expect(page.getByText('Single-Source Findings')).toBeVisible();

    // The high-confidence badge should use green color (the dot + background).
    // The COMPONENT applies inline styles using var(--success, #16a34a).
    const highBadge = page.getByText('高置信度');
    const highColor = await highBadge.evaluate((el) => getComputedStyle(el).color);
    // rgb(22, 163, 74) ≈ #16a34a (green / success).
    expect(highColor).toMatch(/rgb\(22,\s*163,\s*74\)/);

    // Medium-confidence → yellow / warning tone.
    const mediumBadge = page.getByText('中等置信度');
    const mediumColor = await mediumBadge.evaluate((el) => getComputedStyle(el).color);
    expect(mediumColor).toMatch(/rgb\(202,\s*138,\s*4\)/);

    // Low-confidence → amber / caution tone.
    const lowBadge = page.getByText('低置信度');
    const lowColor = await lowBadge.evaluate((el) => getComputedStyle(el).color);
    expect(lowColor).toMatch(/rgb\(217,\s*119,\s*6\)/);
  });

  test('Consensus/Contested/Single-Source sections have distinct left border colors', async ({ page }) => {
    await installConfidenceWorkspaceOverride(page, STRUCTURED_REPORT, { status: 'awaiting_final_review' });
    await installMockApi(page);

    await navigateToAgentWorkspace(page);
    await createProjectAndTask(page);

    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();
    await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });

    // Each section heading paragraph should have a distinct left border colour.
    // The component applies borderLeft inline style:
    //   Consensus  → var(--success, #16a34a)  → green
    //   Contested   → var(--caution, #d97706) → amber
    //   Single-Source → var(--text-muted, #6b7280) → gray

    // Find the paragraph lines that serve as section headers (font-semibold).
    const sectionLines = page.locator('.agent-card.font-semibold');

    // We expect exactly 3 section header lines.
    await expect(sectionLines).toHaveCount(3);

    const borderColors = await sectionLines.evaluateAll((els) =>
      els.map((el) => getComputedStyle(el).borderLeftColor),
    );

    // Consensus → green (#16a34a)
    expect(borderColors[0]).toMatch(/rgb\(22,\s*163,\s*74\)/);
    // Contested → amber (#d97706)
    expect(borderColors[1]).toMatch(/rgb\(217,\s*119,\s*6\)/);
    // Single-Source → gray (#6b7280)
    expect(borderColors[2]).toMatch(/rgb\(107,\s*114,\s*128\)/);
  });

  test('old report without structured sections renders no confidence badges', async ({ page }) => {
    // Use a plain draftReport (no ### ... Findings headings, no credibility pattern).
    await installConfidenceWorkspaceOverride(page, OLD_REPORT, { status: 'awaiting_final_review' });
    await installMockApi(page);

    await navigateToAgentWorkspace(page);
    await createProjectAndTask(page);

    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();
    await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });

    // The draft report section should be visible.
    await expect(page.getByText('最终结果草稿')).toBeVisible();

    // The report content should be rendered.
    await expect(page.getByText(/Smoke Agent 已完成证据检索/)).toBeVisible();

    // No confidence badges should appear.
    await expect(page.getByText('高置信度')).not.toBeVisible();
    await expect(page.getByText('中等置信度')).not.toBeVisible();
    await expect(page.getByText('低置信度')).not.toBeVisible();
    await expect(page.getByText('证据不足')).not.toBeVisible();

    // No structured section headings should appear.
    await expect(page.getByText('Consensus Findings')).not.toBeVisible();
    await expect(page.getByText('Contested Findings')).not.toBeVisible();
    await expect(page.getByText('Single-Source Findings')).not.toBeVisible();
  });
});
