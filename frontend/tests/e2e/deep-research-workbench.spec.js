import { test, expect } from '@playwright/test';

// Exercise the real workbench with a closed API fixture. No model, user data or
// live backend is involved; this proves UI behavior, not research quality.
const TASK = 'dr-ui-fixture';
const RUN = 'dr-ui-run';
const BODY = '本回答引用：全文片段。\n\n编码器输出时空特征，解码器将特征映射为形变。[[1]](#research-evidence-e1)\n\n尚缺独立数据集的泛化比较。';
const QUOTE = 'The decoder maps the encoded features to deformation parameters.';

async function mountResearch(page) {
  const unexpected = [];
  const mutations = [];
  const source = { sourceId: 's1', evidenceIds: ['e1'], sourceKind: 'arxiv',
    title: 'Research UI fixture paper', accessLevel: 'fulltext', page: 4,
    url: 'https://arxiv.org/abs/2310.08528v3', quote: QUOTE,
    evidenceQuotes: { e1: { quote: QUOTE, location: { page: 4 } } } };
  const artifact = { id: 'dr-ui-report', title: '编码器与解码器分工', text: BODY,
    sourceRunId: RUN, sourceResearchId: RUN, engineVersion: 'deep-research-v2',
    reportVersionId: 'v1', origin: 'latest', sources: [source], paperIds: [], versions: [] };
  let task = { id: TASK, title: '研究交互测试', revision: 1, paperIds: [],
    focusedPaperId: null, activeActivity: null, messages: [], notes: [], artifacts: [artifact],
    researchRuns: [{ researchId: RUN, question: '解释编码器与解码器各自负责什么。', createdAt: '2026-10-13T00:00:00Z' }],
    activityHistory: [], updatedAt: '2026-10-13T00:00:00Z' };
  const result = { contractVersion: 2, runId: RUN, taskId: TASK, runRevision: 4,
    status: 'completed', outcome: 'partial', title: artifact.title, report: BODY,
    reportVersionId: 'v1', summary: '本回答引用：全文片段。编码器提取时空特征，解码器预测形变；泛化效果还缺证据。',
    sourceCount: 1, sources: [source], allowedActions: ['continue'],
    plan: [{ itemId: 'p1', question: '区分编码与解码的输入输出', status: 'completed' }],
    events: [{ eventId: 'ev1', label: '核对原文', status: 'completed' }] };
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      unexpected.push(`external ${request.url()}`);
      return route.abort();
    }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const path = decodeURIComponent(url.pathname), method = request.method();
    const send = json => route.fulfill({ json });
    if (method === 'GET' && path === '/api/task-workspaces') return send([task]);
    if (method === 'GET' && path === `/api/task-workspaces/${TASK}`) return send(task);
    if (method === 'GET' && [`/api/task-workspaces/${TASK}/materials`, `/api/task-workspaces/${TASK}/operations`].includes(path)) return send([]);
    if (method === 'GET' && path === `/api/task-workspaces/${TASK}/research/capabilities`) return send({ enabled: true, externalSearch: true });
    if (method === 'GET' && path === `/api/task-workspaces/${TASK}/research/${RUN}`) return send({ task: result, workspace: task });
    if (method === 'PUT' && path === `/api/task-workspaces/${TASK}`) {
      const input = request.postDataJSON();
      mutations.push(input);
      if (input.revision !== task.revision) return route.fulfill({ status: 409, json: { message: 'revision conflict' } });
      task = { ...input, revision: task.revision + 1, updatedAt: '2026-10-13T01:00:00Z' };
      return send(task);
    }
    unexpected.push(`${method} ${path}`);
    return route.fulfill({ status: 501, json: { message: 'No live API calls allowed in this test' } });
  });
  await page.goto('/');
  const card = page.getByRole('article', { name: '研究结果' });
  await expect(card).toContainText('已完成部分研究');
  return { card, unexpected, mutations, getTask: () => task };
}

