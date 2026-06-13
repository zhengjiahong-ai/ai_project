import React, { useMemo, useState } from 'react';
import { AlertCircle, ChevronDown, ChevronUp, FileSearch, Link2, Loader2, RefreshCw, Search, Square, ArrowRight } from 'lucide-react';

import InsightCard from './InsightCard.jsx';
import MarkdownContent from './MarkdownContent';
import {
  TERMINAL_RESEARCH_STATUSES,
  buildResearchContextHint,
  getResearchStageMeta,
  getResearchStatusMeta,
  getResearchVerdictMeta,
  normalizeResearchTask,
} from './deepResearchPanelModel.js';

const ErrorBanner = ({ message, tone = 'danger' }) => {
  if (!message) {
    return null;
  }

  const toneClass =
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

const formatTraceMeta = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length === 0) {
    return '无';
  }
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${typeof item === 'object' ? JSON.stringify(item) : item}`)
    .join(' · ');
};

const formatFindingCoverage = (coverage) => {
  if (!coverage || coverage.score === null) {
    return '';
  }
  const percent = Math.round(coverage.score * 100);
  const evidenceText = coverage.evidenceCount !== null ? ` · 证据 ${coverage.evidenceCount} 条` : '';
  return `覆盖 ${percent}%${evidenceText}`;
};

const getPlanItemStatusLabel = (status) => {
  if (status === 'running') {
    return '执行中';
  }
  if (status === 'done') {
    return '已完成';
  }
  if (status === 'pending') {
    return '待执行';
  }
  return '';
};

const DeepResearchPanel = ({
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
  onQuestionChange,
  onStart,
  onPreviewBrief,
  onBriefConstraintsChange,
  onAcceptBrief,
  onRefresh,
  onCancel,
  onRefreshTrace,
  onCaptureArtifact,
  onJumpToSource,
}) => {
  const normalizedTask = normalizeResearchTask(task);
  const [isPlanExpanded, setIsPlanExpanded] = useState(false);
  const [isReportExpanded, setIsReportExpanded] = useState(false);
  const [isTraceExpanded, setIsTraceExpanded] = useState(false);
  const statusMeta = getResearchStatusMeta(normalizedTask?.status);
  const stageMeta = getResearchStageMeta(normalizedTask?.stage);
  const paperHint = buildResearchContextHint(paperStructure);
  const progressPercent = Math.round((normalizedTask?.progress || 0) * 100);
  const panelBusy = isLoading || isCreating || isPreviewingBrief || isCancelling;
  const hasActiveTask = Boolean(normalizedTask?.taskId);
  const isTerminalTask = hasActiveTask && TERMINAL_RESEARCH_STATUSES.includes(normalizedTask.status);
  const isRunningTask = hasActiveTask && !isTerminalTask;
  const hasPaper = Boolean(pdfFileName);
  const canStart = hasPaper && !isCreating && !isCancelling && !isRunningTask && Boolean(questionDraft.trim());
  const canPreviewBrief = canStart && !isPreviewingBrief;
  const canAcceptBrief = canStart && Boolean(briefPreview);
  const canRefresh = hasActiveTask && !isCreating && !isCancelling;
  const canCancel = isRunningTask && !isCreating && !isCancelling;
  const latestFinding = normalizedTask?.findings?.[normalizedTask.findings.length - 1] || null;

  const taskSnapshot = useMemo(() => {
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

  const topActions = [
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
            {topActions.map((item) => (
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
            onChange={(event) => onQuestionChange?.(event.target.value)}
            rows={4}
            disabled={!hasPaper || isCreating || isCancelling || isRunningTask}
            className="theme-input w-full rounded-xl p-3 text-sm outline-none transition"
            placeholder="例如：这篇论文的实验设计是否足以支撑其核心结论？哪些结论仍然缺少直接证据？"
          />

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
                  {briefPreview.assumptions.map((item, index) => (
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
                  {briefPreview.clarifyingQuestions.map((item, index) => (
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
                  {briefPreview.suggestedSubQuestions.map((item, index) => (
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
                onChange={(event) => onBriefConstraintsChange?.(event.target.value)}
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
                      onClick={() => setIsTraceExpanded((current) => !current)}
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
                        <div className="theme-text-muted">计数器</div>
                        <div className="theme-text-primary mt-1 font-semibold">{formatTraceMeta(traceSummary.counters)}</div>
                      </div>
                    </div>

                    {isTraceExpanded && (
                      <div className="space-y-3">
                        <div className="theme-card-soft rounded-xl px-4 py-3 text-xs leading-6">
                          <div className="theme-text-primary font-semibold">请求摘要</div>
                          <div className="theme-text-secondary mt-1">{formatTraceMeta(traceSummary.requestMeta)}</div>
                          <div className="theme-text-primary mt-3 font-semibold">响应摘要</div>
                          <div className="theme-text-secondary mt-1">{formatTraceMeta(traceSummary.responseMeta)}</div>
                          {traceSummary.error && (
                            <>
                              <div className="theme-text-primary mt-3 font-semibold">错误摘要</div>
                              <div className="text-rose-400 mt-1">{traceSummary.error}</div>
                            </>
                          )}
                        </div>

                        <div className="space-y-2">
                          {traceSummary.steps.length > 0 ? (
                            traceSummary.steps.map((step, index) => (
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
                  onClick={() => setIsPlanExpanded((current) => !current)}
                  className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
                >
                  {isPlanExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  {isPlanExpanded ? '收起计划' : '展开计划'}
                </button>
              </div>
              {normalizedTask.planItems.length > 0 ? (
                isPlanExpanded ? (
                  <div className="space-y-3">
                    {normalizedTask.planItems.map((item, index) => {
                      const statusLabel = getPlanItemStatusLabel(item.status);
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
                            {item.sourceQuestion ? `由“${item.sourceQuestion}”的证据缺口生成` : '由证据缺口生成'}
                            {item.sourceMissingAspects.length > 0 ? `：${item.sourceMissingAspects.join('、')}` : ''}
                          </div>
                        ) : null}
                      </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {normalizedTask.planItems.slice(0, 2).map((item, index) => (
                      <div key={`${normalizedTask.taskId}-plan-preview-${index}`} className="theme-card-soft rounded-xl px-4 py-3 text-sm leading-7 theme-text-secondary">
                        {item.kind === 'follow_up' ? 'Follow-up：' : ''}{item.question}
                      </div>
                    ))}
                  </div>
                )
              ) : (
                <div className="theme-text-secondary text-sm">任务正在规划研究路径，稍后会显示子问题列表。</div>
              )}
            </div>

            <div className="theme-card rounded-2xl p-5">
              <div className="theme-text-primary mb-3 text-sm font-bold">Findings</div>
              {normalizedTask.findings.length > 0 ? (
                <div className="space-y-4">
                  {normalizedTask.findings.map((finding) => {
                    const verdictMeta = getResearchVerdictMeta(finding.verdict);
                    const judgeText = finding.judgeScore !== null ? `JUDGE ${finding.judgeScore}/100` : '';
                    const coverageText = formatFindingCoverage(finding.coverage);
                    return (
                      <InsightCard
                        key={`${normalizedTask.taskId}-${finding.id}`}
                        title={finding.subQuestion}
                        summary={finding.summary}
                        keyPoints={[
                          judgeText,
                          coverageText,
                          finding.sources.length > 0
                            ? `来源：${finding.sources.map((source) => source.locationLabel ? `${source.sourceId} (${source.locationLabel})` : source.sourceId).join('、')}`
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
                          finding.sources.length > 0
                            ? `### 证据来源\n${finding.sources.map((source) => `- [${source.sourceId}]${source.locationLabel ? ` ${source.locationLabel}` : ''} ${source.preview || ''}`).join('\n')}`
                            : '',
                          finding.missingAspects.length > 0 ? `### 仍缺少的证据点\n- ${finding.missingAspects.join('\n- ')}` : '',
                          finding.retryReason ? `### Retry 原因\n${finding.retryReason}` : '',
                        ].filter(Boolean).join('\n\n')}
                        detailsTitle="展开 finding 详情"
                        footer={onCaptureArtifact || finding.sources.some((source) => source.canJumpToSource) ? (
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
                                      finding.sources.length > 0
                                        ? `### 证据来源\n${finding.sources.map((source) => `- [${source.sourceId}]${source.locationLabel ? ` ${source.locationLabel}` : ''} ${source.preview || ''}`).join('\n')}`
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
                            {finding.sources
                              .filter((source) => source.canJumpToSource)
                              .map((source) => (
                                <button
                                  key={source.sourceId}
                                  type="button"
                                  onClick={() => onJumpToSource?.(source)}
                                  className="source-link-chip inline-flex items-center gap-1"
                                >
                                  <Link2 size={12} />
                                  跳回原文 {source.locationLabel}
                                </button>
                              ))}
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

            <div className="theme-card rounded-2xl p-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="theme-text-primary text-sm font-bold">研究报告</div>
                {normalizedTask.report && (
                  <button
                    type="button"
                    onClick={() => setIsReportExpanded((current) => !current)}
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
