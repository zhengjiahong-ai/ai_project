/**
 * E2E tests for paper writer panel: generate, preview, download.
 */
import { test, expect } from '@playwright/test';
import { installMockPaperWriterApi } from '../fixtures/mockPaperWriterApi.js';

test.describe('Paper Writer Panel', () => {
  test('generate paper draft and verify sections', async ({ page }) => {
    await installMockPaperWriterApi(page);

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Navigate to paper writer tab
    const writerTab = page.getByText('论文写作');
    if (await writerTab.isVisible()) {
      await writerTab.click();
    }

    // Fill in research question
    const questionInput = page.getByPlaceholder(/输入研究问题/);
    if (await questionInput.isVisible()) {
      await questionInput.fill('graph neural networks for molecular property prediction');
    }

    // Click generate button
    const generateBtn = page.getByRole('button', { name: /生成论文草稿/ });
    if (await generateBtn.isVisible()) {
      await generateBtn.click();
    }

    // Wait for generation to complete (status: done)
    await expect(page.getByText(/草稿生成完成/)).toBeVisible({ timeout: 15000 });

    // Verify section headings are visible
    await expect(page.getByText('Abstract')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Introduction')).toBeVisible();
  });

  test('download buttons are present after generation', async ({ page }) => {
    await installMockPaperWriterApi(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const writerTab = page.getByText('论文写作');
    if (await writerTab.isVisible()) await writerTab.click();

    const questionInput = page.getByPlaceholder(/输入研究问题/);
    if (await questionInput.isVisible()) {
      await questionInput.fill('transformer attention mechanisms');
    }

    await page.getByRole('button', { name: /生成论文草稿/ }).click();
    await expect(page.getByText(/草稿生成完成/)).toBeVisible({ timeout: 15000 });

    // Verify download links
    await expect(page.getByText('Markdown')).toBeVisible();
    await expect(page.getByText('LaTeX')).toBeVisible();
    await expect(page.getByText('BibTeX')).toBeVisible();
  });
});
