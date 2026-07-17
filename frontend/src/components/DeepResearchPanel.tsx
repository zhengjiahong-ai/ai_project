import React, { useMemo, useState } from 'react';
import { AlertCircle, ChevronDown, ChevronUp, FileSearch, Link2, Loader2, RefreshCw, Search, Square, ArrowRight } from 'lucide-react';

import InsightCard from './InsightCard';
import MarkdownContent from './MarkdownContent';
import SourceList from './SourceCitation.jsx';
import {
  TERMINAL_RESEARCH_STATUSES,
  buildResearchContextHint,
  getResearchStageMeta,
  getResearchStatusMeta,
  getResearchVerdictMeta,
  normalizeResearchTask,
} from './deepResearchPanelModel.ts';

// ── Types ──────────────────────────────────────────────────────────────────

interface PlanItem {
  question: string;
  status?: string;
  kind?: string;
  sourceQuestion?: string;
  sourceMissingAspects?: string[];
}

interface ResearchTask {
  taskId: string;
  traceId: string;
  status: string;
  stage: string;
  progress: number;
  question?: string;
  planItems: PlanItem[];
  findings: Finding[];
  conflicts: Conflict[];
  report?: string;
  error?: string;
  reviewRisks: Risk[];
  externalSearchConfig?: ExternalSearchConfig;
}

interface ExternalSearchConfig {
  allowExternalSearch: boolean;
  provider: string;
  status: string;
  degradation?: string;
  budget: {
    callsUsed: number;
    callLimit: number;
    evidenceUsed: number;
    evidenceLimit: number;
  };
}

interface Finding {
  id: string;
  subQuestion: string;
  summary: string;
  verdict: string;
  judgeScore: number | null;
  sources: ResearchSource[];
  missingAspects: string[];
  retryReason?: string;
  coverage?: FindingCoverage;
}

interface ResearchSource {
  sourceId: string;
  locationLabel?: string;
  preview?: string;
  canJumpToSource?: boolean;
}

interface FindingCoverage {
  score: number | null;
  evidenceCount: number | null;
  sourceDiversityScore: number | null;
  sourceTrustWeightedScore: number | null;
  crossSourceAgreement: number | null;
  sourceTypes?: string[];
}

interface Conflict {
  id: string;
  claim?: string;
  topic?: string;
  summary: string;
  conflictType: string;
  severity: string;
  sources: ResearchSource[];
}

interface Risk {
  riskId: string;
  label: string;
  detail: string;
}

interface BriefPreview {
  brief: string;
  assumptions: string[];
  clarifyingQuestions: string[];
  suggestedSubQuestions: string[];
  needsClarification: boolean;
  source: string;
}

interface TraceSummary {
  traceId: string;
  status: string;
  durationMs?: number;
  counters?: Record<string, number>;
  requestMeta?: Record<string, unknown>;
  responseMeta?: Record<string, unknown>;
  rawCounters?: Record<string, unknown>;
  error?: string;
  steps: TraceStep[];
}

interface TraceStep {
  name: string;
  status: string;
  durationMs: number;
  inputSize?: number | string;
  outputSize?: number | string;
  meta?: Record<string, unknown>;
  error?: string;
}

interface TaskSnapshot {
  summary: string;
  keyPoints: string[];
}

interface ArtifactPayload {
  kind: string;
  title: string;
  summary: string;
  content: string;
  tags?: string[];
}

interface DeepResearchPanelProps {
  pdfFileName?: string;
  paperStructure?: Record<string, unknown> | null;
  questionDraft?: string;
  task?: Record<string, unknown> | null;
  errorMessage?: string;
  pollError?: string;
  briefPreview?: BriefPreview | null;
  briefConstraintsDraft?: string;
  briefError?: string;
  traceSummary?: TraceSummary | null;
  traceError?: string;
  isTraceLoading?: boolean;
  isTracePanelEnabled?: boolean;
  isLoading?: boolean;
  isCreating?: boolean;
  isCancelling?: boolean;
  isPreviewingBrief?: boolean;
  allowExternalSearch?: boolean;
  allowWebSearch?: boolean;
  onQuestionChange?: (value: string) => void;
  onStart?: () => void;
  onPreviewBrief?: () => void;
  onBriefConstraintsChange?: (value: string) => void;
  onAcceptBrief?: () => void;
  onAllowExternalSearchChange?: (value: boolean) => void;
  onAllowWebSearchChange?: (value: boolean) => void;
  onRefresh?: () => void;
  onCancel?: () => void;
  onReviewPlan?: (payload: { subQuestions: string[]; reviewNotes: string }) => void;
  onReviewFinal?: (payload: { reviewNotes: string; riskReviews: { riskId: string; reviewStatus: string }[] }) => void;
  onRefreshTrace?: () => void;
  onCaptureArtifact?: (payload: ArtifactPayload) => void;
  onJumpToSource?: (source: Record<string, unknown>) => void;
}

// ── Sub-components ─────────────────────────────────────────────────────────

interface ErrorBannerProps {
  message?: string;
  tone?: 'danger' | 'warning';
}

const ErrorBanner: React.FC<ErrorBannerProps> = ({ message, tone = 'danger' }) => {
  if (!message) {
    return null;
  }

  const toneClass: string =
    tone === 'warning'
      ? 'border-amber-400/25 bg-amber-500/10 text-amber-500'
      : 'border-rose-400/25 bg-rose-500/10 text-rose-400';

  return (
    <div className={`rounded-xl border px-4 py-3 text-sm ${toneClass}`}>
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 shrink-0" size={16} />
        <div className="leading-6">{message}</div>
      </div>
    </div>
  );
};

