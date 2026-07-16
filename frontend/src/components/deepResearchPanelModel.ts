import { normalizeSourceLocation } from './evidenceCitationModel.ts';

export const TERMINAL_RESEARCH_STATUSES = ['succeeded', 'failed', 'cancelled'];

const STATUS_META = {
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

const STAGE_META = {
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

const VERDICT_META = {
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

const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '');

const normalizeTextList = (items = [], limit = 0) => {
  const normalized = Array.isArray(items)
    ? items.map((item) => normalizeText(item)).filter(Boolean)
    : [];
  if (!limit || normalized.length <= limit) {
    return normalized;
  }
  return normalized.slice(0, limit);
};

const normalizeInteger = (value) => {
  if (Number.isInteger(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isInteger(parsed) ? parsed : null;
  }
  return null;
};

const normalizeNumber = (value, min = 0, max = 1) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return Math.min(max, Math.max(min, numeric));
};

const normalizeJudgeScore = (value) => {
  const numeric = normalizeNumber(value, 0, 100);
  return numeric === null ? null : Math.round(numeric);
};

const normalizeCoverage = (coverage) => {
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
  return {
    score: normalizeNumber(coverage.score, 0, 1),
    matchedAspects: normalizeInteger(coverage.matchedAspects),
    totalAspects: normalizeInteger(coverage.totalAspects),
    evidenceCount: normalizeInteger(coverage.evidenceCount),
    sourceTypes: normalizeTextList(coverage.sourceTypes, 6),
    sourceDiversityScore: normalizeNumber(coverage.sourceDiversityScore, 0, 1),
    sourceTrustWeightedScore: normalizeNumber(coverage.sourceTrustWeightedScore, 0, 1),
    crossSourceAgreement: normalizeNumber(coverage.crossSourceAgreement, 0, 1),
  };
};

const normalizeResearchConflicts = (conflicts) => {
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
        sources: normalizeEvidenceSources(conflict.sources, sourceIds),
      };
    })
    .filter(Boolean)
    .slice(0, 5);
};

const normalizeResearchPlanItems = (plan) => {
  if (!Array.isArray(plan)) {
    return [];
  }

  return plan
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

      const question = normalizeText(item.question) || normalizeText(item.subQuestion) || normalizeText(item.text);
      if (!question) {
        return null;
      }
      const kind = normalizeText(item.kind).toLowerCase();
      const status = normalizeText(item.status).toLowerCase();
      return {
        id: normalizeText(item.id) || `plan-${index + 1}`,
        question,
        kind: kind === 'follow_up' ? 'follow_up' : 'initial',
        status: ['pending', 'running', 'done'].includes(status) ? status : '',
        sourceQuestion: normalizeText(item.sourceQuestion),
        sourceMissingAspects: normalizeTextList(item.sourceMissingAspects, 6),
      };
    })
    .filter(Boolean)
    .slice(0, 6);
};

