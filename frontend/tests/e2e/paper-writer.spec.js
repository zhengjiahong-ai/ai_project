/**
 * E2E tests for paper writer panel: generate, preview, download.
 */
import { test, expect } from '@playwright/test';
import { installMockApi } from '../fixtures/mockApi.js';
import { installMockPaperWriterApi } from '../fixtures/mockPaperWriterApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

async function uploadPdfAndOpenPaperWriter(page) {
  await installMockApi(page);
  await installMockPaperWriterApi(page);

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  await page.locator('input[type="file"]').setInputFiles({
    name: 'smoke-paper.pdf',
    mimeType: 'application/pdf',
    buffer: createSmokePdfBuffer(),
  });

  // Navigate workspace panel using JS DOM operations
  await page.evaluate(() => {
    var navToggle = document.querySelector('.workspace-nav-toggle');
    if (navToggle) navToggle.click();
  });
  await page.waitForTimeout(500);

  await page.evaluate(() => {
    var chips = Array.from(document.querySelectorAll('button.workflow-stage-chip'));
    var analysisChip = chips.find(function (c) { return c.textContent && c.textContent.includes('深度探究'); });
    if (analysisChip) analysisChip.click();
  });
  await page.waitForTimeout(500);

  await page.evaluate(() => {
    var tabs = Array.from(document.querySelectorAll('button.workspace-tab-button'));
    var writerTab = tabs.find(function (t) { return t.textContent && t.textContent.includes('论文写作'); });
    if (writerTab) writerTab.click();
  });
  await page.waitForTimeout(500);

  await expect(page.getByPlaceholder(/研究问题/)).toBeVisible({ timeout: 5000 });
}

test.describe('Paper Writer Panel', () => {
  test('generate paper draft and verify sections', async ({ page }) => {
    await uploadPdfAndOpenPaperWriter(page);

    await page.getByPlaceholder(/研究问题/).fill('graph neural networks for molecular property prediction');
    await page.getByRole('button', { name: /生成论文草稿/ }).click();

    await expect(page.getByText(/草稿生成完成/)).toBeVisible({ timeout: 15000 });

    await expect(page.getByText(/Abstract/).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/Introduction/).first()).toBeVisible();
  });

  test('download buttons are present after generation', async ({ page }) => {
    await uploadPdfAndOpenPaperWriter(page);

    await page.getByPlaceholder(/研究问题/).fill('transformer attention mechanisms');
    await page.getByRole('button', { name: /生成论文草稿/ }).click();
    await expect(page.getByText(/草稿生成完成/)).toBeVisible({ timeout: 15000 });

    await expect(page.getByRole('button', { name: 'Markdown' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'LaTeX' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'BibTeX' }).first()).toBeVisible();
  });
});
