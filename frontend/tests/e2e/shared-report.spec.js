/**
 * Shared Report Page E2E Tests (17-4).
 *
 * Verifies the read-only shared-report view at /share/:token:
 * 1. A valid token renders the report sections (Task / Executive Summary /
 *    Current Conclusion) and shows the "分享视图 · 只读" banner.
 * 2. An expired or invalid token displays the "链接已过期" empty state.
 */
import { expect, test } from '@playwright/test';

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
  '基于对选定论文的系统性分析，三项研究在方法设计上存在显著差异：',
  'Study A 采用随机对照试验（RCT），Study B 使用观察性队列研究，',
  'Study C 则依赖计算模拟。尽管方法不同，三项研究在核心结论上',
  '表现出中等一致性（avg credibility 0.72, level: **high**）。',
  '',
  '## Current Conclusion',
  '',
  '综合证据表明，跨方法验证的结果增强了主结论的可信度。然而，',
  '模拟结果的外部有效性仍需进一步实证验证。',
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
 * @param {'valid'|'expired'|'not-found'|'server-error'} scenario
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
        if (token === 'valid-token-123') {
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

      case 'server-error':
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'error', message: '服务器内部错误。' }),
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

    await page.goto('/share/valid-token-123');
    await page.waitForLoadState('networkidle');

    // The read-only banner should be visible.
    await expect(page.getByText('分享视图 · 只读')).toBeVisible();

    // The project title should be displayed as an h1.
    await expect(page.getByRole('heading', { name: 'Cross-Paper Comparative Analysis' })).toBeVisible();

    // The report sections should appear (they are rendered as separate
    // line-paragraph divs inside the main content area).
    await expect(page.getByText(/比较三篇论文的研究方法/)).toBeVisible();
    await expect(page.getByText(/基于对选定论文的系统性分析/)).toBeVisible();
    await expect(page.getByText(/综合证据表明/)).toBeVisible();

    // Expiry info should be shown in the header.
    await expect(page.getByText(/过期时间/)).toBeVisible();

    // There should be NO edit controls — this is a read-only view.
    // Verify no input fields or action buttons are present.
    const mainContent = page.locator('main');
    await expect(mainContent.locator('input, textarea, button')).toHaveCount(0);

    // Verify the page structure: header with Shield icon + banner text.
    const header = page.locator('header');
    await expect(header.getByText('分享视图 · 只读')).toBeVisible();
  });

  test('expired token shows "链接已过期" empty state', async ({ page }) => {
    await installSharedReportMock(page, 'expired');

    await page.goto('/share/expired-token-456');
    await page.waitForLoadState('networkidle');

    // The empty-state heading should be visible.
    await expect(page.getByRole('heading', { name: '链接已过期' })).toBeVisible();

    // The error message should explain the situation.
    await expect(page.getByText('该分享链接已过期。')).toBeVisible();

    // No report content should be rendered.
    await expect(page.getByRole('heading', { name: 'Cross-Paper Comparative Analysis' })).not.toBeVisible();
    await expect(page.getByText('分享视图 · 只读')).not.toBeVisible();

    // The AlertTriangle iconarea should be present (empty-state visual).
    // The component renders the empty state with a dashed border container.
    const emptyState = page.locator('.border-dashed');
    await expect(emptyState).toBeVisible();
  });

  test('invalid / non-existent token shows "链接已过期" empty state', async ({ page }) => {
    await installSharedReportMock(page, 'not-found');

    await page.goto('/share/nonexistent-token');
    await page.waitForLoadState('networkidle');

    // Should show the same empty-state pattern.
    await expect(page.getByRole('heading', { name: '链接已过期' })).toBeVisible();
    await expect(page.getByText('分享链接不存在或已被删除。')).toBeVisible();

    // No read-only banner or report content.
    await expect(page.getByText('分享视图 · 只读')).not.toBeVisible();
  });
});