const formatTraceMeta = (value: unknown): string => {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value as Record<string, unknown>).length === 0) {
    return '无';
  }
  return Object.entries(value as Record<string, unknown>)
    .map(([key, item]: [string, unknown]) => `${key}: ${typeof item === 'object' ? JSON.stringify(item) : item}`)
    .join(' · ');
};

interface ResearchPlanReviewFormProps {
  task: ResearchTask;
  onReviewPlan?: (payload: { subQuestions: string[]; reviewNotes: string }) => void;
}

const ResearchPlanReviewForm: React.FC<ResearchPlanReviewFormProps> = ({ task, onReviewPlan }) => {
  const [planDraft, setPlanDraft] = useState<string>(() => (task.planItems || []).map((item: PlanItem) => item.question).join('\n'));
  const [reviewNotes, setReviewNotes] = useState<string>('');
  const extConfig = task?.externalSearchConfig;
  return (
    <div className="mt-4 space-y-3 border-t theme-border pt-4">
      <div className="theme-text-primary text-sm font-semibold">人工确认后才会开始检索</div>
      {extConfig?.allowExternalSearch && (
        <div className="rounded-xl border border-indigo-400/25 bg-indigo-500/10 px-4 py-3 text-xs leading-6 text-indigo-400">
          <div className="font-semibold">外部学术检索已授权</div>
          <div className="mt-1 opacity-80">
            Provider: {extConfig.provider || '未知'}
            {' · '}Budget: 调用 {extConfig.budget?.callsUsed || 0}/{extConfig.budget?.callLimit || 0} 次
            {' · '}证据 {extConfig.budget?.evidenceUsed || 0}/{extConfig.budget?.evidenceLimit || 0} 条
          </div>
          {extConfig.degradation && <div className="mt-1 text-amber-400">⚠ {extConfig.degradation}</div>}
          <div className="mt-1 opacity-60">仅访问白名单学术来源，外部证据不自动覆盖内部判断。</div>
        </div>
      )}
      <textarea
        value={planDraft}
        onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => setPlanDraft(event.target.value)}
        className="theme-input min-h-36 w-full rounded-xl p-3 text-sm"
        aria-label="研究子问题，每行一个"
      />
      <textarea
        value={reviewNotes}
        onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => setReviewNotes(event.target.value)}
        className="theme-input min-h-20 w-full rounded-xl p-3 text-sm"
        placeholder="计划审查备注（可选）"
      />
      <button
        type="button"
        className="theme-button-primary rounded-xl px-4 py-2 text-sm font-semibold"
        onClick={() => onReviewPlan?.({ subQuestions: planDraft.split(/\r?\n/).map((item: string) => item.trim()).filter(Boolean), reviewNotes })}
      >
        确认计划并执行
      </button>
    </div>
  );
};

interface ResearchFinalReviewFormProps {
  task: ResearchTask;
  onReviewFinal?: (payload: { reviewNotes: string; riskReviews: { riskId: string; reviewStatus: string }[] }) => void;
}

const ResearchFinalReviewForm: React.FC<ResearchFinalReviewFormProps> = ({ task, onReviewFinal }) => {
  const [reviewNotes, setReviewNotes] = useState<string>('');
  const [riskReviews, setRiskReviews] = useState<Record<string, string>>(() =>
    Object.fromEntries((task.reviewRisks || []).map((risk: Risk) => [risk.riskId, 'reviewed'])),
  );
  return (
    <div className="theme-card rounded-2xl p-5">
      <div className="theme-text-primary mb-3 text-sm font-bold">终稿人工审查</div>
      <div className="space-y-3">
        {task.reviewRisks.map((risk: Risk) => (
          <div key={risk.riskId} className="theme-card-soft rounded-xl p-3">
            <div className="theme-text-primary text-sm font-semibold">{risk.label}</div>
            <div className="theme-text-secondary mt-1 text-xs leading-6">{risk.detail}</div>
            <select
              value={riskReviews[risk.riskId] || 'reviewed'}
              onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
                setRiskReviews((prev: Record<string, string>) => ({ ...prev, [risk.riskId]: event.target.value }))
              }
              className="theme-input mt-2 rounded-lg px-2 py-1 text-xs"
            >
              <option value="reviewed">已核查</option>
              <option value="needs_follow_up">仍需跟进</option>
            </select>
          </div>
        ))}
        <textarea
          value={reviewNotes}
          onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => setReviewNotes(event.target.value)}
          className="theme-input min-h-20 w-full rounded-xl p-3 text-sm"
          placeholder="终稿审查备注（可选）"
        />
        <button
          type="button"
          className="theme-button-primary rounded-xl px-4 py-2 text-sm font-semibold"
          onClick={() =>
            onReviewFinal?.({
              reviewNotes,
              riskReviews: task.reviewRisks.map((risk: Risk) => ({
                riskId: risk.riskId,
                reviewStatus: riskReviews[risk.riskId] || 'reviewed',
              })),
            })
          }
        >
          确认终稿
        </button>
      </div>
    </div>
  );
};

// ── Constants ──────────────────────────────────────────────────────────────

interface TraceCounterItem {
  key: string;
  label: string;
}

const TRACE_COUNTER_ITEMS: TraceCounterItem[] = [
  { key: 'llmCalls', label: 'LLM calls' },
  { key: 'retrievalCalls', label: 'Retrieval calls' },
  { key: 'retryCount', label: 'Retry' },
  { key: 'truncationCount', label: '截断' },
  { key: 'estimatedInputTokens', label: 'Input tokens' },
  { key: 'estimatedOutputTokens', label: 'Output tokens' },
  { key: 'externalSearchCalls', label: 'External calls' },
  { key: 'externalSearchCacheHits', label: 'External cache' },
  { key: 'externalSearchFailures', label: 'External failures' },
  { key: 'externalEvidenceCount', label: 'External evidence' },
  { key: 'externalSearchLatencyMs', label: 'External latency ms' },
  { key: 'externalSearchBudgetBlocks', label: 'External blocks' },
];

