import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { installExternalProviderRoute } from '../fixtures/externalProviderRoute.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

/**
 * Reader IDE + Agent 研究 smoke 主流程。
 *
 * 当前 UI 约定（探针 + 源码核实）：
 * - 顶栏「工作区切换」用「阅读 IDE」/「研究 Agent」切换模式；banner 不再显示当前论文名。
 * - 阅读 IDE 左侧栏（complementary）显示「当前论文」与文件名；论文库为弹层（heading「论文库」+ 表格「打开」）。
 * - 批判阅读入口改为「阅读助手 → 更多工具 → 批判分析」，面板 heading 为「开启批判性阅读」；
 *   旧的 .workspace-top-panels「深度探究/功能导航」工作流条已隐藏（visible=false）。
 * - Agent 项目在侧栏「新建项目」弹层创建；任务经 composer「创建研究任务」+「启动 Agent 任务」发起。
 * - 计划审查表单位于默认折叠的「研究链」内；证据、时间线、工具调用也在研究链内。
 * - 最终结果草稿、终稿人工审查在研究链之外，默认可见；报告正文按行渲染在草稿区。
 */

// 上传论文并停留在阅读 IDE。
async function uploadPaper(page, fileName) {
  await page.goto('/');
  await expect(page.getByText('Pixiu Academic Assistant')).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
}

// 顶栏切换到「研究 Agent」，侧栏出现「新建项目」即表示工作台就绪。
async function enterAgentWorkspace(page) {
  await page.getByRole('button', { name: '研究 Agent' }).click();
  await expect(page.getByRole('button', { name: '新建项目' })).toBeVisible();
}

// 侧栏「新建项目」弹层创建项目（上传论文默认自动选中）。
async function createProject(page, title, goal) {
  await page.getByRole('button', { name: '新建项目' }).click();
  await page.getByPlaceholder('项目标题').fill(title);
  await page.getByPlaceholder('项目目标').fill(goal);
  await page.getByRole('button', { name: '创建项目' }).click();
  await expect(page.getByRole('button', { name: title, exact: true })).toBeVisible();
}

// 研究链默认折叠，交互前需展开。
async function expandResearchChain(page) {
  const chain = page.locator('details.agent-research-chain');
  await expect(page.getByText('研究链 · 点击展开完整过程')).toBeVisible({ timeout: 10_000 });
  if (!(await chain.evaluate((el) => el.open))) {
    await page.getByText('研究链 · 点击展开完整过程').click();
  }
  return chain;
}

// 最终结果草稿区（报告正文在此按行渲染，避免与响应卡片摘要产生严格模式冲突）。
const draftReportSection = (page) => page.locator('details').filter({ hasText: '最终结果草稿' });

// composer「研究设置」弹层里的「外部检索」为原生 checkbox。
async function enableComposerExternalSearch(page) {
  await page.getByTitle('研究设置').click();
  const toggle = page.getByRole('checkbox', { name: '外部检索' });
  await expect(toggle).toBeVisible({ timeout: 5_000 });
  if (!(await toggle.isChecked())) {
    await toggle.click();
  }
  await expect(toggle).toBeChecked();
  // 关闭弹层，避免遮挡 composer 与发送按钮。
  await page.getByTitle('研究设置').click();
}

test('阅读 IDE 与 Agent 研究完成同一浏览器 smoke 主流程', async ({ page }) => {
  const mockState = await installMockApi(page);

  // 阅读 IDE：上传后左侧栏显示「当前论文」与文件名。
  await uploadPaper(page, 'smoke-paper.pdf');
  await expect(page.getByRole('button', { name: '阅读 IDE' })).toBeVisible();
  const sidebar = page.getByRole('complementary');
  await expect(sidebar.getByText('当前论文')).toBeVisible();
  await expect(sidebar.getByText('smoke-paper.pdf').first()).toBeVisible();

  // 论文库弹层：显示已上传论文并可打开。
  await page.getByRole('button', { name: '论文库' }).click();
  await expect(page.getByRole('heading', { name: '论文库' })).toBeVisible();
  await expect(page.getByText('Smoke 测试论文').first()).toBeVisible();
  await page.getByRole('button', { name: '打开' }).click();
  await expect(page.getByRole('heading', { name: '论文库' })).toBeHidden();
  await expect(sidebar.getByText('smoke-paper.pdf').first()).toBeVisible();

  // 阅读助手「更多工具」→「批判分析」→「开启批判性阅读」。
  await page.getByText('更多工具', { exact: true }).click();
  await page.getByRole('button', { name: '批判分析', exact: true }).click();
  await expect(page.getByRole('heading', { name: '开启批判性阅读' })).toBeVisible();

  // 切换到研究 Agent 并创建项目（论文自动选中）。
  await enterAgentWorkspace(page);
  await page.getByRole('button', { name: '新建项目' }).click();
  await page.getByPlaceholder('项目标题').fill('Smoke Agent 项目');
  await page.getByPlaceholder('项目目标').fill('验证任务历史和证据展示');
  await expect(page.getByText('1 篇已选')).toBeVisible();
  await page.getByRole('button', { name: '创建项目' }).click();
  await expect(page.getByRole('button', { name: 'Smoke Agent 项目', exact: true })).toBeVisible();

  const prompt = '比较论文的方法、证据与局限性';
  await page.getByLabel('创建研究任务').fill(prompt);
  await page.getByTitle('启动 Agent 任务').click();

  const chain = await expandResearchChain(page);
  await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '确认计划并执行' }).click();

  await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '确认终稿' }).click();
  await expect(chain.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });

  // 证据、工具调用在研究链内。
  await expect(chain.getByText('1 items').first()).toBeVisible({ timeout: 5_000 });
  await expect(chain.getByText('paper-smoke-1').first()).toBeVisible();
  await expect(chain.getByText('search_paper').first()).toBeVisible();
  await chain.getByRole('button', { name: '查看片段' }).first().click();
  await expect(chain.getByText('Smoke 论文采用可追踪检索流程验证方法设计。')).toBeVisible();

  // 报告正文渲染在最终结果草稿区。
  await expect(draftReportSection(page).getByText(/Smoke Agent 已完成证据检索并生成可追踪结论。/)).toBeVisible();

  expect(mockState.projectPayload).toEqual({
    title: 'Smoke Agent 项目',
    goal: '验证任务历史和证据展示',
    paperIds: ['paper-smoke-1'],
  });
  expect(mockState.taskPayload.prompt).toBe(prompt);
  expect(mockState.workspacePollCount).toBeGreaterThanOrEqual(2);
  expect(mockState.planReviewPayload.focusedPaperIds).toEqual(['paper-smoke-1']);
  expect(mockState.finalReviewPayload.riskReviews).toEqual([{ riskId: 'open:1', reviewStatus: 'reviewed' }]);
});