const normalizeEvidenceSources = (sources, fallbackSourceIds = []) => {
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

export const clampResearchProgress = (value) => {
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

export const getResearchStatusMeta = (status) => STATUS_META[normalizeText(status).toLowerCase()] || STATUS_META.pending;

export const getResearchStageMeta = (stage) => STAGE_META[normalizeText(stage).toLowerCase()] || STAGE_META.planning;

export const getResearchVerdictMeta = (verdict) => VERDICT_META[normalizeText(verdict).toUpperCase()] || VERDICT_META.INCORRECT;

export const buildResearchContextHint = (paperStructure) => {
  if (!paperStructure || typeof paperStructure !== 'object') {
    return '';
  }

  const researchProblem = normalizeText(paperStructure.research_problem);
  if (researchProblem) {
    return researchProblem;
  }

  return normalizeText(paperStructure.core_hypothesis);
};

const normalizeExternalSearchConfig = (config) => {
  if (!config || typeof config !== 'object') {
    return {
      allowExternalSearch: false,
      provider: 'disabled',
      budget: { callLimit: 0, evidenceLimit: 0, callsUsed: 0, evidenceUsed: 0 },
      status: 'disabled',
      degradation: '',
    };
  }
  const budget = config.budget && typeof config.budget === 'object' ? config.budget : {};
  return {
    allowExternalSearch: Boolean(config.allowExternalSearch),
    provider: normalizeText(config.provider) || 'disabled',
    budget: {
      callLimit: normalizeInteger(budget.callLimit) || 0,
      evidenceLimit: normalizeInteger(budget.evidenceLimit) || 0,
      callsUsed: normalizeInteger(budget.callsUsed) || 0,
      evidenceUsed: normalizeInteger(budget.evidenceUsed) || 0,
    },
    status: normalizeText(config.status) || 'disabled',
    degradation: normalizeText(config.degradation),
  };
};

export const normalizeResearchTask = (task) => {
  if (!task || typeof task !== 'object') {
    return null;
  }

  const status = normalizeText(task.status).toLowerCase();
  const normalizedStatus = STATUS_META[status] ? status : 'pending';
  const normalizedStage = (() => {
    const stage = normalizeText(task.stage).toLowerCase();
    if (STAGE_META[stage]) {
      return stage;
    }
    return TERMINAL_RESEARCH_STATUSES.includes(normalizedStatus) ? 'done' : 'planning';
  })();
  const planItems = normalizeResearchPlanItems(task.plan);

  return {
    taskId: normalizeText(task.taskId),
    traceId: normalizeText(task.traceId),
    status: normalizedStatus,
    stage: normalizedStage,
    progress: clampResearchProgress(task.progress),
    question: normalizeText(task.question),
    pdfId: normalizeText(task.pdfId),
    plan: planItems.map((item) => item.question),
    planItems,
    findings: (Array.isArray(task.findings) ? task.findings : []).map((finding, index) => {
      const verdict = normalizeText(finding?.verdict).toUpperCase();
      const sourceIds = normalizeTextList(finding?.sourceIds, 6);
      return {
        id: normalizeText(finding?.id) || `finding-${index + 1}`,
        subQuestion: normalizeText(finding?.subQuestion) || `子问题 ${index + 1}`,
        summary: normalizeText(finding?.summary) || '暂无结论摘要。',
        verdict: VERDICT_META[verdict] ? verdict : 'INCORRECT',
        missingAspects: normalizeTextList(finding?.missingAspects, 6),
        judgeScore: normalizeJudgeScore(finding?.judgeScore),
        coverage: normalizeCoverage(finding?.coverage),
        retryReason: normalizeText(finding?.retryReason),
        isFollowUp: Boolean(finding?.isFollowUp),
        followUpOf: normalizeText(finding?.followUpOf),
        sourceMissingAspects: normalizeTextList(finding?.sourceMissingAspects, 6),
        sourceIds,
        sources: normalizeEvidenceSources(finding?.sources, sourceIds),
      };
    }),
    conflicts: normalizeResearchConflicts(task.conflicts),
    reviewRisks: (Array.isArray(task.reviewRisks) ? task.reviewRisks : []).map((risk, index) => ({
      riskId: normalizeText(risk?.riskId) || `risk-${index + 1}`,
      type: normalizeText(risk?.type), label: normalizeText(risk?.label) || '待核查项',
      detail: normalizeText(risk?.detail), sourceIds: normalizeTextList(risk?.sourceIds, 6),
      reviewStatus: normalizeText(risk?.reviewStatus) || 'pending',
    })),
    humanReview: task.humanReview && typeof task.humanReview === 'object' ? task.humanReview : {},
    report: typeof task.report === 'string' ? task.report : '',
    error: normalizeText(task.error),
    createdAt: normalizeText(task.createdAt),
    updatedAt: normalizeText(task.updatedAt),
    externalSearchConfig: normalizeExternalSearchConfig(task.externalSearchConfig),
  };
};

export const normalizeResearchBriefPreview = (preview) => {
  if (!preview || typeof preview !== 'object') {
    return null;
  }

  return {
    question: normalizeText(preview.question),
    pdfId: normalizeText(preview.pdfId),
    brief: normalizeText(preview.brief),
    assumptions: normalizeTextList(preview.assumptions, 5),
    clarifyingQuestions: normalizeTextList(preview.clarifyingQuestions, 3),
    suggestedSubQuestions: normalizeTextList(preview.suggestedSubQuestions, 3),
    needsClarification: Boolean(preview.needsClarification) && normalizeTextList(preview.clarifyingQuestions, 3).length > 0,
    source: normalizeText(preview.source) || 'fallback',
  };
};

const normalizePlainObject = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => normalizeText(key))
      .map(([key, item]) => [normalizeText(key), item]),
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

const normalizeCounterValue = (value) => {
  const numeric = Math.floor(Number(value));
  if (!Number.isFinite(numeric) || numeric < 0) {
    return 0;
  }
  return numeric;
};

export const normalizeTraceCounters = (counters) => {
  const rawCounters = normalizePlainObject(counters);
  return Object.fromEntries(TRACE_COUNTER_KEYS.map((key) => [key, normalizeCounterValue(rawCounters[key])]));
};

export const normalizeTraceSummary = (trace) => {
  if (!trace || typeof trace !== 'object') {
    return null;
  }

  const rawSteps = Array.isArray(trace.steps) ? trace.steps : [];
  const rawCounters = normalizePlainObject(trace.counters);
  return {
    traceId: normalizeText(trace.traceId),
    taskType: normalizeText(trace.taskType) || 'unknown',
    status: normalizeText(trace.status) || 'unknown',
    startedAt: normalizeText(trace.startedAt),
    finishedAt: normalizeText(trace.finishedAt),
    durationMs: Number.isFinite(Number(trace.durationMs)) ? Math.max(0, Number(trace.durationMs)) : null,
    requestMeta: normalizePlainObject(trace.requestMeta),
    responseMeta: normalizePlainObject(trace.responseMeta),
    counters: normalizeTraceCounters(trace.counters),
    rawCounters,
    steps: rawSteps.slice(0, 12).map((step, index) => ({
      name: normalizeText(step?.name) || `step-${index + 1}`,
      status: normalizeText(step?.status) || 'unknown',
      durationMs: Number.isFinite(Number(step?.durationMs)) ? Math.max(0, Number(step.durationMs)) : 0,
      inputSize: Number.isFinite(Number(step?.inputSize)) ? Math.max(0, Number(step.inputSize)) : null,
      outputSize: Number.isFinite(Number(step?.outputSize)) ? Math.max(0, Number(step.outputSize)) : null,
      error: normalizeText(step?.error),
      meta: normalizePlainObject(step?.meta),
    })),
    error: normalizeText(trace.error),
  };
};

export const shouldRestoreLatestResearchTask = (pdfId, state) => {
  if (!normalizeText(pdfId)) {
    return false;
  }
  const currentState = state || createEmptyDeepResearchState();
  return !currentState.task?.taskId && !currentState.isCreating && !currentState.isCancelling;
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