const formatCounterValue = (value: unknown): string => Number(value || 0).toLocaleString('en-US');

const formatFindingCoverage = (coverage: FindingCoverage | null | undefined): string => {
  if (!coverage || coverage.score === null) {
    return '';
  }
  const percent: number = Math.round(coverage.score * 100);
  const parts: string[] = [`覆盖 ${percent}%`];
  if (coverage.evidenceCount !== null) {
    parts.push(`证据 ${coverage.evidenceCount} 条`);
  }
  if (coverage.sourceDiversityScore !== null) {
    parts.push(`多样性 ${Math.round(coverage.sourceDiversityScore * 100)}%`);
  }
  if (coverage.sourceTrustWeightedScore !== null) {
    parts.push(`可信 ${Math.round(coverage.sourceTrustWeightedScore * 100)}%`);
  }
  return parts.join(' · ');
};

const formatSourceAnalysis = (coverage: FindingCoverage | null | undefined): string => {
  if (!coverage || typeof coverage !== 'object') return '';
  const lines: string[] = [];
  if (coverage.sourceTypes && coverage.sourceTypes.length > 0) {
    lines.push(`**来源类型**: ${coverage.sourceTypes.join(', ')}`);
  }
  if (coverage.sourceDiversityScore !== null) {
    const pct: number = Math.round(coverage.sourceDiversityScore * 100);
    lines.push(`**来源多样性 (Shannon)**: ${pct}%${pct >= 60 ? ' ✓ 多源覆盖' : pct >= 30 ? ' △ 来源偏少' : ' ✗ 来源单一'}`);
  }
  if (coverage.sourceTrustWeightedScore !== null) {
    const pct: number = Math.round(coverage.sourceTrustWeightedScore * 100);
    const label: string = pct >= 80 ? '高可信' : pct >= 55 ? '中等可信' : '可信度偏低';
    lines.push(`**可信度加权分**: ${pct}% (${label})`);
  }
  if (coverage.crossSourceAgreement !== null) {
    const pct: number = Math.round(coverage.crossSourceAgreement * 100);
    lines.push(`**跨源一致性**: ${pct}%${pct >= 70 ? ' ✓ 多源一致' : pct >= 40 ? ' △ 部分一致' : ' ✗ 一致性低'}`);
  } else {
    lines.push('**跨源一致性**: 无法评估（来源类型不足）');
  }
  return lines.join('\n');
};

const getPlanItemStatusLabel = (status: string): string => {
  if (status === 'running') return '执行中';
  if (status === 'done') return '已完成';
  if (status === 'pending') return '待执行';
  return '';
};

const getConflictTypeLabel = (type: string): string => {
  if (type === 'numeric_mismatch') return '数值不一致';
  if (type === 'opposing_conclusion') return '结论相反';
  return '待核查冲突';
};

const getConflictSeverityClass = (severity: string): string => {
  if (severity === 'high') return 'border-rose-400/25 bg-rose-500/10 text-rose-400';
  if (severity === 'low') return 'border-slate-400/25 bg-slate-500/10 text-slate-400';
  return 'border-amber-400/25 bg-amber-500/10 text-amber-500';
};

// ── Main component ─────────────────────────────────────────────────────────

