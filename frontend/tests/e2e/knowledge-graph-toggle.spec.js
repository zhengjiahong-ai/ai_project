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
  await page.getByRole('button', { name: 'Agent 研究', exact: true }).click();
  await expect(page.getByText('Agent 学术研究工作台')).toBeVisible();
}

async function createProject(page) {
  await page.getByPlaceholder('项目标题').fill('KG Toggle Test');
  await page.getByPlaceholder('项目目标').fill('Verify knowledge graph toggle behavior');
  await page.getByTitle('创建项目').click();
  await expect(page.getByRole('heading', { name: 'KG Toggle Test' })).toBeVisible();
}

const kgToggle = (page) =>
  page.getByRole('switch', { name: '使用知识图谱补充证据' });

test.describe('Knowledge Graph Toggle', () => {
  test('knowledge graph toggle is enabled by default', async ({ page }) => {
    await installMockApi(page);
    await navigateToAgentWorkspace(page);
    await createProject(page);

    const toggle = kgToggle(page);
    await expect(toggle).toBeVisible({ timeout: 5_000 });
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  test('turning off knowledge graph sends allowKnowledgeGraph: false in task payload', async ({ page }) => {
    const mockState = await installMockApi(page);
    await navigateToAgentWorkspace(page);
    await createProject(page);

    const toggle = kgToggle(page);
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', 'false');

    await page.getByPlaceholder(/让 Agent 比较/).fill('KG toggle off test prompt');
    await page.getByTitle('启动 Agent 任务').click();

    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });

    expect(mockState.taskPayload).not.toBeNull();
    expect(mockState.taskPayload.allowKnowledgeGraph).toBe(false);
  });

  test('knowledge graph evidence items appear in the Tools & Evidence panel', async ({ page }) => {
    await installMockApi(page, { evidenceItems: KG_EVIDENCE_ITEMS });
    await navigateToAgentWorkspace(page);
    await createProject(page);

    await page.getByPlaceholder(/让 Agent 比较/).fill('Test KG evidence rendering');
    await page.getByTitle('启动 Agent 任务').click();

    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();

    await expect(page.getByText('研究任务已完成')).toBeVisible({ timeout: 10_000 });

    const evidencePanel = page.locator('aside').filter({ hasText: 'Tools & Evidence' });
    await expect(evidencePanel).toBeVisible({ timeout: 5_000 });
    await expect(evidencePanel.getByText('3 items').first()).toBeVisible({ timeout: 5_000 });
    await expect(evidencePanel.getByText('knowledge_graph').first()).toBeVisible({ timeout: 5_000 });
    await expect(evidencePanel.getByText('paper').first()).toBeVisible();
  });
});
