import assert from 'node:assert/strict';

import {
  buildResearchContextHint,
  clampResearchProgress,
  createDeepResearchSnapshot,
  createEmptyDeepResearchState,
  getResearchStageMeta,
  getResearchStatusMeta,
  getResearchVerdictMeta,
  normalizeResearchBriefPreview,
  normalizeTraceCounters,
  normalizeTraceSummary,
  normalizeResearchTask,
  sanitizeResearchReport,
  shouldRestoreLatestResearchTask,
} from './deepResearchPanelModel.ts';


const run = async () => {
  const emptyState = createEmptyDeepResearchState();
  assert.deepEqual(emptyState, {
    questionDraft: '',
    task: null,
    errorMessage: '',
    isCreating: false,
    isCancelling: false,
    pollError: '',
    traceSummary: null,
    traceError: '',
    isTraceLoading: false,
    briefPreview: null,
    briefConstraintsDraft: '',
    isPreviewingBrief: false,
    briefError: '',
    allowExternalSearch: false,
  });

  assert.equal(clampResearchProgress(-1), 0);
  assert.equal(clampResearchProgress(0.45), 0.45);
  assert.equal(clampResearchProgress(3), 1);
  assert.equal(clampResearchProgress('bad'), 0);

  assert.equal(getResearchStatusMeta('running').label, '进行中');
  assert.equal(getResearchStageMeta('synthesizing').label, '综合');
  assert.equal(getResearchVerdictMeta('CORRECT').label, '证据充足');
  assert.equal(getResearchVerdictMeta('unknown').label, '证据不足');

  assert.equal(buildResearchContextHint({ research_problem: '验证 RAG 是否提升论文问答质量' }), '验证 RAG 是否提升论文问答质量');
  assert.equal(buildResearchContextHint({ core_hypothesis: '当前论文假设图检索可以减少幻觉' }), '当前论文假设图检索可以减少幻觉');
  assert.equal(buildResearchContextHint({}), '');

  const normalizedRunningTask = normalizeResearchTask({
    taskId: 'task-1',
    traceId: 'trace-1',
    status: 'running',
    stage: 'retrieving',
    progress: 1.8,
    question: '研究问题',
    pdfId: 'paper-1',
    plan: [
      '子问题一',
      '',
      {
        id: 'follow-up-1',
        question: '继续核查消融实验和关键指标。',
        kind: 'follow_up',
        status: 'done',
        sourceQuestion: '子问题一',
        sourceMissingAspects: ['消融实验', '', '关键指标'],
      },
    ],
    findings: [
      {
        subQuestion: '实验支撑是否充分？',
        summary: '当前论文已有部分结果，但 ablation 不完整。',
        verdict: 'AMBIGUOUS',
        missingAspects: ['ablation', '', 'baseline'],
        judgeScore: '82',
        coverage: {
          score: '0.67',
          matchedAspects: '2',
          totalAspects: '3',
          evidenceCount: '2',
          sourceTypes: ['current_paper', '', 'library'],
        },
        retryReason: '证据覆盖不足，仍缺少 baseline。',
        sourceIds: ['paper-1-chunk-2', '', 'lib-1-chunk-3'],
        sources: [
          {
            sourceId: 'paper-1-chunk-2',
            text: '当前论文实验片段。',
            sourceType: 'current_paper',
            pageIndex: 4,
            sectionId: 'section-5',
            chunkIndex: 2,
          },
        ],
      },
      {
        summary: '',
        verdict: 'unexpected',
      },
    ],
    conflicts: [
      {
        id: 'conflict-1',
        topic: 'accuracy',
        claim: 'accuracy 相关数值存在差异',
        conflictType: 'numeric_mismatch',
        severity: 'high',
        summary: '不同来源对 accuracy 给出 91.2% 与 87.5%。',
        sourceIds: ['paper-1-chunk-2', 'lib-1-chunk-3'],
        sources: [
          {
            sourceId: 'paper-1-chunk-2',
            text: 'Accuracy reaches 91.2%.',
            sourceType: 'current_paper',
            pageIndex: 4,
            sectionId: 'section-5',
            chunkIndex: 2,
          },
          {
            sourceId: 'lib-1-chunk-3',
            text: 'Accuracy is 87.5%.',
            sourceType: 'library',
          },
        ],
      },
    ],
    report: null,
    error: null,
    createdAt: '2026-06-01T10:00:00Z',
    updatedAt: '2026-06-01T10:02:00Z',
  });

  assert.equal(normalizedRunningTask.traceId, 'trace-1');
  assert.equal(normalizedRunningTask.progress, 1);
  assert.deepEqual(normalizedRunningTask.plan, ['子问题一', '继续核查消融实验和关键指标。']);
  assert.equal(normalizedRunningTask.planItems.length, 2);
  assert.deepEqual(normalizedRunningTask.planItems[0], {
    id: 'plan-1',
    question: '子问题一',
    kind: 'initial',
    status: '',
    sourceQuestion: '',
    sourceMissingAspects: [],
  });
  assert.deepEqual(normalizedRunningTask.planItems[1], {
    id: 'follow-up-1',
    question: '继续核查消融实验和关键指标。',
    kind: 'follow_up',
    status: 'done',
    sourceQuestion: '子问题一',
    sourceMissingAspects: ['消融实验', '关键指标'],
  });
  assert.equal(normalizedRunningTask.findings[0].verdict, 'AMBIGUOUS');
  assert.deepEqual(normalizedRunningTask.findings[0].missingAspects, ['ablation', 'baseline']);
  assert.equal(normalizedRunningTask.findings[0].judgeScore, 82);
  assert.equal(normalizedRunningTask.findings[0].coverage.score, 0.67);
  assert.equal(normalizedRunningTask.findings[0].coverage.matchedAspects, 2);
  assert.equal(normalizedRunningTask.findings[0].coverage.totalAspects, 3);
  assert.equal(normalizedRunningTask.findings[0].coverage.evidenceCount, 2);
  assert.deepEqual(normalizedRunningTask.findings[0].coverage.sourceTypes, ['current_paper', 'library']);
  assert.equal(normalizedRunningTask.findings[0].retryReason, '证据覆盖不足，仍缺少 baseline。');
  assert.deepEqual(normalizedRunningTask.findings[0].sourceIds, ['paper-1-chunk-2', 'lib-1-chunk-3']);
  assert.equal(normalizedRunningTask.findings[0].sources[0].pageIndex, 4);
  assert.equal(normalizedRunningTask.findings[0].sources[0].sectionId, 'section-5');
  assert.equal(normalizedRunningTask.findings[0].sources[0].locationLabel, 'p.5');
  assert.equal(normalizedRunningTask.findings[0].sources[0].canJumpToSource, true);
  assert.equal(normalizedRunningTask.findings[1].subQuestion, '子问题 2');
  assert.equal(normalizedRunningTask.findings[1].summary, '暂无结论摘要。');
  assert.equal(normalizedRunningTask.findings[1].verdict, 'INCORRECT');
  assert.equal(normalizedRunningTask.findings[1].judgeScore, null);
  assert.deepEqual(normalizedRunningTask.findings[1].coverage, {
    score: null,
    matchedAspects: null,
    totalAspects: null,
    evidenceCount: null,
    sourceTypes: [],
    sourceDiversityScore: null,
    sourceTrustWeightedScore: null,
    crossSourceAgreement: null,
  });
  assert.equal(normalizedRunningTask.findings[1].retryReason, '');
  assert.equal(normalizedRunningTask.conflicts.length, 1);
  assert.equal(normalizedRunningTask.conflicts[0].conflictType, 'numeric_mismatch');
  assert.equal(normalizedRunningTask.conflicts[0].severity, 'high');
  assert.deepEqual(normalizedRunningTask.conflicts[0].sourceIds, ['paper-1-chunk-2', 'lib-1-chunk-3']);
  assert.equal(normalizedRunningTask.conflicts[0].sources[0].locationLabel, 'p.5');
  assert.equal(normalizedRunningTask.conflicts[0].sources[0].canJumpToSource, true);
  assert.equal(normalizedRunningTask.report, '');
  assert.equal(normalizedRunningTask.createdAt, '2026-06-01T10:00:00Z');
  assert.equal(normalizedRunningTask.updatedAt, '2026-06-01T10:02:00Z');

  assert.deepEqual(normalizeResearchTask({ taskId: 'legacy-task' }).conflicts, []);

  const snapshot = createDeepResearchSnapshot({
    pdfFileName: 'paper.pdf',
    paperStructure: { research_problem: '判断这篇论文的实验结论边界' },
    questionDraft: '请对实验设计做深度研究',
    pollError: '任务状态已丢失',
    task: {
      taskId: 'task-2',
      status: 'cancelled',
      stage: 'done',
      progress: 0.76,
      findings: [
        {
          subQuestion: '子问题 A',
          summary: '结论',
          verdict: 'CORRECT',
          sourceIds: ['source-1', 'source-2'],
          missingAspects: [],
        },
        {
          subQuestion: '子问题 B',
          summary: '仍缺证据',
          verdict: 'INCORRECT',
          sourceIds: [],
          missingAspects: ['更完整指标'],
        },
      ],
      conflicts: [{ summary: '存在冲突' }],
      report: '## 报告',
      error: '',
    },
  });

  assert.equal(snapshot.fileLabel, 'paper.pdf');
  assert.equal(snapshot.paperHint, '判断这篇论文的实验结论边界');
  assert.equal(snapshot.questionDraft, '请对实验设计做深度研究');
  assert.equal(snapshot.statusLabel, '已取消');
  assert.equal(snapshot.stageLabel, '完成');
  assert.equal(snapshot.progressPercent, 76);
  assert.deepEqual(snapshot.verdictLabels, ['证据充足', '证据不足']);
  assert.deepEqual(snapshot.sourceIdCounts, [2, 0]);
  assert.deepEqual(snapshot.missingAspectCounts, [0, 1]);
  assert.equal(snapshot.conflictCount, 1);
  assert.equal(snapshot.planItemCount, 0);
  assert.equal(snapshot.hasReport, true);
  assert.equal(snapshot.errorText, '任务状态已丢失');

  assert.equal(shouldRestoreLatestResearchTask('paper-1', createEmptyDeepResearchState()), true);
  assert.equal(shouldRestoreLatestResearchTask('', createEmptyDeepResearchState()), false);
  assert.equal(shouldRestoreLatestResearchTask('paper-1', { task: { taskId: 'task-1' } }), false);
  assert.equal(shouldRestoreLatestResearchTask('paper-1', { task: null, isCreating: true }), false);

  const normalizedTrace = normalizeTraceSummary({
    traceId: 'trace-1',
    taskType: 'deep_research',
    status: 'success',
    startedAt: '2026-06-04T00:00:00Z',
    finishedAt: '2026-06-04T00:00:03Z',
    durationMs: 3000,
    requestMeta: { question: '研究问题' },
    responseMeta: { findingCount: 3 },
    counters: {
      llmCalls: 2,
      retrievalCalls: 4,
      retryCount: '1',
      truncationCount: 2.7,
      estimatedInputTokens: '123',
      estimatedOutputTokens: 'bad',
      externalSearchCalls: 3,
      externalSearchCacheHits: '2',
      externalSearchFailures: 1.5,
      externalEvidenceCount: 12,
      externalSearchLatencyMs: 245.9,
      externalSearchBudgetBlocks: '1',
      extraCounter: 99,
    },
    steps: Array.from({ length: 20 }, (_, index) => ({
      name: `step-${index + 1}`,
      status: index === 3 ? 'error' : 'success',
      durationMs: index * 10,
      inputSize: index,
      outputSize: index + 1,
      error: index === 3 ? '失败摘要' : '',
      meta: { subQuestion: `子问题 ${index + 1}` },
    })),
    error: '',
  });

  assert.equal(normalizedTrace.traceId, 'trace-1');
  assert.equal(normalizedTrace.taskType, 'deep_research');
  assert.equal(normalizedTrace.durationMs, 3000);
  assert.deepEqual(normalizedTrace.counters, {
    llmCalls: 2,
    retrievalCalls: 4,
    retryCount: 1,
    truncationCount: 2,
    estimatedInputTokens: 123,
    estimatedOutputTokens: 0,
    externalSearchCalls: 3,
    externalSearchCacheHits: 2,
    externalSearchFailures: 1,
    externalEvidenceCount: 12,
    externalSearchLatencyMs: 245,
    externalSearchBudgetBlocks: 1,
  });
  assert.deepEqual(normalizedTrace.rawCounters, {
    llmCalls: 2,
    retrievalCalls: 4,
    retryCount: '1',
    truncationCount: 2.7,
    estimatedInputTokens: '123',
    estimatedOutputTokens: 'bad',
    externalSearchCalls: 3,
    externalSearchCacheHits: '2',
    externalSearchFailures: 1.5,
    externalEvidenceCount: 12,
    externalSearchLatencyMs: 245.9,
    externalSearchBudgetBlocks: '1',
    extraCounter: 99,
  });
  assert.equal(normalizedTrace.steps.length, 12);
  assert.equal(normalizedTrace.steps[3].status, 'error');
  assert.equal(normalizedTrace.steps[3].error, '失败摘要');
  assert.equal(normalizedTrace.steps[3].meta.subQuestion, '子问题 4');

  const fallbackTrace = normalizeTraceSummary({ traceId: 123, steps: 'bad', counters: null });
  assert.equal(fallbackTrace.traceId, '');
  assert.deepEqual(fallbackTrace.steps, []);
  assert.deepEqual(fallbackTrace.counters, {
    llmCalls: 0,
    retrievalCalls: 0,
    retryCount: 0,
    truncationCount: 0,
    estimatedInputTokens: 0,
    estimatedOutputTokens: 0,
    externalSearchCalls: 0,
    externalSearchCacheHits: 0,
    externalSearchFailures: 0,
    externalEvidenceCount: 0,
    externalSearchLatencyMs: 0,
    externalSearchBudgetBlocks: 0,
  });
  assert.deepEqual(fallbackTrace.rawCounters, {});

  assert.deepEqual(normalizeTraceCounters({ llmCalls: -1, retrievalCalls: '3.9', retryCount: null }), {
    llmCalls: 0,
    retrievalCalls: 3,
    retryCount: 0,
    truncationCount: 0,
    estimatedInputTokens: 0,
    estimatedOutputTokens: 0,
    externalSearchCalls: 0,
    externalSearchCacheHits: 0,
    externalSearchFailures: 0,
    externalEvidenceCount: 0,
    externalSearchLatencyMs: 0,
    externalSearchBudgetBlocks: 0,
  });

  const normalizedPreview = normalizeResearchBriefPreview({
    question: '研究问题',
    pdfId: 'paper-1',
    brief: '聚焦实验设计。',
    assumptions: ['优先检查当前论文', '', '内部文献库只做补充'],
    clarifyingQuestions: ['关注实验？', '关注方法？', '关注局限？', '多余问题'],
    suggestedSubQuestions: ['实验设置是什么？', '指标是否充分？', '局限是什么？', '多余子问题'],
    needsClarification: true,
    source: 'llm',
  });
  assert.equal(normalizedPreview.brief, '聚焦实验设计。');
  assert.deepEqual(normalizedPreview.assumptions, ['优先检查当前论文', '内部文献库只做补充']);
  assert.deepEqual(normalizedPreview.clarifyingQuestions, ['关注实验？', '关注方法？', '关注局限？']);
  assert.deepEqual(normalizedPreview.suggestedSubQuestions, ['实验设置是什么？', '指标是否充分？', '局限是什么？']);
  assert.equal(normalizedPreview.needsClarification, true);
  assert.equal(normalizedPreview.source, 'llm');

  assert.equal(normalizeResearchBriefPreview(null), null);
  const fallbackPreview = normalizeResearchBriefPreview({ brief: '', clarifyingQuestions: 'bad' });
  assert.equal(fallbackPreview.brief, '');
  assert.deepEqual(fallbackPreview.clarifyingQuestions, []);
  assert.deepEqual(fallbackPreview.suggestedSubQuestions, []);

  // ── sanitizeResearchReport：默认视图剥离开发可观测细节 ──
  const rawReport = [
    '## 研究 brief',
    '围绕 SPaGS 方法检索后续研究。',
    '',
    '## 子问题结论',
    '### 1. SPaGS 论文提出了哪些未来工作？',
    '- 结论：现有证据基本充分。',
    '- 证据判断：CORRECT',
    '- 证据来源：cgf70171.pdf-chunk-57, cgf70171.pdf-chunk-56',
    '- JUDGE评分: 86/100 · 覆盖: 88% · 多样性: 0% · 可信度: 100%',
    '- 来源分布: current_paper(5)',
    '- 跨源一致性: 无法评估',
    '- 缺失点：缺少外部对比',
    '',
    '## 证据收集摘要',
    '- 总证据条数: 5',
    '- 平均来源多样性 (Shannon): 0.00',
    '',
    '## 来源追溯',
    '- [rag] 查询: "spags" 第1轮',
    '',
    '## 综合判断',
    '证据主要来自当前论文。',
    '',
    '## 执行统计',
    '| 指标 | 数值 |',
    '|------|------|',
    '| LLM 调用 | 4 |',
    '| 检索调用 | 5 |',
  ].join('\n');

  const cleanReport = sanitizeResearchReport(rawReport);
  // 开发段落整段剥离
  assert.equal(cleanReport.includes('## 执行统计'), false);
  assert.equal(cleanReport.includes('LLM 调用'), false);
  assert.equal(cleanReport.includes('## 证据收集摘要'), false);
  assert.equal(cleanReport.includes('Shannon'), false);
  assert.equal(cleanReport.includes('## 来源追溯'), false);
  assert.equal(cleanReport.includes('第1轮'), false);
  // 每条 finding 的开发 bullet 剥离
  assert.equal(cleanReport.includes('JUDGE评分'), false);
  assert.equal(cleanReport.includes('来源分布'), false);
  assert.equal(cleanReport.includes('跨源一致性'), false);
  // 用户关心的内容保留
  assert.equal(cleanReport.includes('## 研究 brief'), true);
  assert.equal(cleanReport.includes('## 子问题结论'), true);
  assert.equal(cleanReport.includes('- 结论：现有证据基本充分。'), true);
  assert.equal(cleanReport.includes('- 证据来源：cgf70171.pdf-chunk-57'), true);
  assert.equal(cleanReport.includes('- 缺失点：缺少外部对比'), true);
  // 开发段之后的保留段（综合判断）必须还在，证明跳过逻辑会正确复位
  assert.equal(cleanReport.includes('## 综合判断'), true);
  assert.equal(cleanReport.includes('证据主要来自当前论文。'), true);
  // 剥离后不残留三连空行
  assert.equal(/\n{3,}/.test(cleanReport), false);

  // 空值 / 非字符串安全
  assert.equal(sanitizeResearchReport(''), '');
  assert.equal(sanitizeResearchReport('   \n  '), '');
  assert.equal(sanitizeResearchReport(null), '');
  assert.equal(sanitizeResearchReport(undefined), '');
  assert.equal(sanitizeResearchReport(123), '');
  // 无开发噪声的报告原样保留（仅去首尾空白）
  assert.equal(sanitizeResearchReport('## 研究 brief\n只有结论。'), '## 研究 brief\n只有结论。');

  console.log('deep research panel model smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
