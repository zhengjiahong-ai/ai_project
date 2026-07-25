/**
 * Agent Report Confidence E2E Tests (17-1).
 */
import { expect, test } from '@playwright/test';

import { installMockApi } from '../fixtures/mockApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

const STRUCTURED_REPORT = [
  '### Consensus Findings',
  'Method X consistently outperforms all baselines across every benchmark suite. (avg credibility 0.92, level: **high**)',
  '### Contested Findings',
  'The reported effect size varies substantially between Study A and Study B. (avg credibility 0.55, level: **medium**)',
  '### Single-Source Findings',
  'Only one preprint reports this outlier result without replication. (avg credibility 0.32, level: **low**)',
].join('\n');

const OLD_REPORT = [
  '## Current Conclusion',
  'Smoke Agent 已完成证据检索并生成可追踪结论。整体方法论较为稳健，但存在若干未解决的开放问题。',
].join('\n');

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

test.describe('Agent Report Confidence Badges', () => {
  test('structured report renders confidence badges with correct colors', async ({ page }) => {
    await installMockApi(page, { draftReport: STRUCTURED_REPORT });
    await navigateToAgentWorkspace(page);
    await createProjectAndTask(page);

    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();

    await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('最终结果草稿')).toBeVisible();
    await expect(page.getByText(/Method X consistently outperforms/)).toBeVisible({ timeout: 5_000 });

    await expect(page.getByText('高置信度')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('中等置信度')).toBeVisible();
    await expect(page.getByText('低置信度')).toBeVisible();

    await expect(page.getByText('Consensus Findings')).toBeVisible();
    await expect(page.getByText('Contested Findings')).toBeVisible();
    await expect(page.getByText('Single-Source Findings')).toBeVisible();

    const highBadge = page.getByText('高置信度');
    expect(await highBadge.evaluate((el) => getComputedStyle(el).color))
      .toMatch(/rgb\(22,\s*163,\s*74\)/);

    const mediumBadge = page.getByText('中等置信度');
    expect(await mediumBadge.evaluate((el) => getComputedStyle(el).color))
      .toMatch(/rgb\(202,\s*138,\s*4\)/);

    const lowBadge = page.getByText('低置信度');
    expect(await lowBadge.evaluate((el) => getComputedStyle(el).color))
      .toMatch(/rgb\(217,\s*119,\s*6\)/);
  });

  test('Consensus/Contested/Single-Source sections have distinct left border colors', async ({ page }) => {
    await installMockApi(page, { draftReport: STRUCTURED_REPORT });
    await navigateToAgentWorkspace(page);
    await createProjectAndTask(page);

    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();
    await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });

    const draftReportSection = page.locator('details').filter({ hasText: '最终结果草稿' });
    await expect(draftReportSection).toBeVisible();

    const sectionHeaders = draftReportSection.locator('.agent-card.font-semibold.text-sm');
    await expect(sectionHeaders).toHaveCount(3);

    const borderColors = await sectionHeaders.evaluateAll((els) =>
      els.map((el) => getComputedStyle(el).borderLeftColor),
    );

    expect(borderColors[0]).toMatch(/rgb\(22,\s*163,\s*74\)/);   // green
    expect(borderColors[1]).toMatch(/rgb\(217,\s*119,\s*6\)/);    // amber
    // Single-Source → muted gray (exact value depends on --text-muted CSS variable)
    expect(borderColors[2]).not.toBe(borderColors[0]);
    expect(borderColors[2]).not.toBe(borderColors[1]);
  });

  test('old report without structured sections renders no confidence badges', async ({ page }) => {
    await installMockApi(page, { draftReport: OLD_REPORT });
    await navigateToAgentWorkspace(page);
    await createProjectAndTask(page);

    await expect(page.getByText('确认论文范围、约束和研究指令后才会执行')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '确认计划并执行' }).click();
    await expect(page.getByText('终稿人工审查')).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText('最终结果草稿')).toBeVisible();
    await expect(page.getByText(/Smoke Agent 已完成证据检索/)).toBeVisible();

    await expect(page.getByText('高置信度')).not.toBeVisible();
    await expect(page.getByText('中等置信度')).not.toBeVisible();
    await expect(page.getByText('低置信度')).not.toBeVisible();
    await expect(page.getByText('证据不足')).not.toBeVisible();
    await expect(page.getByText('Consensus Findings')).not.toBeVisible();
    await expect(page.getByText('Contested Findings')).not.toBeVisible();
    await expect(page.getByText('Single-Source Findings')).not.toBeVisible();
  });
});