for (const viewport of [{ width: 1366, height: 768 }, { width: 1440, height: 900 },
  { width: 1093, height: 614 }, { width: 1152, height: 720 }]) {
  test(`research results and controls fit ${viewport.width}x${viewport.height} CSS pixels`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const { card, unexpected } = await mountResearch(page);
    await expect(page.getByRole('region', { name: '研究详情' })).toHaveCount(0);
    const composer = page.locator('.workbench-composer-container');
    const bounds = await composer.boundingBox();
    expect(bounds.height).toBeLessThanOrEqual(Math.min(180, viewport.height * .25) + 2);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height + 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    expect(await page.locator('#unified-navigation').textContent()).not.toContain('research-evidence-');
    await page.screenshot({ path: testInfo.outputPath('research-card.png') });

    for (const [label, heading] of [['功能', '选择功能'], ['对话材料', '本轮对话材料']]) {
      const trigger = page.getByRole('button', { name: label, exact: true });
      await trigger.click();
      await expect(page.getByText(heading, { exact: true })).toBeVisible();
      await card.locator('strong').click();
      await expect(page.getByText(heading, { exact: true })).toHaveCount(0);
      await trigger.click();
      await page.keyboard.press('Escape');
      await expect(trigger).toBeFocused();
    }
    await page.getByRole('textbox', { name: '输入问题' }).fill('未发送的研究草稿');
    await page.getByRole('button', { name: '展开输入' }).click();
    const fullInput = page.getByRole('dialog', { name: '全屏输入' });
    await expect(fullInput).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(fullInput).toHaveCount(0);
    await expect(page.getByRole('textbox', { name: '输入问题' })).toHaveValue('未发送的研究草稿');

    const details = card.getByRole('button', { name: /来源与详情/ });
    await details.click();
    await card.getByRole('tab', { name: '资料' }).click();
    await expect(card.getByText('全文片段', { exact: true })).toBeVisible();
    await card.getByText('原文依据', { exact: true }).click();
    await expect(card.getByText(QUOTE, { exact: true })).toBeVisible();
    await card.getByRole('button', { name: '关闭研究详情' }).click();
    await expect(details).toBeFocused();

    await card.getByRole('button', { name: '查看已有结果' }).click();
    const report = page.getByRole('article', { name: '成果正文' });
    await expect(report).toContainText('尚缺独立数据集');
    const citation = report.getByRole('button', { name: /查看引用/ });
    await citation.click();
    const preview = page.getByRole('dialog', { name: '引用依据' });
    await expect(preview.getByText(QUOTE, { exact: true })).toBeVisible();
    await expect(preview).toContainText('第 4 页');
    await expect(preview.getByRole('link', { name: '查看来源页面' })).toHaveAttribute('href', 'https://arxiv.org/abs/2310.08528v3');
    const previewBounds = await preview.boundingBox();
    expect(previewBounds.x).toBeGreaterThanOrEqual(0);
    expect(previewBounds.x + previewBounds.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(previewBounds.y + previewBounds.height).toBeLessThanOrEqual(viewport.height + 1);
    await page.keyboard.press('Escape');
    await expect(citation).toBeFocused();
    await page.screenshot({ path: testInfo.outputPath('research-report.png') });
    expect(unexpected).toEqual([]);
  });
}

test('saved research edits survive refresh and the original remains recoverable', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  const state = await mountResearch(page);
  await state.card.getByRole('button', { name: '查看已有结果' }).click();
  await page.getByRole('button', { name: '编辑', exact: true }).click();
  const revised = BODY + '\n\n我的补充：下一步单独比较泛化效果。';
  await page.getByRole('textbox', { name: '编辑笔记与成果' }).fill(revised);
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(page.getByText('已保存', { exact: true }).first()).toBeVisible();
  expect(state.getTask().artifacts[0].text).toBe(revised);
  expect(state.getTask().artifacts[0].versions.at(-1).text).toBe(BODY);
  await page.reload();
  await expect(page.getByRole('article', { name: '成果正文' })).toContainText('我的补充');
  await page.getByRole('button', { name: '成果更多操作' }).click();
  await page.getByRole('button', { name: '历史版本（1）' }).click();
  const history = page.getByRole('dialog', { name: '历史版本' });
  await history.getByRole('combobox', { name: '选择历史版本' }).selectOption('0');
  await expect(history).toContainText('尚缺独立数据集');
  await history.getByRole('button', { name: '恢复这个版本' }).click();
  await expect(history.getByRole('combobox', { name: '选择历史版本' })).toHaveValue('');
  await history.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(history).toHaveCount(0);
  await expect(page.getByRole('article', { name: '成果正文' })).not.toContainText('我的补充');
  expect(state.getTask().artifacts[0].versions.at(-1).text).toBe(revised);
  expect(state.unexpected).toEqual([]);
});
