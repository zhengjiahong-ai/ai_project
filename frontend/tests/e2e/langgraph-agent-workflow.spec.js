import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

/**
 * LangGraph Agent Workflow E2E Tests (13-6).
 *
 * These tests verify the LangGraph agent-graph API integration:
 * 1. When the agent-graph endpoint is available, the frontend calls it first.
 * 2. When the agent-graph endpoint is unavailable (500), the frontend falls
 *    back to the legacy run/task path (covered by reader-agent-smoke.spec.js).
 */
const NOW = '2026-07-23T10:00:00.000Z';

const makeGraphState = (overrides = {}) => ({
  threadId: 'lg-thread-smoke-1',
  status: 'awaiting_plan_review',
  prompt: '比较论文的方法与证据',
  paper_ids: ['paper-smoke-1'],
  planItems: [
    { id: 'retrieve', label: '检索论文证据', detail: '读取方法与结论章节', status: 'pending' },
  ],
  plan_approved: false,
  final_approved: false,
  humanReview: { plan: { status: 'pending' }, final: { status: 'not_started' } },
  evidenceItems: [],
  findings: [],
  comparisonTable: {},
  conflicts: [],
  openQuestions: [],
  reviewRisks: [],
  draftReport: '',
  researchTimeline: [{ node: 'init', summary: 'Building research plan', timestamp: NOW }],
  error: '',
  ...overrides,
});

test('Agent run 优先调用 LangGraph agent-graph 端点', async ({ page }) => {
  const mockState = await installMockApi(page);

  let graphCalled = false;
  let graphPayload = null;

  // Intercept the agent-graph POST endpoint
  await page.route('**/api/agent-graph', async (route, request) => {
    const req = route.request();
    const url = new URL(req.url());
    if (req.method() === 'POST' && url.pathname === '/api/agent-graph') {
      graphCalled = true;
      graphPayload = req.postDataJSON() || {};
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          task: makeGraphState({ prompt: graphPayload.prompt || 'default' }),
        }),
      });
      return;
    }
    await route.fallback();
  });

  // Also intercept sub-paths (GET state, POST resume)
  await page.route('**/api/agent-graph/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.pathname.endsWith('/resume') || req.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          task: makeGraphState({
            status: 'awaiting_final_review',
            plan_approved: true,
            draftReport: '# LangGraph Report',
          }),
        }),
      });
      return;
    }
    await route.fallback();
  });

  await page.goto('/');
  await expect(page.getByText('Pixiu Academic Assistant')).toBeVisible();

  // Upload paper
  await page.locator('input[type="file"]').setInputFiles({
    name: 'lg-smoke.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
  await page.getByRole('button', { name: 'Agent 研究', exact: true }).click();
  await expect(page.getByText('Agent 学术研究工作台')).toBeVisible();

  // Create project
  await page.getByPlaceholder('项目标题').fill('LangGraph Smoke');
  await page.getByPlaceholder('项目目标').fill('Verify LangGraph integration');
  await page.getByTitle('创建项目').click();
  await expect(page.getByRole('heading', { name: 'LangGraph Smoke' })).toBeVisible();

  // Start a task
  await page.getByPlaceholder(/让 Agent 比较/).fill('LangGraph integration test');
  await page.getByTitle('启动 Agent 任务').click();

  // The frontend should have tried the LangGraph endpoint
  expect(graphCalled).toBe(true);
  expect(graphPayload).not.toBeNull();
  expect(graphPayload.prompt).toBe('LangGraph integration test');
});

test('LangGraph 不可用时 fallback 到旧 Agent run 路径', async ({ page }) => {
  const mockState = await installMockApi(page);

  // Make agent-graph endpoints return 500
  await page.route('**/api/agent-graph', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'error', message: 'LangGraph unavailable' }),
    });
  });
  await page.route('**/api/agent-graph/**', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'error', message: 'LangGraph unavailable' }),
    });
  });

  await page.goto('/');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'fallback-smoke.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
  await page.getByRole('button', { name: 'Agent 研究', exact: true }).click();

  await page.getByPlaceholder('项目标题').fill('Fallback 项目');
  await page.getByPlaceholder('项目目标').fill('验证 LangGraph 回退');
  await page.getByTitle('创建项目').click();
  await expect(page.getByRole('heading', { name: 'Fallback 项目' })).toBeVisible();

  await page.getByPlaceholder(/让 Agent 比较/).fill('回退路径测试');
  await page.getByTitle('启动 Agent 任务').click();

  // Should reach plan review via the legacy run/task path
  await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });

  // Complete through legacy path
  await page.getByRole('button', { name: '确认计划并执行' }).click();
  await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '确认终稿' }).click();
  await expect(page.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });

  // Verify the legacy path was used (task was created)
  expect(mockState.taskPayload).not.toBeNull();
});
