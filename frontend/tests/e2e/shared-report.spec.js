/**
 * Shared Report Page E2E Tests (17-4).
 *
 * Verifies the read-only shared-report view at /share/:token:
 * 1. A valid token renders the report sections and shows the "分享视图 · 只读" banner.
 * 2. An expired or invalid token displays the "链接已过期" empty state.
 */
import { expect, test } from '@playwright/test';

// Tokens MUST be hex-only — App.jsx route regex: /^\/share\/([a-f0-9]+)$/i
const VALID_TOKEN = 'abc123def456';
const EXPIRED_TOKEN = 'fed789cba012';
const INVALID_TOKEN = 'deadbeef9999';

const NOW = '2026-07-25T14:00:00.000Z';
const EXPIRES = '2026-08-25T14:00:00.000Z';

// ── Sample shared report content ────────────────────────────────────────────
const VALID_REPORT = [
  '## Task',
  '',
  '比较三篇论文的研究方法、实验设计与结论可靠性，生成跨论文证据对比报告。',
  '',
  '## Executive Summary',
  '',
  '基于对选定论文的系统性分析，三项研究在方法设计上存在显著差异。',
  '',
  '## Current Conclusion',
  '',
  '综合证据表明，跨方法验证的结果增强了主结论的可信度。',
].join('\n');

const VALID_SHARE_DATA = {
  report: VALID_REPORT,
  projectTitle: 'Cross-Paper Comparative Analysis',
  expiresAt: EXPIRES,
};

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Install a route handler for the shared-report API endpoint.
 *
 * @param {import('@playwright/test').Page} page
 * @param {'valid'|'expired'|'not-found'} scenario
 */
async function installSharedReportMock(page, scenario = 'valid') {
  await page.route('**/api/shared/**', async (route) => {
    const url = new URL(route.request().url());
    const pathParts = url.pathname.split('/');
    const token = pathParts[pathParts.length - 1];
    const method = route.request().method();

    if (method !== 'GET') {
      await route.fallback();
      return;
    }

    switch (scenario) {
      case 'valid':
        if (token === VALID_TOKEN) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ status: 'success', share: VALID_SHARE_DATA }),
          });
          return;
        }
        break;

      case 'expired':
        await route.fulfill({
          status: 410,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'error', message: '该分享链接已过期。' }),
        });
        return;

      case 'not-found':
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'error', message: '分享链接不存在或已被删除。' }),
        });
        return;

      default:
        break;
    }

    await route.fallback();
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('Shared Report Page', () => {
  test('valid token renders read-only report with all expected sections', async ({ page }) => {
    await installSharedReportMock(page, 'valid');

    await page.goto(`/share/${VALID_TOKEN}`);
    await page.waitForLoadState('networkidle');

    // The read-only banner should be visible.
    await expect(page.getByText('分享视图 · 只读')).toBeVisible({ timeout: 10_000 });

    // The project title should be displayed as an h1.
    await expect(page.getByRole('heading', { name: 'Cross-Paper Comparative Analysis' })).toBeVisible();

    // The report sections should appear.
    await expect(page.getByText(/比较三篇论文的研究方法/)).toBeVisible();
    await expect(page.getByText(/基于对选定论文的系统性分析/)).toBeVisible();
    await expect(page.getByText(/综合证据表明/)).toBeVisible();

    // Expiry info should be shown in the header.
    await expect(page.getByText(/过期时间/)).toBeVisible();

    // Verify the page structure: header with Shield icon + banner text.
    const header = page.locator('header');
    await expect(header.getByText('分享视图 · 只读')).toBeVisible();
  });

  test('expired token shows "链接已过期" empty state', async ({ page }) => {
    await installSharedReportMock(page, 'expired');

    await page.goto(`/share/${EXPIRED_TOKEN}`);
    await page.waitForLoadState('networkidle');

    // The empty-state heading should be visible.
    await expect(page.getByRole('heading', { name: '链接已过期' })).toBeVisible({ timeout: 10_000 });

    // The error message should explain the situation.
    await expect(page.getByText('该分享链接已过期。')).toBeVisible();

    // No read-only banner or report content.
    await expect(page.getByText('分享视图 · 只读')).not.toBeVisible();

    // The empty-state container should be present (dashed border).
    const emptyState = page.locator('.border-dashed');
    await expect(emptyState).toBeVisible();
  });

  test('invalid / non-existent token shows "链接已过期" empty state', async ({ page }) => {
    await installSharedReportMock(page, 'not-found');

    await page.goto(`/share/${INVALID_TOKEN}`);
    await page.waitForLoadState('networkidle');

    // Should show the same empty-state pattern.
    await expect(page.getByRole('heading', { name: '链接已过期' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('分享链接不存在或已被删除。')).toBeVisible();

    // No read-only banner or report content.
    await expect(page.getByText('分享视图 · 只读')).not.toBeVisible();
  });
});
