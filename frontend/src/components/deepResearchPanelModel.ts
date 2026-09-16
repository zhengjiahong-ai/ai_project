import { normalizeSourceLocation } from './evidenceCitationModel.ts';

export const TERMINAL_RESEARCH_STATUSES = ['succeeded', 'failed', 'cancelled'];

const STATUS_META: Record<string, { label: string; toneClass: string }> = {
  pending: {
    label: '待开始',
    toneClass: 'border-slate-400/25 bg-slate-500/10 text-slate-400',
  },
  running: {
    label: '进行中',
    toneClass: 'border-pixiu/25 bg-pixiu/10 text-pixiu',
  },
  awaiting_plan_review: { label: '等待计划确认', toneClass: 'border-amber-400/25 bg-amber-500/10 text-amber-500' },
  awaiting_final_review: { label: '等待终稿确认', toneClass: 'border-amber-400/25 bg-amber-500/10 text-amber-500' },
  succeeded: {
    label: '已完成',
    toneClass: 'border-emerald-400/25 bg-emerald-500/10 text-emerald-400',
  },
  failed: {
    label: '失败',
    toneClass: 'border-rose-400/25 bg-rose-500/10 text-rose-400',
  },
  cancelled: {
    label: '已取消',
    toneClass: 'border-amber-400/25 bg-amber-500/10 text-amber-500',
  },
};

const STAGE_META: Record<string, { label: string; description: string }> = {
  planning: {
    label: '规划',
    description: '正在拆分研究 brief 与子问题。',
  },
  retrieving: {
    label: '检索',
    description: '正在优先检索当前论文，并按需补充文献库线索。',
  },
  judging: {
    label: '判断',
    description: '正在评估证据覆盖情况并整理 findings。',
  },
  synthesizing: {
    label: '综合',
    description: '正在汇总 findings 并生成最终 Markdown 报告。',
  },
  done: {
    label: '完成',
    description: '任务已经结束，可查看 findings 与报告。',
  },
};

const VERDICT_META: Record<string, { label: string; toneClass: string }> = {
  CORRECT: {
    label: '证据充足',
    toneClass: 'border-emerald-400/25 bg-emerald-500/10 text-emerald-400',
  },
  AMBIGUOUS: {
    label: '部分相关',
    toneClass: 'border-amber-400/25 bg-amber-500/10 text-amber-500',
  },
  INCORRECT: {
    label: '证据不足',
    toneClass: 'border-rose-400/25 bg-rose-500/10 text-rose-400',
  },
};

const normalizeText = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

const normalizeTextList = (items: unknown = [], limit: number = 0): string[] => {
  const normalized = Array.isArray(items)
    ? items.map((item) => normalizeText(item)).filter(Boolean)
    : [];
  if (!limit || normalized.length <= limit) {
    return normalized;
  }
  return normalized.slice(0, limit);
};

const normalizeInteger = (value: unknown): number | null => {
  if (Number.isInteger(value)) {
    return value as number;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isInteger(parsed) ? parsed : null;
  }
  return null;
};

const normalizeNumber = (value: unknown, min = 0, max = 1): number | null => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return Math.min(max, Math.max(min, numeric));
};

const normalizeJudgeScore = (value: unknown): number | null => {
  const numeric = normalizeNumber(value, 0, 100);
  return numeric === null ? null : Math.round(numeric);
};

const normalizeCoverage = (coverage: unknown) => {
  if (!coverage || typeof coverage !== 'object') {
    return {
      score: null,
      matchedAspects: null,
      totalAspects: null,
      evidenceCount: null,
      sourceTypes: [],
      sourceDiversityScore: null,
      sourceTrustWeightedScore: null,
      crossSourceAgreement: null,
    };
  }
  const c = coverage as Record<string, unknown>;
  return {
    score: normalizeNumber(c.score, 0, 1),
    matchedAspects: normalizeInteger(c.matchedAspects),
    totalAspects: normalizeInteger(c.totalAspects),
    evidenceCount: normalizeInteger(c.evidenceCount),
    sourceTypes: normalizeTextList(c.sourceTypes, 6),
    sourceDiversityScore: normalizeNumber(c.sourceDiversityScore, 0, 1),
    sourceTrustWeightedScore: normalizeNumber(c.sourceTrustWeightedScore, 0, 1),
    crossSourceAgreement: normalizeNumber(c.crossSourceAgreement, 0, 1),
  };
};

