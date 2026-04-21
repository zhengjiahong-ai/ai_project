import assert from 'node:assert/strict';
import {
  buildMetricCards,
  buildSummary,
  getDetailSections,
  getEvidencePreview,
  getEvidenceBasedContributions,
  getStructuredSections,
} from './criticalAnalysisData.js';

const legacyPayload = {
  claimed_contributions: '作者声称提出了一个新的检索排序方法。',
  inferred_real_contributions: '现有结果显示该方法在若干基准上确有改进。',
  critical_analysis: '实验规模有限，但主线论证仍较清楚。',
};

const structuredPayload = {
  ...legacyPayload,
  evidence_based_contributions: '根据全文证据，论文真正站得住脚的是更稳定的重排策略与实验增益。',
  weaknesses: ['消融实验覆盖不够完整', '低资源场景分析不足'],
  overclaim_risks: ['对泛化能力的表述略强'],
  missing_evidence: ['跨领域验证不足'],
  rag_sources: [
    { sourceId: 'chunk-1', sourceType: 'current_paper', text: '当前论文片段 1', chunkIndex: 0 },
    { sourceId: 'chunk-2', sourceType: 'library', text: '文献库片段 2', chunkIndex: 3 },
    { sourceId: 'chunk-3', sourceType: 'current_paper', text: '  ' },
  ],
};

const run = async () => {
  const legacySummary = buildSummary(legacyPayload);
  assert.match(legacySummary, /推断出的真实贡献/);
  assert.equal(getEvidenceBasedContributions(legacyPayload), legacyPayload.inferred_real_contributions);

  const structuredSummary = buildSummary(structuredPayload);
  assert.match(structuredSummary, /基于证据的真实贡献/);
  assert.equal(getEvidenceBasedContributions(structuredPayload), structuredPayload.evidence_based_contributions);

  const detailSections = getDetailSections(structuredPayload);
  assert.equal(detailSections[1].title, '基于证据的真实贡献');
  assert.equal(detailSections[1].content, structuredPayload.evidence_based_contributions);

  const metrics = buildMetricCards(structuredPayload);
  assert.equal(metrics[1].detail, structuredPayload.evidence_based_contributions);
  assert.equal(metrics.length, 3);

  const structuredSections = getStructuredSections(structuredPayload);
  assert.deepEqual(
    structuredSections.map((section) => section.key),
    ['weaknesses', 'overclaim_risks', 'missing_evidence'],
  );

  const evidencePreview = getEvidencePreview(structuredPayload);
  assert.equal(evidencePreview.length, 2);
  assert.equal(evidencePreview[0].sourceLabel, '当前论文');
  assert.equal(evidencePreview[1].sourceLabel, '文献库');
  assert.equal(evidencePreview[0].chunkIndex, 0);

  console.log('critical analysis data helper smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
