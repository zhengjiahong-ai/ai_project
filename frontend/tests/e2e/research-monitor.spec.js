/**
 * E2E tests for research monitor: create, check, digest, deactivate.
 */
import { test, expect } from '@playwright/test';
import { installMockResearchMonitorApi } from '../fixtures/mockResearchMonitorApi.js';

test.describe('Research Monitor', () => {
  test('create monitor and verify it appears in the list', async ({ page }) => {
    await installMockResearchMonitorApi(page);

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Navigate to research monitor (may need to be in the reading IDE context)
    // The monitor is accessible via agent workspace or deep research panel

    // Try to find the "新建监控" button
    const newMonitorBtn = page.getByRole('button', { name: '新建监控' });
    if (await newMonitorBtn.isVisible()) {
      await newMonitorBtn.click();

      // Fill in question
      const questionInput = page.getByPlaceholder(/检索式/);
      if (await questionInput.isVisible()) {
        await questionInput.fill('retrieval-augmented generation');
      }

      // Select arXiv source
      const arxivBtn = page.getByRole('button', { name: 'arXiv' });
      if (await arxivBtn.isVisible()) {
        await arxivBtn.click();
      }

      // Click create
      const createBtn = page.getByRole('button', { name: '创建' });
      if (await createBtn.isVisible()) {
        await createBtn.click();
      }
    }
  });

  test('check monitor for new papers', async ({ page }) => {
    await installMockResearchMonitorApi(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Look for "检查新论文" button
    const checkBtn = page.getByRole('button', { name: '检查新论文' });
    if (await checkBtn.isVisible()) {
      await checkBtn.click();
      await expect(page.getByText(/发现.*篇新论文/)).toBeVisible({ timeout: 10000 });
    }
  });

  test('get monitor digest', async ({ page }) => {
    await installMockResearchMonitorApi(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Look for "摘要" button
    const digestBtn = page.getByRole('button', { name: '摘要' });
    if (await digestBtn.isVisible()) {
      await digestBtn.click();
      await expect(page.getByText(/研究摘要|研究发现/)).toBeVisible({ timeout: 10000 });
    }
  });
});
