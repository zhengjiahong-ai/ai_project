/**
 * Knowledge Graph Toggle E2E Tests.
 */
import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

const KG_EVIDENCE_ITEMS = [
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
];

async function navigateToAgentWorkspace(page) {
  await page.goto('/');
  await expect(page.getByText('Pixiu Academic Assistant')).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: 'kg-paper.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });
  // 顶栏模式切换到「研究 Agent」，侧栏出现「新建项目」即表示工作台已就绪。
  await page.getByRole('button', { name: '研究 Agent' }).click();
  await expect(page.getByRole('button', { name: '新建项目' })).toBeVisible();
}

async function createProject(page) {
  // 创建表单现在位于侧栏「新建项目」弹层中。
  await page.getByRole('button', { name: '新建项目' }).click();
  await page.getByPlaceholder('项目标题').fill('KG Toggle Test');
  await page.getByPlaceholder('项目目标').fill('Verify knowledge graph toggle behavior');
  await page.getByRole('button', { name: '创建项目' }).click();
  await expect(page.getByRole('button', { name: 'KG Toggle Test', exact: true })).toBeVisible();
}

// 研究设置（含图谱补充开关）位于 composer 的「研究设置」弹出面板内。
const openResearchSettings = (page) => page.getByTitle('研究设置').click();
const kgToggle = (page) => page.getByRole('checkbox', { name: '图谱补充' });

// 计划审查表单位于默认折叠的「研究链」内，交互前需先展开。
async function expandResearchChain(page) {
  const chain = page.locator('details.agent-research-chain');
  await expect(page.getByText('研究链 · 点击展开完整过程')).toBeVisible({ timeout: 10_000 });
  if (!(await chain.evaluate((el) => el.open))) {
    await page.getByText('研究链 · 点击展开完整过程').click();
  }
  return chain;
}

test.describe('Knowledge Graph Toggle', () => {
  test('knowledge graph toggle is enabled by default', async ({ page }) => {
    await installMockApi(page);
    await navigateToAgentWorkspace(page);
    await createProject(page);

    await openResearchSettings(page);
    const toggle = kgToggle(page);
    await expect(toggle).toBeVisible({ timeout: 5_000 });
    await expect(toggle).toBeChecked();
  });

  test('turning off knowledge graph sends allowKnowledgeGraph: false in task payload', async ({ page }) => {
    const mockState = await installMockApi(page);
    await navigateToAgentWorkspace(page);
    await createProject(page);

    await openResearchSettings(page);
    const toggle = kgToggle(page);
    await expect(toggle).toBeChecked();
    await toggle.click();
    await expect(toggle).not.toBeChecked();
    // 关闭弹层，避免遮挡 composer 与发送按钮。
    await openResearchSettings(page);

    await page.getByLabel('创建研究任务').fill('KG toggle off test prompt');
    await page.getByTitle('启动 Agent 任务').click();

    await expandResearchChain(page);
    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });

    expect(mockState.taskPayload).not.toBeNull();
    expect(mockState.taskPayload.allowKnowledgeGraph).toBe(false);
  });

  test('knowledge graph evidence items appear in the research chain evidence list', async ({ page }) => {
    await installMockApi(page, { evidenceItems: KG_EVIDENCE_ITEMS });
    await navigateToAgentWorkspace(page);
    await createProject(page);

    await page.getByLabel('创建研究任务').fill('Test KG evidence rendering');
    await page.getByTitle('启动 Agent 任务').click();

    const chain = await expandResearchChain(page);
    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();

    await expect(chain.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });
    await expect(chain.getByText('3 items').first()).toBeVisible({ timeout: 5_000 });
    await expect(chain.getByText('knowledge_graph').first()).toBeVisible({ timeout: 5_000 });
    await expect(chain.getByText('paper').first()).toBeVisible();
  });
});