const normalizeResearchConflicts = (conflicts: unknown): unknown[] => {
  if (!Array.isArray(conflicts)) {
    return [];
  }

  return conflicts
    .map((conflict, index) => {
      if (!conflict || typeof conflict !== 'object') {
        return null;
      }
      const sourceIds = normalizeTextList(conflict.sourceIds, 6);
      const conflictType = normalizeText(conflict.conflictType).toLowerCase();
      const severity = normalizeText(conflict.severity).toLowerCase();
      const summary = normalizeText(conflict.summary);
      const topic = normalizeText(conflict.topic);
      const claim = normalizeText(conflict.claim);
      if (!summary && !claim && sourceIds.length === 0) {
        return null;
      }
      return {
        id: normalizeText(conflict.id) || `conflict-${index + 1}`,
        topic,
        claim,
        conflictType: ['numeric_mismatch', 'opposing_conclusion'].includes(conflictType) ? conflictType : 'unknown',
        severity: ['high', 'medium', 'low'].includes(severity) ? severity : 'medium',
        summary: summary || '不同来源存在需要人工核查的矛盾线索。',
        sourceIds,
        sources: normalizeEvidenceSources(conflict.sources, sourceIds as string[]),
      };
    })
    .filter(Boolean)
    .slice(0, 5);
};

const normalizeResearchPlanItems = (plan: unknown) => {
  if (!Array.isArray(plan)) {
    return [];
  }

  return (plan as unknown[])
    .map((item, index) => {
      if (typeof item === 'string') {
        const question = normalizeText(item);
        if (!question) {
          return null;
        }
        return {
          id: `plan-${index + 1}`,
          question,
          kind: 'initial',
          status: '',
          sourceQuestion: '',
          sourceMissingAspects: [],
        };
      }

      if (!item || typeof item !== 'object') {
        return null;
      }
      const it = item as Record<string, unknown>;

      const question = normalizeText(it.question) || normalizeText(it.subQuestion) || normalizeText(it.text);
      if (!question) {
        return null;
      }
      const kind = normalizeText(it.kind).toLowerCase();
      const status = normalizeText(it.status).toLowerCase();
      return {
        id: normalizeText(it.id) || `plan-${index + 1}`,
        question,
        kind: kind === 'follow_up' ? 'follow_up' : 'initial',
        status: ['pending', 'running', 'done'].includes(status) ? status : '',
        sourceQuestion: normalizeText(it.sourceQuestion),
        sourceMissingAspects: normalizeTextList(it.sourceMissingAspects, 6),
      };
    })
    .filter(Boolean)
    .slice(0, 6);
};

const normalizeEvidenceSources = (sources: unknown, fallbackSourceIds: string[] = []) => {
  if (Array.isArray(sources) && sources.length > 0) {
    return sources
      .map((source, index) => {
        const sourceId = normalizeText(source?.sourceId) || normalizeText(source?.id) || fallbackSourceIds[index] || `source-${index + 1}`;
        const text = normalizeText(source?.text);
        if (!sourceId && !text) {
          return null;
        }
        return {
          sourceId,
          text,
          preview: text.length > 140 ? `${text.slice(0, 140).trimEnd()}...` : text,
          sourceType: normalizeText(source?.sourceType) || 'unknown',
          chunkIndex: normalizeInteger(source?.chunkIndex),
          ...normalizeSourceLocation(source),
        };
      })
      .filter(Boolean)
      .slice(0, 6);
  }

  return fallbackSourceIds.map((sourceId) => ({
    sourceId,
    text: '',
    preview: '',
    sourceType: 'unknown',
    chunkIndex: null,
    pageIndex: null,
    sectionId: null,
    pdfId: null,
    canJumpToSource: false,
    locationLabel: '',
  }));
};

