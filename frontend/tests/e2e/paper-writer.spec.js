/**
 * E2E tests for paper writer panel: generate, preview, download.
 */
import { test, expect } from '@playwright/test';
import { installMockApi } from '../fixtures/mockApi.js';
import { installMockPaperWriterApi } from '../fixtures/mockPaperWriterApi.js';
import { createSmokePdfBuffer } from '../fixtures/smokePdf.js';

test.describe('Paper Writer Panel', () => {
  test('generate paper draft and verify sections', async ({ page }) => {
    await installMockApi(page);
    await installMockPaperWriterApi(page);

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Upload a PDF first so the workspace tabs (including paper-writer) are visible
    await page.locator('input[type="file"]').setInputFiles({
      name: 'smoke-paper.pdf',
      mimeType: 'application/pdf',
      buffer: createSmokePdfBuffer(),
    });

    // Navigate to paper writer tab via the workspace panel navigation
    const workspacePanels = page.locator('.workspace-top-panels');
    await workspacePanels.hover();
    // Click the stage chip with title "论文写作"
    const writerChip = workspacePanels.locator('[title*="论文"]').or(
      page.getByRole('button', { name: /论文写作/ }),
    );
    await writerChip.first().click({ timeout: 5000 });

    // Fill in research question
    const questionInput = page.getByPlaceholder(/研究问题/);
    await expect(questionInput).toBeVisible({ timeout: 5000 });
    await questionInput.fill('graph neural networks for molecular property prediction');

    // Click generate button
    await page.getByRole('button', { name: /生成论文草稿/ }).click();

    // Wait for generation to complete
    await expect(page.getByText(/草稿生成完成/)).toBeVisible({ timeout: 15000 });

    // Verify section headings are visible
    await expect(page.getByText('Abstract')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Introduction')).toBeVisible();
  });

  test('download buttons are present after generation', async ({ page }) => {
    await installMockApi(page);
    await installMockPaperWriterApi(page);

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await page.locator('input[type="file"]').setInputFiles({
      name: 'smoke-paper.pdf',
      mimeType: 'application/pdf',
      buffer: createSmokePdfBuffer(),
    });

    await page.locator('.workspace-top-panels').hover();
    const chip = page.locator('.workspace-top-panels [title*="论文"]').or(
      page.getByRole('button', { name: /论文写作/ }),
    );
    await chip.first().click({ timeout: 5000 });

    const questionInput = page.getByPlaceholder(/研究问题/);
    await expect(questionInput).toBeVisible({ timeout: 5000 });
    await questionInput.fill('transformer attention mechanisms');

    await page.getByRole('button', { name: /生成论文草稿/ }).click();
    await expect(page.getByText(/草稿生成完成/)).toBeVisible({ timeout: 15000 });

    // Verify download links
    await expect(page.getByText('Markdown')).toBeVisible();
    await expect(page.getByText('LaTeX')).toBeVisible();
    await expect(page.getByText('BibTeX')).toBeVisible();
  });
});