const DeepResearchPanel: React.FC<DeepResearchPanelProps> = ({
  pdfFileName = '',
  paperStructure = null,
  questionDraft = '',
  task = null,
  errorMessage = '',
  pollError = '',
  briefPreview = null,
  briefConstraintsDraft = '',
  briefError = '',
  traceSummary = null,
  traceError = '',
  isTraceLoading = false,
  isTracePanelEnabled = false,
  isLoading = false,
  isCreating = false,
  isCancelling = false,
  isPreviewingBrief = false,
  allowExternalSearch = false,
  allowWebSearch = false,
  onQuestionChange,
  onStart,
  onPreviewBrief,
  onBriefConstraintsChange,
  onAcceptBrief,
  onAllowExternalSearchChange,
  onAllowWebSearchChange,
  onRefresh,
  onCancel,
  onReviewPlan,
  onReviewFinal,
  onRefreshTrace,
  onCaptureArtifact,
  onJumpToSource,
}) => {
  const normalizedTask: ResearchTask = normalizeResearchTask(task) as ResearchTask;
  const [isPlanExpanded, setIsPlanExpanded] = useState<boolean>(false);
  const [isReportExpanded, setIsReportExpanded] = useState<boolean>(false);
  const [isTraceExpanded, setIsTraceExpanded] = useState<boolean>(false);
  const statusMeta = getResearchStatusMeta(normalizedTask?.status);
  const stageMeta = getResearchStageMeta(normalizedTask?.stage);
  const paperHint: string = buildResearchContextHint(paperStructure);
  const progressPercent: number = Math.round((normalizedTask?.progress || 0) * 100);
  const panelBusy: boolean = isLoading || isCreating || isPreviewingBrief || isCancelling;
  const hasActiveTask: boolean = Boolean(normalizedTask?.taskId);
  const isTerminalTask: boolean = hasActiveTask && TERMINAL_RESEARCH_STATUSES.includes(normalizedTask.status);
  const isRunningTask: boolean = hasActiveTask && !isTerminalTask;
  const hasPaper: boolean = Boolean(pdfFileName);
  const canStart: boolean = hasPaper && !isCreating && !isCancelling && !isRunningTask && Boolean(questionDraft.trim());
  const canPreviewBrief: boolean = canStart && !isPreviewingBrief;
  const canAcceptBrief: boolean = canStart && Boolean(briefPreview);
  const canRefresh: boolean = hasActiveTask && !isCreating && !isCancelling;
  const canCancel: boolean = isRunningTask && !isCreating && !isCancelling;
  const latestFinding: Finding | null = normalizedTask?.findings?.[normalizedTask.findings.length - 1] || null;

  const taskSnapshot: TaskSnapshot | null = useMemo(() => {
    if (!hasActiveTask) {
      return null;
    }

    return {
      summary: latestFinding?.summary || `${normalizedTask.question || '当前研究问题'} 正在推进中。`,
      keyPoints: [
        `当前阶段：${stageMeta.label}`,
        `任务进度：${progressPercent}%`,
        normalizedTask?.findings?.length ? `已产出 ${normalizedTask.findings.length} 条 findings` : '正在等待 findings 输出',
      ],
    };
  }, [hasActiveTask, latestFinding?.summary, normalizedTask?.findings?.length, normalizedTask?.question, progressPercent, stageMeta.label]);

  const topActions: string[] = [
    '先给一页 brief，再决定是否启动任务',
    '可在任务运行中刷新状态或取消',
    '结果完成后可回到批判阅读核对结论',
  ];

  if (!hasActiveTask && !panelBusy) {
    return (
      <div className="theme-panel-muted flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <FileSearch className="text-pixiu" size={40} />
        </div>
        <h3 className="theme-text-primary text-xl font-bold">发起深度研究</h3>
        <p className="theme-text-secondary mb-8 mt-2 max-w-xs text-sm">
          输入一个足够具体的问题后，系统会自动规划子问题、检索与综合阶段，并逐步输出 findings。
        </p>
        <button
          type="button"
          onClick={() => onStart?.()}
          className="flex items-center gap-2 rounded-xl bg-pixiu px-8 py-3 font-semibold text-white shadow-lg transition-all hover:bg-pixiu-dark hover:shadow-pixiu/20 active:scale-95"
        >
          <Search size={20} />
          直接开始研究
        </button>
      </div>
    );
  }

  if (panelBusy && !hasActiveTask) {
    return (
      <div className="theme-panel flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="relative mb-6">
          <Loader2 className="animate-spin text-pixiu" size={48} />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="h-2 w-2 animate-ping rounded-full bg-pixiu" />
          </div>
        </div>
        <p className="theme-text-primary text-lg font-medium">正在整理深度研究任务</p>
        <p className="theme-text-secondary mt-2 text-xs">系统会先规划，再检索，最后综合输出结果。</p>
      </div>
    );
  }

  return (
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 flex items-center justify-between border-b px-6 py-4">
        <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
          <FileSearch className="text-pixiu" size={20} />
          深度研究
        </h2>
        {hasActiveTask && (
          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusMeta.toneClass}`}>
            {statusMeta.label}
          </span>
        )}
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-2 text-sm font-bold">当前研究上下文</div>
          <div className="theme-card-soft rounded-xl px-4 py-3">
            <div className="theme-text-primary text-sm font-semibold">{pdfFileName || '尚未选择论文'}</div>
            <div className="theme-text-secondary mt-2 text-sm leading-6">
              {paperHint || '围绕当前论文提出一个足够清晰的问题，系统会按规划、检索、判断和综合四个阶段逐步生成结果。'}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {topActions.map((item: string) => (
              <span key={item} className="source-link-chip inline-flex items-center gap-1">
                <ArrowRight size={12} />
                {item}
              </span>
            ))}
          </div>
          <div className="theme-text-muted mt-3 text-xs">
            已结束任务会保存为服务端快照，刷新页面后可按当前论文恢复。
          </div>
        </div>

        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-3 text-sm font-bold">研究问题</div>
          <textarea
            value={questionDraft}
            onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => onQuestionChange?.(event.target.value)}
            rows={4}
            disabled={!hasPaper || isCreating || isCancelling || isRunningTask}
            className="theme-input w-full rounded-xl p-3 text-sm outline-none transition"
            placeholder="例如：这篇论文的实验设计是否足以支撑其核心结论？哪些结论仍然缺少直接证据？"
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => onAllowExternalSearchChange?.(!allowExternalSearch)}
              disabled={isCreating || isCancelling || isRunningTask}
              className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
                allowExternalSearch ? 'bg-pixiu' : 'bg-slate-600'
              }`}
              role="switch"
              aria-checked={allowExternalSearch}
              aria-label="授权外部学术检索"
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  allowExternalSearch ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <div>
              <div className="theme-text-primary text-xs font-semibold">授权外部学术检索</div>
              <div className="theme-text-muted text-[11px] leading-5">
                仅访问白名单学术来源（Crossref、Semantic Scholar）· 默认关闭
              </div>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => onAllowWebSearchChange?.(!allowWebSearch)}
              disabled={isCreating || isCancelling || isRunningTask}
              className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
                allowWebSearch ? 'bg-pixiu' : 'bg-slate-600'
              }`}
              role="switch"
              aria-checked={allowWebSearch}
              aria-label="授权网页搜索"
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  allowWebSearch ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <div>
              <div className="theme-text-primary text-xs font-semibold">授权网页搜索</div>
              <div className="theme-text-muted text-[11px] leading-5">
                Brave + Tavily · 仅授权后启用 · 默认关闭
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onPreviewBrief}
              disabled={!canPreviewBrief}
              className="theme-button-secondary flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isPreviewingBrief ? <Loader2 className="animate-spin" size={18} /> : <FileSearch size={18} />}
              生成 brief
            </button>

            <button
              type="button"
              onClick={() => onStart?.()}
              disabled={!canStart}
              className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isCreating ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
              {hasActiveTask && isTerminalTask ? '重新发起研究' : '开始研究'}
            </button>

            <button
              type="button"
              onClick={onRefresh}
              disabled={!canRefresh}
              className="theme-button-secondary flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw size={16} className={canRefresh && !isCancelling && !isCreating ? '' : 'opacity-60'} />
              刷新状态
            </button>

            <button
              type="button"
              onClick={onCancel}
              disabled={!canCancel}
              className="theme-button-secondary flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isCancelling ? <Loader2 className="animate-spin" size={16} /> : <Square size={16} />}
              取消任务
            </button>
          </div>

          {!hasPaper && (
            <div className="theme-text-muted mt-4 text-xs">请先上传并选择一篇论文，再启动深度研究任务。</div>
          )}
        </div>

        <ErrorBanner message={errorMessage} tone="danger" />
        <ErrorBanner message={pollError} tone="warning" />
        <ErrorBanner message={briefError} tone="warning" />

        {briefPreview && (
          <div className="theme-card rounded-2xl p-5">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="theme-text-primary text-sm font-bold">brief preview</div>
                <div className="theme-text-secondary mt-1 text-xs">
                  {briefPreview.needsClarification ? '建议先补足约束再启动任务。' : '可以直接接受该 brief。'}
                </div>
              </div>
              <span className="theme-card-soft rounded-full px-3 py-1 text-[11px] font-semibold">
                {briefPreview.source === 'llm' ? 'LLM preview' : 'fallback preview'}
              </span>
            </div>

            <div className="theme-card-soft rounded-xl px-4 py-3">
              <div className="theme-text-primary text-sm font-semibold">研究范围</div>
              <div className="theme-text-secondary mt-2 text-sm leading-7">{briefPreview.brief || '暂无 brief。'}</div>
            </div>

            {briefPreview.assumptions.length > 0 && (
              <div className="mt-4">
                <div className="theme-text-primary text-xs font-bold">默认假设</div>
                <div className="mt-2 space-y-2">
                  {briefPreview.assumptions.map((item: string, index: number) => (
                    <div key={`brief-assumption-${index}`} className="theme-card-soft rounded-xl px-4 py-2 text-sm leading-6 theme-text-secondary">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {briefPreview.clarifyingQuestions.length > 0 && (
              <div className="mt-4">
                <div className="theme-text-primary text-xs font-bold">澄清问题</div>
                <div className="mt-2 space-y-2">
                  {briefPreview.clarifyingQuestions.map((item: string, index: number) => (
                    <div key={`brief-question-${index}`} className="theme-card-soft rounded-xl px-4 py-2 text-sm leading-6 theme-text-secondary">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {briefPreview.suggestedSubQuestions.length > 0 && (
              <div className="mt-4">
                <div className="theme-text-primary text-xs font-bold">建议子问题</div>
                <div className="mt-2 space-y-2">
                  {briefPreview.suggestedSubQuestions.map((item: string, index: number) => (
                    <div key={`brief-sub-question-${index}`} className="theme-card-soft rounded-xl px-4 py-2 text-sm leading-6 theme-text-secondary">
                      {index + 1}. {item}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-4">
              <div className="theme-text-primary mb-2 text-xs font-bold">补充约束</div>
              <textarea
                value={briefConstraintsDraft}
                onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => onBriefConstraintsChange?.(event.target.value)}
                rows={3}
                disabled={!hasPaper || isCreating || isCancelling || isRunningTask}
                className="theme-input w-full rounded-xl p-3 text-sm outline-none transition"
                placeholder="例如：重点检查消融实验；不要展开相关工作；优先关注过度主张风险。"
              />
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={onAcceptBrief}
                disabled={!canAcceptBrief}
                className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isCreating ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
                接受 brief 并启动
              </button>
              <button
                type="button"
                onClick={onPreviewBrief}
                disabled={!canPreviewBrief}
                className="theme-button-secondary flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isPreviewingBrief ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
                重新生成 brief
              </button>
            </div>
          </div>
        )}

        {!hasActiveTask && (
          <div className="theme-panel flex flex-col items-center justify-center rounded-2xl p-8 text-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-pixiu/10">
              <FileSearch className="text-pixiu" size={32} />
            </div>
            <div className="theme-text-primary text-lg font-semibold">等待启动深度研究任务</div>
            <div className="theme-text-secondary mt-2 max-w-sm text-sm leading-7">
              输入研究问题后，系统会先规划，再检索，最后综合输出 findings 和 Markdown 报告。
            </div>
          </div>
        )}

        {hasActiveTask && (
          <>
            <div className="theme-card rounded-2xl p-5">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="theme-text-primary text-sm font-bold">任务进度</div>
                  <div className="theme-text-secondary mt-1 text-sm">
                    {normalizedTask.question || '当前研究问题'} · 阶段：{stageMeta.label}
                  </div>
                </div>
                <div className="text-right">
                  <div className="theme-text-primary text-2xl font-bold">{progressPercent}%</div>
                  <div className="theme-text-secondary text-xs">{stageMeta.description}</div>
                </div>
              </div>

              <div className="theme-card-soft h-3 overflow-hidden rounded-full">
                <div className="h-full rounded-full bg-pixiu transition-all duration-300" style={{ width: `${progressPercent}%` }} />
              </div>

              {normalizedTask?.externalSearchConfig?.allowExternalSearch && (
                <div className={`mt-3 rounded-xl border px-4 py-2.5 text-xs leading-6 ${
                  normalizedTask.externalSearchConfig.status === 'degraded'
                    ? 'border-amber-400/25 bg-amber-500/10 text-amber-400'
                    : 'border-indigo-400/25 bg-indigo-500/10 text-indigo-400'
                }`}>
                  <span className="font-semibold">
                    外部检索：{normalizedTask.externalSearchConfig.provider}
                  </span>
                  <span className="opacity-75">
                    {' '}· 已调用 {normalizedTask.externalSearchConfig.budget.callsUsed}/{normalizedTask.externalSearchConfig.budget.callLimit} 次
                    · 已收集 {normalizedTask.externalSearchConfig.budget.evidenceUsed}/{normalizedTask.externalSearchConfig.budget.evidenceLimit} 条
                  </span>
                  {normalizedTask.externalSearchConfig.status === 'degraded' && normalizedTask.externalSearchConfig.degradation && (
                    <span className="block mt-1">
                      ⚠ 已降级：{normalizedTask.externalSearchConfig.degradation}
                    </span>
                  )}
                </div>
              )}

              <div className="theme-text-muted mt-3 text-xs">
                Task ID: {normalizedTask.taskId || '未知'} | Trace ID: {normalizedTask.traceId || '未知'} | 状态：{statusMeta.label}
              </div>
            </div>

            {isTracePanelEnabled && (
              <div className="theme-card rounded-2xl p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="theme-text-primary text-sm font-bold">Trace 调试</div>
                    <div className="theme-text-secondary mt-1 text-xs">
                      {normalizedTask.traceId ? `Trace ID: ${normalizedTask.traceId}` : '当前任务没有返回 traceId'}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={onRefreshTrace}
                      disabled={!normalizedTask.traceId || isTraceLoading}
                      className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isTraceLoading ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                      刷新 trace
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsTraceExpanded((current: boolean) => !current)}
                      disabled={!traceSummary}
                      className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isTraceExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      {isTraceExpanded ? '收起详情' : '展开详情'}
                    </button>
                  </div>
                </div>

                {traceError && <ErrorBanner message={traceError} tone="warning" />}

                {traceSummary ? (
                  <div className="space-y-3">
                    <div className="grid gap-3 text-xs sm:grid-cols-2">
                      <div className="theme-card-soft rounded-xl px-4 py-3">
                        <div className="theme-text-muted">状态</div>
                        <div className="theme-text-primary mt-1 font-semibold">
                          {traceSummary.status} · {traceSummary.durationMs ?? 0}ms
                        </div>
                      </div>
                      <div className="theme-card-soft rounded-xl px-4 py-3">
                        <div className="theme-text-muted">预算计数器</div>
                        <div className="mt-2 grid grid-cols-2 gap-2">
                          {TRACE_COUNTER_ITEMS.map((item: TraceCounterItem) => (
                            <div key={item.key} className="min-w-0">
                              <div className="theme-text-muted truncate">{item.label}</div>
                              <div className="theme-text-primary font-semibold">{formatCounterValue(traceSummary.counters?.[item.key])}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    {isTraceExpanded && (
                      <div className="space-y-3">
                        <div className="theme-card-soft rounded-xl px-4 py-3 text-xs leading-6">
                          <div className="theme-text-primary font-semibold">请求摘要</div>
                          <div className="theme-text-secondary mt-1">{formatTraceMeta(traceSummary.requestMeta)}</div>
                          <div className="theme-text-primary mt-3 font-semibold">响应摘要</div>
                          <div className="theme-text-secondary mt-1">{formatTraceMeta(traceSummary.responseMeta)}</div>
                          <div className="theme-text-primary mt-3 font-semibold">原始计数器</div>
                          <div className="theme-text-secondary mt-1">{formatTraceMeta(traceSummary.rawCounters)}</div>
                          {traceSummary.error && (
                            <>
                              <div className="theme-text-primary mt-3 font-semibold">错误摘要</div>
                              <div className="text-rose-400 mt-1">{traceSummary.error}</div>
                            </>
                          )}
                        </div>

                        <div className="space-y-2">
                          {traceSummary.steps.length > 0 ? (
                            traceSummary.steps.map((step: TraceStep, index: number) => (
                              <div key={`${traceSummary.traceId}-step-${index}`} className="theme-card-soft rounded-xl px-4 py-3 text-xs">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <div className="theme-text-primary font-semibold">
                                    {index + 1}. {step.name}
                                  </div>
                                  <div className={step.status === 'error' ? 'text-rose-400' : 'text-emerald-400'}>
                                    {step.status} · {step.durationMs}ms
                                  </div>
                                </div>
                                <div className="theme-text-secondary mt-2 leading-6">
                                  input: {step.inputSize ?? 'n/a'} · output: {step.outputSize ?? 'n/a'} · meta: {formatTraceMeta(step.meta)}
                                </div>
                                {step.error && <div className="mt-2 text-rose-400">{step.error}</div>}
                              </div>
                            ))
                          ) : (
                            <div className="theme-text-secondary text-sm">当前 trace 还没有记录步骤。</div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="theme-text-secondary text-sm">
                    {isTraceLoading ? '正在加载 trace summary...' : '尚未加载 trace summary。'}
                  </div>
                )}
              </div>
            )}

            {taskSnapshot && (
              <InsightCard
                title="当前结论快照"
                summary={taskSnapshot.summary}
                keyPoints={taskSnapshot.keyPoints}
                detailsTitle="展开任务详情"
                content={[
                  normalizedTask.question ? `### 研究问题\n${normalizedTask.question}` : '',
                  latestFinding ? `### 最近一条 finding\n${latestFinding.summary}` : '',
                ].filter(Boolean).join('\n\n')}
                footer={onCaptureArtifact ? (
                  <button
                    type="button"
                    onClick={() =>
                      onCaptureArtifact({
                        kind: 'research-snapshot',
                        title: '深度研究快照',
                        summary: taskSnapshot.summary,
                        content: [
                          normalizedTask.question ? `### 研究问题\n${normalizedTask.question}` : '',
                          latestFinding ? `### 最近一条 finding\n${latestFinding.summary}` : '',
                        ].filter(Boolean).join('\n\n'),
                        tags: ['research', 'snapshot'],
                      })
                    }
                    className="source-link-chip"
                  >
                    加入工作台
                  </button>
                ) : null}
              />
            )}

            <div className="theme-card rounded-2xl p-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="theme-text-primary text-sm font-bold">研究计划</div>
                <button
                  type="button"
                  onClick={() => setIsPlanExpanded((current: boolean) => !current)}
                  className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
                >
                  {isPlanExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  {isPlanExpanded ? '收起计划' : '展开计划'}
                </button>
              </div>
              {normalizedTask.planItems.length > 0 ? (
                isPlanExpanded ? (
                  <div className="space-y-3">
                    {normalizedTask.planItems.map((item: PlanItem, index: number) => {
                      const statusLabel: string = getPlanItemStatusLabel(item.status || '');
                      return (
                        <div key={`${normalizedTask.taskId}-plan-${index}`} className="theme-card-soft rounded-xl px-4 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="theme-text-primary text-sm font-semibold">
                              {item.kind === 'follow_up' ? 'Follow-up' : `子问题 ${index + 1}`}
                            </div>
                            {item.kind === 'follow_up' ? (
                              <span className="rounded-full border border-amber-400/25 bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-500">
                                缺口驱动
                              </span>
                            ) : null}
                            {statusLabel ? (
                              <span className="theme-text-muted rounded-full border theme-border px-2 py-0.5 text-[11px]">
                                {statusLabel}
                              </span>
                            ) : null}
                          </div>
                          <div className="theme-text-secondary mt-1 text-sm leading-7">{item.question}</div>
                          {item.kind === 'follow_up' ? (
                            <div className="theme-text-muted mt-2 text-xs leading-6">
                              {item.sourceQuestion ? `由"${item.sourceQuestion}"的证据缺口生成` : '由证据缺口生成'}
                              {item.sourceMissingAspects && item.sourceMissingAspects.length > 0 ? `：${item.sourceMissingAspects.join('、')}` : ''}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {normalizedTask.planItems.slice(0, 2).map((item: PlanItem, index: number) => (
                      <div key={`${normalizedTask.taskId}-plan-preview-${index}`} className="theme-card-soft rounded-xl px-4 py-3 text-sm leading-7 theme-text-secondary">
                        {item.kind === 'follow_up' ? 'Follow-up：' : ''}{item.question}
                      </div>
                    ))}
                  </div>
                )
              ) : (
                <div className="theme-text-secondary text-sm">任务正在规划研究路径，稍后会显示子问题列表。</div>
              )}
              {normalizedTask.status === 'awaiting_plan_review' && (
                <ResearchPlanReviewForm key={normalizedTask.taskId} task={normalizedTask} onReviewPlan={onReviewPlan} />
              )}
            </div>

            <div className="theme-card rounded-2xl p-5">
              <div className="theme-text-primary mb-3 text-sm font-bold">Findings</div>
              {normalizedTask.findings.length > 0 ? (
                <div className="space-y-4">
                  {normalizedTask.findings.map((finding: Finding) => {
                    const verdictMeta = getResearchVerdictMeta(finding.verdict);
                    const judgeText: string = finding.judgeScore !== null ? `JUDGE ${finding.judgeScore}/100` : '';
                    const coverageText: string = formatFindingCoverage(finding.coverage);
                    return (
                      <InsightCard
                        key={`${normalizedTask.taskId}-${finding.id}`}
                        title={finding.subQuestion}
                        summary={finding.summary}
                        keyPoints={[
                          judgeText,
                          coverageText,
                          finding.sources.length > 0
                            ? `来源：${finding.sources.map((source: ResearchSource) => source.locationLabel ? `${source.sourceId} (${source.locationLabel})` : source.sourceId).join('、')}`
                            : '尚未绑定来源片段',
                          finding.missingAspects.length > 0 ? `仍缺证据：${finding.missingAspects.join('、')}` : '当前没有额外缺口提示',
                          finding.retryReason ? `Retry：${finding.retryReason}` : '',
                        ].filter(Boolean)}
                        meta={(
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${verdictMeta.toneClass}`}>
                            {verdictMeta.label}
                          </span>
                        )}
                        content={[
                          `### 结论摘要\n${finding.summary}`,
                          judgeText || coverageText ? `### JUDGE 评分\n${[judgeText, coverageText].filter(Boolean).join(' · ')}` : '',
                          formatSourceAnalysis(finding.coverage)
                            ? `### 来源分析\n${formatSourceAnalysis(finding.coverage)}`
                            : '',
                          finding.sources.length > 0
                            ? `### 证据来源\n${finding.sources.map((source: ResearchSource) => `- [${source.sourceId}]${source.locationLabel ? ` ${source.locationLabel}` : ''} ${source.preview || ''}`).join('\n')}`
                            : '',
                          finding.missingAspects.length > 0 ? `### 仍缺少的证据点\n- ${finding.missingAspects.join('\n- ')}` : '',
                          finding.retryReason ? `### Retry 原因\n${finding.retryReason}` : '',
                        ].filter(Boolean).join('\n\n')}
                        detailsTitle="展开 finding 详情"
                        footer={onCaptureArtifact || finding.sources.some((source: ResearchSource) => source.canJumpToSource) ? (
                          <div className="flex flex-wrap gap-2">
                            {onCaptureArtifact && (
                              <button
                                type="button"
                                onClick={() =>
                                  onCaptureArtifact({
                                    kind: 'research-finding',
                                    title: finding.subQuestion,
                                    summary: finding.summary,
                                    content: [
                                      `### 结论摘要\n${finding.summary}`,
                                      judgeText || coverageText ? `### JUDGE 评分\n${[judgeText, coverageText].filter(Boolean).join(' · ')}` : '',
                                      formatSourceAnalysis(finding.coverage)
                                        ? `### 来源分析\n${formatSourceAnalysis(finding.coverage)}`
                                        : '',
                                      finding.sources.length > 0
                                        ? `### 证据来源\n${finding.sources.map((source: ResearchSource) => `- [${source.sourceId}]${source.locationLabel ? ` ${source.locationLabel}` : ''} ${source.preview || ''}`).join('\n')}`
                                        : '',
                                      finding.missingAspects.length > 0 ? `### 仍缺少的证据点\n- ${finding.missingAspects.join('\n- ')}` : '',
                                      finding.retryReason ? `### Retry 原因\n${finding.retryReason}` : '',
                                    ].filter(Boolean).join('\n\n'),
                                    tags: ['research', finding.verdict.toLowerCase()],
                                  })
                                }
                                className="source-link-chip"
                              >
                                加入工作台
                              </button>
                            )}
                            <SourceList sources={finding.sources} onJumpToSource={onJumpToSource} />
                          </div>
                        ) : null}
                      />
                    );
                  })}
                </div>
              ) : (
                <div className="theme-text-secondary text-sm">
                  {isRunningTask ? '正在整理 findings，稍后会逐步显示结构化结果。' : '当前任务还没有返回 findings。'}
                </div>
              )}
            </div>

            {normalizedTask.status === 'awaiting_final_review' && (
              <ResearchFinalReviewForm key={normalizedTask.taskId} task={normalizedTask} onReviewFinal={onReviewFinal} />
            )}

            <div className="theme-card rounded-2xl p-5">
              <div className="theme-text-primary mb-3 text-sm font-bold">证据冲突/需人工核查</div>
              {normalizedTask.conflicts.length > 0 ? (
                <div className="space-y-4">
                  {normalizedTask.conflicts.map((conflict: Conflict) => (
                    <InsightCard
                      key={`${normalizedTask.taskId}-${conflict.id}`}
                      title={conflict.claim || conflict.topic || '跨源证据冲突'}
                      summary={conflict.summary}
                      keyPoints={[
                        getConflictTypeLabel(conflict.conflictType),
                        conflict.sources.length > 0
                          ? `来源：${conflict.sources.map((source: ResearchSource) => source.locationLabel ? `${source.sourceId} (${source.locationLabel})` : source.sourceId).join('、')}`
                          : '尚未绑定来源片段',
                      ]}
                      meta={(
                        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${getConflictSeverityClass(conflict.severity)}`}>
                          {conflict.severity === 'high' ? '高风险' : conflict.severity === 'low' ? '低风险' : '中风险'}
                        </span>
                      )}
                      content={[
                        `### 冲突摘要\n${conflict.summary}`,
                        `### 类型\n${getConflictTypeLabel(conflict.conflictType)}`,
                        conflict.sources.length > 0
                          ? `### 冲突来源\n${conflict.sources.map((source: ResearchSource) => `- [${source.sourceId}]${source.locationLabel ? ` ${source.locationLabel}` : ''} ${source.preview || ''}`).join('\n')}`
                          : '',
                      ].filter(Boolean).join('\n\n')}
                      detailsTitle="展开冲突详情"
                      footer={conflict.sources.some((source: ResearchSource) => source.canJumpToSource) ? (
                        <div className="flex flex-wrap gap-2">
                          <SourceList sources={conflict.sources} onJumpToSource={onJumpToSource} />
                        </div>
                      ) : null}
                    />
                  ))}
                </div>
              ) : (
                <div className="theme-text-secondary text-sm">当前未检测到明确跨源冲突。</div>
              )}
            </div>

            <div className="theme-card rounded-2xl p-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="theme-text-primary text-sm font-bold">研究报告</div>
                {normalizedTask.report && (
                  <button
                    type="button"
                    onClick={() => setIsReportExpanded((current: boolean) => !current)}
                    className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
                  >
                    {isReportExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    {isReportExpanded ? '收起报告' : '展开报告'}
                  </button>
                )}
              </div>
              {normalizedTask.report ? (
                isReportExpanded ? (
                  <div className="theme-markdown-panel rounded-xl p-4">
                    <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
                      {normalizedTask.report}
                    </MarkdownContent>
                  </div>
                ) : (
                  <InsightCard
                    summary={normalizedTask.report}
                    content={normalizedTask.report}
                    detailsTitle="展开完整报告"
                    className="border-none p-0 shadow-none"
                  />
                )
              ) : (
                <div className="theme-text-secondary text-sm">
                  {isRunningTask ? 'Markdown 报告会在综合阶段生成。' : '当前任务尚未生成最终报告。'}
                </div>
              )}
            </div>

            {normalizedTask.error && <ErrorBanner message={normalizedTask.error} tone="danger" />}
          </>
        )}
      </div>
    </div>
  );
};

export default DeepResearchPanel;
