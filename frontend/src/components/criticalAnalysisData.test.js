import assert from 'node:assert/strict';
import {
  buildEvidenceGraphLegend,
  buildMetricCards,
  buildSummary,
  getCitationGraph,
  getDetailSections,
  getEvidenceGraph,
  getEvidencePreview,
  getEvidenceBasedContributions,
  getClaimSupportRows,
  getNoveltyDimensionRows,
  getSentenceSourceReferences,
  getStructuredSections,
} from './criticalAnalysisData.ts';

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

  assert.equal(getCitationGraph(legacyPayload), null);
  assert.equal(getCitationGraph({ citationGraph: null }), null);
  assert.equal(getCitationGraph({ citationGraph: { nodes: [], links: [] } }), null);

  const citationGraph = getCitationGraph({
    citationGraph: {
      nodes: [
        { id: 'current', name: '当前论文', val: 12 },
        { id: 'ref-1', label: '真实参考文献', color: '#64748b' },
        { id: '', name: '无效节点' },
      ],
      links: [
        { source: 'current', target: 'ref-1', relation: 'cites' },
        { source: 'current', target: '', relation: 'broken' },
      ],
    },
  });
  assert.equal(citationGraph.nodes.length, 2);
  assert.equal(citationGraph.nodes[0].name, '当前论文');
  assert.equal(citationGraph.nodes[1].name, '真实参考文献');
  assert.equal(citationGraph.links.length, 1);
  assert.equal(citationGraph.links[0].source, 'current');
  assert.equal(citationGraph.links[0].target, 'ref-1');

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
        numericVerificationStatus: 'insufficient_for_auto_verification',
        numericEvidenceCandidates: [
          {
            sourceId: 'chunk-1',
            text: 'Table 2: F1 improves by 20%.',
            label: 'Table 2',
            metrics: ['f1'],
            numbers: ['20%'],
            status: 'candidate_found',
            reason: '匹配到表格和百分比。',
          },
        ],
      },
      {
        id: 'claim-2',
        claim: '作者提出通用框架。',
        supportLevel: 'UNKNOWN',
        evidenceSourceIds: [],
        missingEvidence: ['缺少跨领域实验'],
        reason: '证据不足。',
        numericVerificationStatus: 'not_applicable',
      },
    ],
  });
  assert.equal(claimRows.length, 2);
  assert.equal(claimRows[0].supportLevel, 'SUPPORTED');
  assert.equal(claimRows[0].supportLabel, '已支撑');
  assert.equal(claimRows[0].sources.length, 1);
  assert.equal(claimRows[0].sources[0].locationLabel, 'p.3');
  assert.equal(claimRows[0].numericVerificationStatusLabel, '候选证据不足以自动验证');
  assert.equal(claimRows[0].numericEvidenceCandidates.length, 1);
  assert.equal(claimRows[0].numericEvidenceCandidates[0].sourceId, 'chunk-1');
  assert.equal(claimRows[0].numericEvidenceCandidates[0].locationLabel, 'p.3');
  assert.equal(claimRows[0].numericEvidenceCandidates[0].canJumpToSource, true);
  assert.deepEqual(claimRows[0].numericEvidenceCandidates[0].metrics, ['f1']);
  assert.deepEqual(claimRows[0].numericEvidenceCandidates[0].numbers, ['20%']);
  assert.equal(claimRows[1].supportLevel, 'PARTIAL');
  assert.equal(claimRows[1].missingEvidence[0], '缺少跨领域实验');
  assert.equal(claimRows[1].numericVerificationStatusLabel, '不涉及数值核对');
  assert.deepEqual(claimRows[1].numericEvidenceCandidates, []);

  // 证据关系图：优先 evidenceGraph（后端离线构造的主张—证据图），回退 citationGraph。
  // claim-2 刻意不带出边：孤立主张节点就是“找不到落点”的视觉信号。
  const evidenceGraphPayload = {
    citationGraph: null,
    evidenceGraph: {
      nodes: [
        { id: 'claim-1', name: '作者提出新的检索排序方法。', group: 'claim', supportLevel: 'SUPPORTED' },
        { id: 'claim-2', name: '作者宣称通用框架。', group: 'claim', supportLevel: 'UNSUPPORTED' },
        { id: 'chunk-1', name: '第 3 页', group: 'evidence' },
      ],
      links: [{ source: 'claim-1', target: 'chunk-1', relation: 'supported_by' }],
    },
  };
  const evidenceGraph = getEvidenceGraph(evidenceGraphPayload);
  assert.equal(evidenceGraph.nodes.length, 3);
  assert.equal(evidenceGraph.nodes[0].supportLevel, 'SUPPORTED');
  assert.equal(evidenceGraph.links.length, 1);
  assert.equal(evidenceGraph.links[0].relation, 'supported_by');
  // citationGraph 仍为 null（未配 Semantic Scholar key），但卡片不再永远空态。
  assert.equal(getCitationGraph(evidenceGraphPayload), null);
  // 无 evidenceGraph 时回退到真实引用网络，保留将来接回 traverse_citation_graph 的路径。
  assert.equal(getEvidenceGraph({ citationGraph }).nodes.length, 2);

  // 图例只给图里真存在的等级（PARTIAL 缺席则不列）；无主张节点时不给图例。
  assert.deepEqual(buildEvidenceGraphLegend(evidenceGraph), [
    { level: 'SUPPORTED', label: '有原文支撑', color: '#22c55e', count: 1 },
    { level: 'UNSUPPORTED', label: '未找到落点', color: '#94a3b8', count: 1 },
  ]);
  assert.deepEqual(buildEvidenceGraphLegend(null), []);
  assert.deepEqual(buildEvidenceGraphLegend({ nodes: [{ id: 'chunk-1', group: 'evidence' }] }), []);

  console.log('critical analysis data helper smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