export const createEmptyDeepResearchState = () => ({
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

export const clampResearchProgress = (value: unknown): number => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  if (numeric <= 0) {
    return 0;
  }
  if (numeric >= 1) {
    return 1;
  }
  return numeric;
};

export const getResearchStatusMeta = (status: unknown) => STATUS_META[normalizeText(status).toLowerCase()] || STATUS_META.pending;

export const getResearchStageMeta = (stage: unknown) => STAGE_META[normalizeText(stage).toLowerCase()] || STAGE_META.planning;

export const getResearchVerdictMeta = (verdict: unknown) => VERDICT_META[normalizeText(verdict).toUpperCase()] || VERDICT_META.INCORRECT;

export const buildResearchContextHint = (paperStructure: unknown): string => {
  if (!paperStructure || typeof paperStructure !== 'object') {
    return '';
  }
  const ps = paperStructure as Record<string, unknown>;

  const researchProblem = normalizeText(ps.research_problem);
  if (researchProblem) {
    return researchProblem;
  }

  return normalizeText(ps.core_hypothesis);
};

// 深度研究报告由后端 build_research_report 拼接，混入了大量开发可观测细节：
// 整段的「执行统计 / 证据收集摘要 / 来源追溯」，以及每条 finding 的 JUDGE 评分、
// 来源分布、跨源一致性 bullet。这些对读论文的用户是噪声。默认视图用本函数按后端
// 已知的二级标题与 bullet 前缀精确剥离它们，只保留用户真正关心的结论与证据；
// 开启「开发者详情」时面板改用未净化的原始全文。
const DEV_REPORT_SECTION_HEADERS = ['## 执行统计', '## 证据收集摘要', '## 来源追溯'];
const DEV_REPORT_BULLET_PREFIXES = ['- JUDGE评分', '- 来源分布', '- 跨源一致性'];

export const sanitizeResearchReport = (report: unknown): string => {
  const text = typeof report === 'string' ? report : '';
  if (!text.trim()) {
    return '';
  }
  const kept: string[] = [];
  let skippingDevSection = false;
  for (const rawLine of text.split(/\r?\n/)) {
    const trimmed = rawLine.trim();
    if (trimmed.startsWith('## ')) {
      // 任何二级标题都结束上一段跳过；若该标题本身是开发段则开始跳过整段
      skippingDevSection = DEV_REPORT_SECTION_HEADERS.some((header) => trimmed.startsWith(header));
      if (skippingDevSection) {
        continue;
      }
    }
    if (skippingDevSection) {
      continue;
    }
    if (DEV_REPORT_BULLET_PREFIXES.some((prefix) => trimmed.startsWith(prefix))) {
      continue;
    }
    kept.push(rawLine);
  }
  return kept.join('\n').replace(/\n{3,}/g, '\n\n').trim();
};

const normalizeExternalSearchConfig = (config: unknown) => {
  if (!config || typeof config !== 'object') {
    return {
      allowExternalSearch: false,
      provider: 'disabled',
      budget: { callLimit: 0, evidenceLimit: 0, callsUsed: 0, evidenceUsed: 0 },
      status: 'disabled',
      degradation: '',
    };
  }
  const cfg = config as Record<string, unknown>;
  const budget = cfg.budget && typeof cfg.budget === 'object' ? (cfg.budget as Record<string, unknown>) : {};
  return {
    allowExternalSearch: Boolean(cfg.allowExternalSearch),
    provider: normalizeText(cfg.provider) || 'disabled',
    budget: {
      callLimit: normalizeInteger(budget.callLimit) || 0,
      evidenceLimit: normalizeInteger(budget.evidenceLimit) || 0,
      callsUsed: normalizeInteger(budget.callsUsed) || 0,
      evidenceUsed: normalizeInteger(budget.evidenceUsed) || 0,
    },
    status: normalizeText(cfg.status) || 'disabled',
    degradation: normalizeText(cfg.degradation),
  };
};

export const normalizeResearchTask = (task: unknown) => {
  if (!task || typeof task !== 'object') {
    return null;
  }
  const t = task as Record<string, unknown>;

  const status = normalizeText(t.status).toLowerCase();
  const normalizedStatus = STATUS_META[status] ? status : 'pending';
  const normalizedStage = (() => {
    const stage = normalizeText(t.stage).toLowerCase();
    if (STAGE_META[stage]) {
      return stage;
    }
    return TERMINAL_RESEARCH_STATUSES.includes(normalizedStatus) ? 'done' : 'planning';
  })();
  const planItems = normalizeResearchPlanItems(t.plan);

  return {
    taskId: normalizeText(t.taskId),
    traceId: normalizeText(t.traceId),
    status: normalizedStatus,
    stage: normalizedStage,
    progress: clampResearchProgress(t.progress),
    question: normalizeText(t.question),
    pdfId: normalizeText(t.pdfId),
    plan: planItems.map((item) => (item as { question: string }).question),
    planItems,
    findings: (Array.isArray(t.findings) ? t.findings : []).map((finding: unknown, index: number) => {
      const f = finding as Record<string, unknown>;
      const verdict = normalizeText(f.verdict).toUpperCase();
      const sourceIds = normalizeTextList(f.sourceIds, 6);
      return {
        id: normalizeText(f.id) || `finding-${index + 1}`,
        subQuestion: normalizeText(f.subQuestion) || `子问题 ${index + 1}`,
        summary: normalizeText(f.summary) || '暂无结论摘要。',
        verdict: VERDICT_META[verdict] ? verdict : 'INCORRECT',
        missingAspects: normalizeTextList(f.missingAspects, 6),
        judgeScore: normalizeJudgeScore(f.judgeScore),
        coverage: normalizeCoverage(f.coverage),
        retryReason: normalizeText(f.retryReason),
        isFollowUp: Boolean(f.isFollowUp),
        followUpOf: normalizeText(f.followUpOf),
        sourceMissingAspects: normalizeTextList(f.sourceMissingAspects, 6),
        sourceIds,
        sources: normalizeEvidenceSources(f.sources, sourceIds as string[]),
      };
    }),
    conflicts: normalizeResearchConflicts(t.conflicts),
    reviewRisks: (Array.isArray(t.reviewRisks) ? t.reviewRisks : []).map((risk: unknown, index: number) => {
      const r = risk as Record<string, unknown>;
      return {
        riskId: normalizeText(r.riskId) || `risk-${index + 1}`,
        type: normalizeText(r.type), label: normalizeText(r.label) || '待核查项',
        detail: normalizeText(r.detail), sourceIds: normalizeTextList(r.sourceIds, 6),
        reviewStatus: normalizeText(r.reviewStatus) || 'pending',
      };
    }),
    humanReview: t.humanReview && typeof t.humanReview === 'object' ? t.humanReview : {},
    report: typeof t.report === 'string' ? t.report : '',
    error: normalizeText(t.error),
    createdAt: normalizeText(t.createdAt),
    updatedAt: normalizeText(t.updatedAt),
    externalSearchConfig: normalizeExternalSearchConfig(t.externalSearchConfig),
  };
};

export const normalizeResearchBriefPreview = (preview: unknown) => {
  if (!preview || typeof preview !== 'object') {
    return null;
  }
  const p = preview as Record<string, unknown>;

  return {
    question: normalizeText(p.question),
    pdfId: normalizeText(p.pdfId),
    brief: normalizeText(p.brief),
    assumptions: normalizeTextList(p.assumptions, 5),
    clarifyingQuestions: normalizeTextList(p.clarifyingQuestions, 3),
    suggestedSubQuestions: normalizeTextList(p.suggestedSubQuestions, 3),
    needsClarification: Boolean(p.needsClarification) && normalizeTextList(p.clarifyingQuestions, 3).length > 0,
    source: normalizeText(p.source) || 'fallback',
  };
};

const normalizePlainObject = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]: [string, unknown]) => normalizeText(key))
      .map(([key, item]: [string, unknown]) => [normalizeText(key), item]),
  );
};

