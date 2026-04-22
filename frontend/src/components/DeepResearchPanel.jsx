import React from 'react';
import {
  AlertCircle,
  FileSearch,
  Loader2,
  RefreshCw,
  Search,
  Square,
} from 'lucide-react';

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

const DeepResearchPanel = ({
  pdfFileName = '',
  paperStructure = null,
  questionDraft = '',
  task = null,
  errorMessage = '',
  pollError = '',
  isCreating = false,
  isCancelling = false,
  onQuestionChange,
  onStart,
  onRefresh,
  onCancel,
}) => {
  const normalizedTask = normalizeResearchTask(task);
  const statusMeta = getResearchStatusMeta(normalizedTask?.status);
  const stageMeta = getResearchStageMeta(normalizedTask?.stage);
  const paperHint = buildResearchContextHint(paperStructure);
  const progressPercent = Math.round((normalizedTask?.progress || 0) * 100);
  const hasActiveTask = Boolean(normalizedTask?.taskId);
  const isTerminalTask = hasActiveTask && TERMINAL_RESEARCH_STATUSES.includes(normalizedTask.status);
  const isRunningTask = hasActiveTask && !isTerminalTask;
  const hasPaper = Boolean(pdfFileName);
  const canStart = hasPaper && !isCreating && !isCancelling && !isRunningTask && Boolean(questionDraft.trim());
  const canRefresh = hasActiveTask && !isCreating && !isCancelling;
  const canCancel = isRunningTask && !isCreating && !isCancelling;

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
          <div className="theme-text-primary mb-2 text-sm font-bold">当前论文上下文</div>
          <div className="theme-card-soft rounded-xl px-4 py-3">
            <div className="theme-text-primary text-sm font-semibold">{pdfFileName || '尚未选择论文'}</div>
            <div className="theme-text-secondary mt-2 text-sm leading-6">
              {paperHint || '围绕当前论文提出一个较大的研究问题，系统会按规划、检索、判断、综合四个阶段逐步生成 findings 与报告。'}
            </div>
          </div>
          <div className="theme-text-muted mt-3 text-xs">
            当前任务状态只保留在本次浏览器会话内存中。刷新页面或后端服务重启后，运行中的任务不保证可恢复。
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
              onClick={onStart}
              disabled={!canStart}
              className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isCreating ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
              {hasActiveTask && isTerminalTask ? '重新发起研究' : '开始深度研究'}
            </button>

            <button
              onClick={onRefresh}
              disabled={!canRefresh}
              className="theme-button-secondary flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw size={16} className={canRefresh && !isCancelling && !isCreating ? '' : 'opacity-60'} />
              刷新状态
            </button>

            <button
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

        {!hasActiveTask && (
          <div className="theme-panel flex flex-col items-center justify-center rounded-2xl p-8 text-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-pixiu/10">
              <FileSearch className="text-pixiu" size={32} />
            </div>
            <div className="theme-text-primary text-lg font-semibold">等待启动深度研究任务</div>
            <div className="theme-text-secondary mt-2 max-w-sm text-sm leading-7">
              输入研究问题后，系统会自动创建任务，轮询状态，并逐步展示子问题 findings 与最终 Markdown 报告。
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
                <div
                  className="h-full rounded-full bg-pixiu transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>

              <div className="theme-text-muted mt-3 text-xs">
                Task ID: {normalizedTask.taskId || '未返回'} | 状态：{statusMeta.label}
              </div>
            </div>

            <div className="theme-card rounded-2xl p-5">
              <div className="theme-text-primary mb-3 text-sm font-bold">研究计划</div>
              {normalizedTask.plan.length > 0 ? (
                <div className="space-y-3">
                  {normalizedTask.plan.map((item, index) => (
                    <div key={`${normalizedTask.taskId}-plan-${index}`} className="theme-card-soft rounded-xl px-4 py-3">
                      <div className="theme-text-primary text-sm font-semibold">子问题 {index + 1}</div>
                      <div className="theme-text-secondary mt-1 text-sm leading-7">{item}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="theme-text-secondary text-sm">任务正在规划研究路径，子问题生成后会显示在这里。</div>
              )}
            </div>

            <div className="theme-card rounded-2xl p-5">
              <div className="theme-text-primary mb-3 text-sm font-bold">Findings</div>
              {normalizedTask.findings.length > 0 ? (
                <div className="space-y-4">
                  {normalizedTask.findings.map((finding) => {
                    const verdictMeta = getResearchVerdictMeta(finding.verdict);
                    return (
                      <div key={`${normalizedTask.taskId}-${finding.id}`} className="theme-card-soft rounded-xl px-4 py-4">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                          <div className="theme-text-primary text-sm font-semibold">{finding.subQuestion}</div>
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${verdictMeta.toneClass}`}>
                            {verdictMeta.label}
                          </span>
                        </div>

                        <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
                          {finding.summary}
                        </MarkdownContent>

                        {finding.sourceIds.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {finding.sourceIds.map((sourceId) => (
                              <span key={`${finding.id}-${sourceId}`} className="rounded-full bg-pixiu/10 px-3 py-1 text-[11px] font-semibold text-pixiu">
                                {sourceId}
                              </span>
                            ))}
                          </div>
                        )}

                        {finding.missingAspects.length > 0 && (
                          <div className="mt-3 text-sm">
                            <div className="theme-text-secondary mb-1 text-xs font-semibold tracking-wide">仍缺少的证据点</div>
                            <div className="theme-text-secondary leading-7">{finding.missingAspects.join('、')}</div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="theme-text-secondary text-sm">
                  {isRunningTask ? '任务正在整理 findings，随着阶段推进这里会逐步出现结构化结论。' : '当前任务还没有返回 findings。'}
                </div>
              )}
            </div>

            <div className="theme-card rounded-2xl p-5">
              <div className="theme-text-primary mb-3 text-sm font-bold">研究报告</div>
              {normalizedTask.report ? (
                <div className="theme-markdown-panel rounded-xl p-4">
                  <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
                    {normalizedTask.report}
                  </MarkdownContent>
                </div>
              ) : (
                <div className="theme-text-secondary text-sm">
                  {isRunningTask ? 'Markdown 报告将在综合阶段生成。' : '当前任务尚未生成最终报告。'}
                </div>
              )}
            </div>

            {normalizedTask.error && (
              <ErrorBanner message={normalizedTask.error} tone="danger" />
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default DeepResearchPanel;
