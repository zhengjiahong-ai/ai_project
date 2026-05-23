import assert from 'node:assert/strict';

import {
  buildInsightCardModel,
  extractKeyPoints,
  extractSummarySentence,
  stripMarkdown,
} from './insightCardModel.js';

const run = async () => {
  assert.equal(stripMarkdown('**RAG** improves [QA](https://example.com).'), 'RAG improves QA.');

  assert.equal(
    extractSummarySentence('第一段总结。\n\n- 要点一\n- 要点二'),
    '第一段总结。',
  );

  assert.deepEqual(
    extractKeyPoints('第一段总结。\n\n- 要点一\n- 要点二\n- 要点三', 2),
    ['要点一', '要点二'],
  );

  const model = buildInsightCardModel({
    content: '研究结论。\n\n1. 证据链完整\n2. 仍缺消融实验',
    detailsTitle: '展开完整分析',
  });

  assert.equal(model.summary, '研究结论。');
  assert.deepEqual(model.points, ['证据链完整', '仍缺消融实验']);
  assert.equal(model.detailsTitle, '展开完整分析');
  assert.equal(model.hasDetails, true);

  const modelWithExplicitSummary = buildInsightCardModel({
    content: '',
    summary: '手动摘要',
    keyPoints: ['  第一条  ', '', '第二条'],
  });

  assert.equal(modelWithExplicitSummary.summary, '手动摘要');
  assert.deepEqual(modelWithExplicitSummary.points, ['第一条', '第二条']);
  assert.equal(modelWithExplicitSummary.hasDetails, false);

  console.log('insight card model smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