const TRACE_COUNTER_KEYS = [
  'llmCalls',
  'retrievalCalls',
  'retryCount',
  'truncationCount',
  'estimatedInputTokens',
  'estimatedOutputTokens',
  'externalSearchCalls',
  'externalSearchCacheHits',
  'externalSearchFailures',
  'externalEvidenceCount',
  'externalSearchLatencyMs',
  'externalSearchBudgetBlocks',
];

const normalizeCounterValue = (value: unknown): number => {
  const numeric = Math.floor(Number(value));
  if (!Number.isFinite(numeric) || numeric < 0) {
    return 0;
  }
  return numeric;
};

export const normalizeTraceCounters = (counters: unknown) => {
  const rawCounters = normalizePlainObject(counters);
  return Object.fromEntries(TRACE_COUNTER_KEYS.map((key) => [key, normalizeCounterValue(rawCounters[key])]));
};

export const normalizeTraceSummary = (trace: unknown) => {
  if (!trace || typeof trace !== 'object') {
    return null;
  }
  const tr = trace as Record<string, unknown>;

  const rawSteps = Array.isArray(tr.steps) ? tr.steps : [];
  const rawCounters = normalizePlainObject(tr.counters);
  return {
    traceId: normalizeText(tr.traceId),
    taskType: normalizeText(tr.taskType) || 'unknown',
    status: normalizeText(tr.status) || 'unknown',
    startedAt: normalizeText(tr.startedAt),
    finishedAt: normalizeText(tr.finishedAt),
    durationMs: Number.isFinite(Number(tr.durationMs)) ? Math.max(0, Number(tr.durationMs)) : null,
    requestMeta: normalizePlainObject(tr.requestMeta),
    responseMeta: normalizePlainObject(tr.responseMeta),
    counters: normalizeTraceCounters(tr.counters),
    rawCounters,
    steps: (rawSteps as unknown[]).slice(0, 12).map((step: unknown, index: number) => {
      const st = step as Record<string, unknown>;
      return {
        name: normalizeText(st.name) || `step-${index + 1}`,
        status: normalizeText(st.status) || 'unknown',
        durationMs: Number.isFinite(Number(st.durationMs)) ? Math.max(0, Number(st.durationMs)) : 0,
        inputSize: Number.isFinite(Number(st.inputSize)) ? Math.max(0, Number(st.inputSize)) : null,
        outputSize: Number.isFinite(Number(st.outputSize)) ? Math.max(0, Number(st.outputSize)) : null,
        error: normalizeText(st.error),
        meta: normalizePlainObject(st.meta),
      };
    }),
    error: normalizeText(tr.error),
  };
};

