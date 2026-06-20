import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

test('阅读 IDE 与 Agent 研究完成同一浏览器 smoke 主流程', async ({ page }) => {
  const mockState = await installMockApi(page);

  await page.goto('/');
  await expect(page.getByText('Pixiu Academic Assistant')).toBeVisible();
  await expect(page.getByRole('button', { name: '阅读 IDE' })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: 'smoke-paper.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
  const navbar = page.getByRole('banner');
  await expect(navbar.getByText('当前论文')).toBeVisible();
  await expect(navbar.getByText('smoke-paper.pdf')).toBeVisible();

  await page.getByRole('button', { name: '论文库' }).click();
  const library = page.locator('section').filter({ has: page.getByRole('heading', { name: '论文库' }) });
  await expect(library.getByText('Smoke 测试论文')).toBeVisible();
  await library.getByRole('button', { name: '打开' }).click();
  await expect(navbar.getByText('smoke-paper.pdf')).toBeVisible();

  const workspaceNavigation = page.locator('.workspace-top-panels');
  await workspaceNavigation.hover();
  await page.getByRole('button', { name: '深度探究' }).click();
  await workspaceNavigation.hover();
  await page.getByRole('button', { name: '功能导航' }).click();
  await page.getByRole('button', { name: '批判阅读', exact: true }).click();
  await expect(page.getByRole('heading', { name: '开启批判性阅读' })).toBeVisible();
  await expect(page.getByText('研读工作台')).toBeVisible();

  await page.getByRole('button', { name: 'Agent 研究' }).click();
  await expect(page.getByText('Agent 学术研究工作台')).toBeVisible();
  await page.getByPlaceholder('项目标题').fill('Smoke Agent 项目');
  await page.getByPlaceholder('项目目标').fill('验证任务历史和证据展示');
  await expect(page.getByText('1 篇已选')).toBeVisible();
  await page.getByTitle('创建项目').click();
  await expect(page.getByRole('heading', { name: 'Smoke Agent 项目' })).toBeVisible();

  const prompt = '比较论文的方法、证据与局限性';
  await page.getByPlaceholder(/让 Agent 比较/).fill(prompt);
  await page.getByTitle('启动 Agent 任务').click();

  await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '确认计划并执行' }).click();

  await expect(page.getByText('项目对话记录')).toBeVisible();
  await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '确认终稿' }).click();
  await expect(page.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });
  const evidencePanel = page.locator('aside').filter({ hasText: 'Tools & Evidence' });
  await expect(evidencePanel.getByText('1 items')).toBeVisible();
  await expect(evidencePanel.getByText('paper-smoke-1', { exact: true }).first()).toBeVisible();
  await evidencePanel.getByRole('button', { name: '查看片段' }).click();
  await expect(evidencePanel.getByText('Smoke 论文采用可追踪检索流程验证方法设计。')).toBeVisible();
  await expect(page.getByText('Smoke Agent 已完成证据检索并生成可追踪结论。')).toBeVisible();
  await expect(evidencePanel.getByText('search_paper')).toBeVisible();

  expect(mockState.projectPayload).toEqual({
    title: 'Smoke Agent 项目',
    goal: '验证任务历史和证据展示',
    paperIds: ['paper-smoke-1'],
  });
  expect(mockState.taskPayload.prompt).toBe(prompt);
  expect(mockState.taskPollCount).toBeGreaterThanOrEqual(2);
  expect(mockState.planReviewPayload.focusedPaperIds).toEqual(['paper-smoke-1']);
  expect(mockState.finalReviewPayload.riskReviews).toEqual([{ riskId: 'open:1', reviewStatus: 'reviewed' }]);
});
