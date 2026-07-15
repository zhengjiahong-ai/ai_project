/**
 * Mock /api/research-monitors endpoints for E2E tests.
 */
let monitorIdCounter = 0;

export function installMockResearchMonitorApi(page) {
  const monitors = [];

  return page.route('**/api/research-monitors**', async (route) => {
    const request = route.request();
    const method = request.method();
    const url = request.url();

    // GET /research-monitors — list all
    if (method === 'GET' && url.endsWith('/research-monitors')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success', monitors }),
      });
    }

    // POST /research-monitors — create
    if (method === 'POST' && url.endsWith('/research-monitors')) {
      const body = request.postDataJSON() || {};
      monitorIdCounter += 1;
      const monitor = {
        monitorId: `mon-${monitorIdCounter}`,
        query: body.query || 'test query',
        source: body.source || 'arxiv',
        label: body.label || '',
        status: 'active',
        createdAt: new Date().toISOString(),
        paperCount: 0,
      };
      monitors.push(monitor);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success', task: monitor }),
      });
    }

    // GET /research-monitors/:id/check — check for new papers
    if (method === 'GET' && url.includes('/check')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          papers: [
            { title: 'New Paper 1: Advances in Testing', relevance: 0.92, url: 'https://arxiv.org/abs/2401.00001', year: 2024 },
            { title: 'New Paper 2: E2E Test Automation', relevance: 0.85, url: 'https://arxiv.org/abs/2401.00002', year: 2024 },
          ],
          newCount: 2,
        }),
      });
    }

    // GET /research-monitors/:id/digest — get digest
    if (method === 'GET' && url.includes('/digest')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          digest: {
            summary: '研究发现：最近有两篇新论文涉及 E2E 测试自动化领域。',
            keyFindings: ['测试自动化工具正在快速发展', 'AI 辅助测试成为新趋势'],
            recommendations: ['建议关注自动化测试框架的更新'],
          },
        }),
      });
    }

    // DELETE /research-monitors/:id — deactivate
    if (method === 'DELETE') {
      const id = url.split('/').pop();
      const idx = monitors.findIndex((m) => m.monitorId === id);
      if (idx >= 0) {
        monitors[idx].status = 'inactive';
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success' }),
      });
    }

    return route.fulfill({ status: 404, body: '{}' });
  });
}