export const shouldRestoreLatestResearchTask = (pdfId: unknown, state: unknown): boolean => {
  if (!normalizeText(pdfId)) {
    return false;
  }
  const currentState = (state || createEmptyDeepResearchState()) as Record<string, unknown>;
  return !(currentState.task as Record<string, unknown>)?.taskId && !currentState.isCreating && !currentState.isCancelling;
};

export const createDeepResearchSnapshot = ({
  task = null,
  questionDraft = '',
  pdfFileName = '',
  paperStructure = null,
  errorMessage = '',
  pollError = '',
} = {}) => {
  const normalizedTask = normalizeResearchTask(task);
  return {
    fileLabel: normalizeText(pdfFileName) || '当前论文',
    paperHint: buildResearchContextHint(paperStructure),
    questionDraft: typeof questionDraft === 'string' ? questionDraft : '',
    hasTask: Boolean(normalizedTask?.taskId),
    statusLabel: getResearchStatusMeta(normalizedTask?.status).label,
    stageLabel: getResearchStageMeta(normalizedTask?.stage).label,
    progressPercent: Math.round((normalizedTask?.progress || 0) * 100),
    verdictLabels: (normalizedTask?.findings || []).map((finding) => getResearchVerdictMeta(finding.verdict).label),
    planItemCount: normalizedTask?.planItems?.length || 0,
    sourceIdCounts: (normalizedTask?.findings || []).map((finding) => finding.sourceIds.length),
    missingAspectCounts: (normalizedTask?.findings || []).map((finding) => finding.missingAspects.length),
    conflictCount: normalizedTask?.conflicts?.length || 0,
    hasReport: Boolean(normalizedTask?.report),
    errorText: normalizeText(pollError) || normalizeText(errorMessage) || normalizedTask?.error || '',
  };
};
