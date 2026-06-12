import assert from 'node:assert/strict';
import {
  buildMetricCards,
  buildSummary,
  getDetailSections,
  getEvidencePreview,
  getEvidenceBasedContributions,
  getClaimSupportRows,
  getNoveltyDimensionRows,
  getSentenceSourceReferences,
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
    { sourceId: 'chunk-1', sourceType: 'current_paper', text: '当前论文片段 1', chunkIndex: 0, pageIndex: 2, sectionId: 'section-1' },
    { sourceId: 'chunk-2', sourceType: 'library', text: '文献库片段 2', chunkIndex: 3 },
    { sourceId: 'chunk-3', sourceType: 'current_paper', text: '  ' },
  ],
  sentenceSourceMap: [
    {
      id: 'ref-1',
      target: 'critical_analysis',
      sentence: '实验规模有限，但主线论证仍较清楚。',
      sourceIds: ['chunk-1', 'missing'],
    },
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
  assert.equal(metrics[0].name, '作者主张');

  const assessedPayload = {
    ...structuredPayload,
    contributionScore: {
      score: 84.8,
      label: '可信度较高',
      summary: '2/2 条主张获得直接证据支撑。',
      factors: ['主张支撑率 100%', '方法章节覆盖充分'],
    },
    riskScore: {
      score: 18.2,
      label: '低风险',
      summary: '未发现明显伪贡献风险。',
      factors: ['缺失证据 0 条', '夸大风险 0 条'],
    },
    noveltyDimensions: [
      { id: 'claim_support', label: '主张支撑', score: 100, status: 'strong', detail: '主张证据充分。' },
      { id: 'method_grounding', label: '方法落地', score: 85, status: 'strong', detail: '方法证据充分。' },
      { id: 'empty', label: ' ', score: 999, status: 'unknown', detail: '' },
    ],
  };
  const assessedMetrics = buildMetricCards(assessedPayload);
  assert.equal(assessedMetrics[0].name, '核心贡献可信度');
  assert.equal(assessedMetrics[0].score, 85);
  assert.match(assessedMetrics[0].detail, /2\/2 条主张/);
  assert.match(assessedMetrics[0].basis[0], /主张支撑率/);
  assert.equal(assessedMetrics[1].name, '伪贡献/夸大风险');
  assert.equal(assessedMetrics[1].score, 18);

  const noveltyRows = getNoveltyDimensionRows(assessedPayload);
  assert.equal(noveltyRows.length, 2);
  assert.equal(noveltyRows[0].score, 100);
  assert.equal(noveltyRows[0].statusLabel, '强');

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
  assert.equal(evidencePreview[0].pageIndex, 2);
  assert.equal(evidencePreview[0].sectionId, 'section-1');
  assert.equal(evidencePreview[0].locationLabel, 'p.3');
  assert.equal(evidencePreview[0].canJumpToSource, true);
  assert.equal(evidencePreview[1].canJumpToSource, false);

  const references = getSentenceSourceReferences(structuredPayload);
  assert.equal(references.length, 1);
  assert.equal(references[0].sourceIds[0], 'chunk-1');
  assert.equal(references[0].sources[0].preview, '当前论文片段 1');
  assert.equal(references[0].sources[0].pageIndex, 2);

  assert.deepEqual(getClaimSupportRows(legacyPayload), []);

  const claimRows = getClaimSupportRows({
    ...structuredPayload,
    claims: [
      {
        id: 'claim-1',
        claim: '作者提出新的检索排序方法。',
        supportLevel: 'SUPPORTED',
        evidenceSourceIds: ['chunk-1', 'missing'],
        missingEvidence: [],
        reason: '实验结果提供了直接支撑。',
      },
      {
        id: 'claim-2',
        claim: '作者提出通用框架。',
        supportLevel: 'UNKNOWN',
        evidenceSourceIds: [],
        missingEvidence: ['缺少跨领域实验'],
        reason: '证据不足。',
      },
    ],
  });
  assert.equal(claimRows.length, 2);
  assert.equal(claimRows[0].supportLevel, 'SUPPORTED');
  assert.equal(claimRows[0].supportLabel, '已支撑');
  assert.equal(claimRows[0].sources.length, 1);
  assert.equal(claimRows[0].sources[0].locationLabel, 'p.3');
  assert.equal(claimRows[1].supportLevel, 'PARTIAL');
  assert.equal(claimRows[1].missingEvidence[0], '缺少跨领域实验');

  console.log('critical analysis data helper smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
