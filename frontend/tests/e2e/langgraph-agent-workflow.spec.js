import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

/**
 * Agent Workflow E2E Tests (13-6).
 *
 * 当前架构：Agent 任务统一经「持久化 run 接口」（POST /api/agent-projects/:id/runs）
 * 创建，并通过 workspace 轮询推进；前端不再优先调用 LangGraph `/api/agent-graph`
 * 端点（见 AgentWorkspace.test.tsx 中 "does NOT call runAgentGraph" 等用例）。
 * 因此本 spec 验证：
 * 1. 任务经 run 接口创建，agent-graph 端点不被调用。
 * 2. 即使 agent-graph 端点不可用（500），研究流程仍能完成计划/终稿人工审查。
 */

async function enterAgentWorkspace(page) {
  await page.goto('/');
  await expect(page.getByText('Pixiu Academic Assistant')).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: 'lg-smoke.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
  await page.getByRole('button', { name: '研究 Agent' }).click();
  await expect(page.getByRole('button', { name: '新建项目' })).toBeVisible();
}

async function createProject(page, title, goal) {
  await page.getByRole('button', { name: '新建项目' }).click();
  await page.getByPlaceholder('项目标题').fill(title);
  await page.getByPlaceholder('项目目标').fill(goal);
  await page.getByRole('button', { name: '创建项目' }).click();
  await expect(page.getByRole('button', { name: title, exact: true })).toBeVisible();
}

// 计划审查表单位于默认折叠的「研究链」内，交互前需先展开。
async function expandResearchChain(page) {
  const chain = page.locator('details.agent-research-chain');
  await expect(page.getByText('研究链 · 点击展开完整过程')).toBeVisible({ timeout: 10_000 });
  if (!(await chain.evaluate((el) => el.open))) {
    await page.getByText('研究链 · 点击展开完整过程').click();
  }
  return chain;
}

test('Agent run 通过持久化 run 接口创建任务，不调用 agent-graph 端点', async ({ page }) => {
  const mockState = await installMockApi(page);

  let graphCalled = false;
  await page.route('**/api/agent-graph', async (route) => {
    graphCalled = true;
    await route.fallback();
  });
  await page.route('**/api/agent-graph/**', async (route) => {
    graphCalled = true;
    await route.fallback();
  });

  await enterAgentWorkspace(page);
  await createProject(page, 'LangGraph Smoke', 'Verify run/task integration');

  await page.getByLabel('创建研究任务').fill('LangGraph integration test');
  await page.getByTitle('启动 Agent 任务').click();

  await expandResearchChain(page);
  await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });

  // 当前架构下任务经 run 接口创建，agent-graph 端点不应被调用。
  expect(graphCalled).toBe(false);
  expect(mockState.taskPayload).not.toBeNull();
  expect(mockState.taskPayload.prompt).toBe('LangGraph integration test');
});

test('agent-graph 端点不可用（500）时研究流程仍能完成人工审查', async ({ page }) => {
  const mockState = await installMockApi(page);

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

  await enterAgentWorkspace(page);
  await createProject(page, 'Fallback 项目', '验证 run/task 路径');

  await page.getByLabel('创建研究任务').fill('回退路径测试');
  await page.getByTitle('启动 Agent 任务').click();

  const chain = await expandResearchChain(page);
  await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });

  await page.getByRole('button', { name: '确认计划并执行' }).click();
  await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '确认终稿' }).click();
  await expect(chain.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });

  expect(mockState.taskPayload).not.toBeNull();
});
