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

export const createEmptyDeepResearchState = () => ({
  questionDraft: '',
  task: null,
  errorMessage: '',
  isCreating: false,
  isCancelling: false,
  pollError: '',
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

  return {
    taskId: normalizeText(task.taskId),
    traceId: normalizeText(task.traceId),
    status: normalizedStatus,
    stage: normalizedStage,
    progress: clampResearchProgress(task.progress),
    question: normalizeText(task.question),
    pdfId: normalizeText(task.pdfId),
    plan: normalizeTextList(task.plan, 5),
    findings: (Array.isArray(task.findings) ? task.findings : []).map((finding, index) => {
      const verdict = normalizeText(finding?.verdict).toUpperCase();
      return {
        id: normalizeText(finding?.id) || `finding-${index + 1}`,
        subQuestion: normalizeText(finding?.subQuestion) || `子问题 ${index + 1}`,
        summary: normalizeText(finding?.summary) || '暂无结论摘要。',
        verdict: VERDICT_META[verdict] ? verdict : 'INCORRECT',
        missingAspects: normalizeTextList(finding?.missingAspects, 6),
        sourceIds: normalizeTextList(finding?.sourceIds, 6),
      };
    }),
    report: typeof task.report === 'string' ? task.report : '',
    error: normalizeText(task.error),
    createdAt: normalizeText(task.createdAt),
    updatedAt: normalizeText(task.updatedAt),
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
    sourceIdCounts: (normalizedTask?.findings || []).map((finding) => finding.sourceIds.length),
    missingAspectCounts: (normalizedTask?.findings || []).map((finding) => finding.missingAspects.length),
    hasReport: Boolean(normalizedTask?.report),
    errorText: normalizeText(pollError) || normalizeText(errorMessage) || normalizedTask?.error || '',
  };
};