test('Agent 外部检索从显式授权到报告引用和终稿审查', async ({ page }) => {
  const mockState = await installExternalProviderRoute(page, { scenario: 'success' });
  await uploadPaper(page, 'external-search-paper.pdf');
  await enterAgentWorkspace(page);
  await createProject(page, '外部检索验证项目', '验证授权、来源和降级恢复');

  // composer 研究设置里开启「外部检索」。
  await enableComposerExternalSearch(page);

  await page.getByLabel('创建研究任务').fill('核查证据缺口并补充外部复现实验');
  await page.getByTitle('启动 Agent 任务').click();

  const chain = await expandResearchChain(page);
  await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });

  // 计划审查里开启「授权外部学术检索」开关（role=switch）。
  const planSwitch = page.getByRole('switch', { name: '授权外部学术检索' });
  await expect(planSwitch).toHaveAttribute('aria-checked', 'false');
  await planSwitch.click();
  await expect(planSwitch).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByText('外部学术检索已授权')).toBeVisible();
  await expect(page.getByText(/Provider: crossref/)).toBeVisible();
  await page.getByRole('button', { name: '确认计划并执行' }).click();

  await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });

  // 证据在研究链内：2 items（内部 + 外部），外部来源 chip 与详情。
  await expect(chain.getByText('2 items').first()).toBeVisible({ timeout: 5_000 });
  await expect(chain.getByText('外部来源 · crossref · 2022')).toBeVisible();
  await chain.getByRole('button', { name: '查看详情' }).first().click();
  await expect(chain.getByText('DOI: 10.3390/app12188972')).toBeVisible();

  await page.getByRole('button', { name: '确认终稿' }).click();
  await expect(chain.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });

  expect(mockState.taskPayload.allowExternalSearch).toBe(true);
  // 当前契约：计划审查表单以 run 响应初始化（不含 pendingReview.planItems），
  // 故提交的 planItems 为空；外部授权由 composer run payload 与计划审查 UI 证明。
  expect(mockState.planReviewPayload.focusedPaperIds).toEqual(['paper-external-1']);
  expect(mockState.finalReviewPayload.riskReviews).toEqual([{ riskId: 'external:1', reviewStatus: 'reviewed' }]);
});

test('Agent Provider 故障降级后可刷新恢复并完成人工审查', async ({ page }) => {
  const mockState = await installExternalProviderRoute(page, { scenario: 'failure' });
  await uploadPaper(page, 'external-search-paper.pdf');
  await enterAgentWorkspace(page);
  await createProject(page, '外部检索验证项目', '验证授权、来源和降级恢复');

  await enableComposerExternalSearch(page);
  await page.getByLabel('创建研究任务').fill('验证 Provider 故障降级');
  await page.getByTitle('启动 Agent 任务').click();

  await expandResearchChain(page);
  await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '确认计划并执行' }).click();

  const degradedText = 'External academic provider failed. 内部证据与未解决缺口均已保留。';
  await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });
  await expect(draftReportSection(page).getByText(degradedText, { exact: true })).toBeVisible();

  // 刷新后重新进入 Agent，降级草稿与终稿审查应恢复（run 状态持久化）。
  await page.reload();
  await enterAgentWorkspace(page);
  await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });
  await expect(draftReportSection(page).getByText(degradedText, { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '确认终稿' }).click();
  const chainAfterReload = await expandResearchChain(page);
  await expect(chainAfterReload.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });
  expect(mockState.workspacePollCount).toBeGreaterThanOrEqual(2);
});
