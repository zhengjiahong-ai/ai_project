import React, { useState } from 'react';
import { AlertTriangle, Archive, BookOpen, FileText, GitCompare, Sparkles, Terminal, Workflow } from 'lucide-react';

import { buildAgentComparisonArtifact, buildAgentReportArtifact } from '../artifactModel.js';
import SourceList from '../SourceCitation.jsx';
import { getAgentArtifactSaveState } from './agentWorkspaceModel.js';
import { formatAgentTime, getStatusLabel, getStatusTone } from './agentWorkspaceUi.js';

export const AgentTaskPromptBubble = ({ task, prompt }) => (
  <div className="flex justify-end">
    <div className="agent-user-bubble max-w-[82%] rounded-[22px]">
      <div className="agent-header flex items-center justify-between gap-4 border-b px-4 py-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-[color:var(--accent-strong)]">
          <span className="agent-card inline-flex h-6 w-6 items-center justify-center rounded-lg text-[11px] font-bold">
            你
          </span>
          研究请求
        </div>
        <span className="agent-muted text-[11px]">{formatAgentTime(task?.createdAt || task?.updatedAt) || '实时输入'}</span>
      </div>
      <div className="agent-body whitespace-pre-wrap px-4 py-3 text-sm leading-7">
        {task?.prompt || prompt || '输入一个多论文研究任务，例如比较方法、证据和局限性。'}
      </div>
    </div>
  </div>
);

export const AgentTaskHistoryCard = ({ task, isActive, onSelect }) => (
  <button
    type="button"
    onClick={() => onSelect?.(task)}
    className={`w-full rounded-[22px] border p-4 text-left transition ${
      isActive
        ? 'agent-card'
        : 'agent-card-soft hover:border-[color:var(--accent)]'
    }`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="agent-title line-clamp-2 text-sm font-semibold leading-6">
          {task.prompt || '未命名研究任务'}
        </div>
        <div className="agent-muted mt-1 text-[11px]">
          {formatAgentTime(task.updatedAt || task.createdAt)} · {task.stage || 'planning'}
        </div>
      </div>
      <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${getStatusTone(task.status)}`}>
        {getStatusLabel(task.status)}
      </span>
    </div>
    <div className="agent-muted mt-3 grid gap-2 text-[11px] sm:grid-cols-3">
      <div className="agent-card-soft rounded-xl px-3 py-2">{(task.events || []).length} 个事件</div>
      <div className="agent-card-soft rounded-xl px-3 py-2">{(task.evidenceItems || []).length} 条证据</div>
      <div className="agent-card-soft rounded-xl px-3 py-2">{(task.conflicts || []).length} 个冲突</div>
    </div>
  </button>
);

export const AgentTaskHistorySection = ({ tasks, currentTask, onSelectTask }) => {
  if (!tasks.length) {
    return (
      <div className="agent-empty-state rounded-[24px] border-dashed px-5 py-8 text-center">
        <div className="agent-title text-sm font-semibold">还没有研究记录</div>
        <p className="agent-muted mx-auto mt-2 max-w-xl text-xs leading-6">
          创建项目后，在底部输入框发起第一个任务。之后每次提问都会作为独立研究记录保留在当前项目下。
        </p>
      </div>
    );
  }

  return (
    <section className="agent-section rounded-[24px] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="agent-title text-sm font-semibold">项目对话记录</div>
          <div className="agent-muted mt-1 text-[11px]">每次研究请求都会保留，可点击切换查看过程和结果。</div>
        </div>
        <span className="agent-chip-accent px-2.5 py-1 text-[11px] font-semibold">
          {tasks.length} tasks
        </span>
      </div>
      <div className="grid gap-3">
        {tasks.map((task) => (
          <AgentTaskHistoryCard
            key={task.taskId}
            task={task}
            isActive={task.taskId === currentTask?.taskId}
            onSelect={onSelectTask}
          />
        ))}
      </div>
    </section>
  );
};

export const AgentTimelineSection = ({ currentTask }) => {
  const events = currentTask?.events || [];

  return (
    <details className="agent-section mt-4 rounded-[18px]" open>
      <summary className="agent-title flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
        <span className="flex items-center gap-2">
          <span className="agent-icon-accent inline-flex h-6 w-6 items-center justify-center rounded-lg">
            <Workflow size={14} />
          </span>
          研究过程时间线
        </span>
        <span className="agent-chip-accent px-2.5 py-1 text-[11px] font-semibold">
          {events.length} events
        </span>
      </summary>
      <div className="space-y-2 px-4 pb-4">
        {events.map((event, index) => (
          <div key={event.eventId || `${event.type}-${index}`} className="grid grid-cols-[16px_minmax(0,1fr)] gap-3">
            <div className="pt-1">
              <span className="agent-timeline-dot block h-3 w-3 rounded-full" />
            </div>
            <div className="agent-card rounded-2xl px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="agent-title text-xs font-semibold">{event.summary || event.type}</span>
                <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--accent-strong)]">
                  {event.stage || currentTask?.stage || 'stage'}
                </span>
              </div>
              <div className="agent-muted mt-1 text-[10px]">{event.type}</div>
            </div>
          </div>
        ))}
        {events.length === 0 && (
          <div className="agent-empty-state rounded-2xl border-dashed px-4 py-4 text-xs leading-6">
            启动任务后，这里会随着轮询逐步出现规划、检索、判断和报告更新事件。
          </div>
        )}
      </div>
    </details>
  );
};

const AgentPlanReviewForm = ({ currentTask, activeProject, onReviewPlan }) => {
  const [items, setItems] = useState(() => (currentTask?.planItems || []).map((item) => ({ ...item })));
  const [paperIds, setPaperIds] = useState(() => currentTask?.focusedPaperIds || activeProject?.paperIds || []);
  const [constraints, setConstraints] = useState(() => currentTask?.constraints || '');
  const [reviewNotes, setReviewNotes] = useState('');
  const [allowExternalSearch, setAllowExternalSearch] = useState(false);
  const [allowWebSearch, setAllowWebSearch] = useState(false);
  const [allowIterativeSearch, setAllowIterativeSearch] = useState(false);
  const extConfig = currentTask?.externalSearchConfig;
  if (currentTask?.status !== 'awaiting_plan_review') return null;
  return (
    <div className="mx-4 mb-4 space-y-3 border-t border-[color:var(--border)] pt-4">
      <div className="agent-title text-xs font-semibold">确认论文范围、约束和研究指令后才会执行</div>
      <div className="flex flex-wrap gap-2">{(activeProject?.paperIds || []).map((paperId) => <label key={paperId} className="agent-card-soft rounded-lg px-2 py-1 text-xs"><input type="checkbox" checked={paperIds.includes(paperId)} onChange={() => setPaperIds((prev) => prev.includes(paperId) ? prev.filter((id) => id !== paperId) : [...prev, paperId])} /> {paperId}</label>)}</div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setAllowExternalSearch((prev) => !prev)}
          className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
            allowExternalSearch ? 'bg-[color:var(--accent)]' : 'bg-[color:var(--border)]'
          }`}
          role="switch"
          aria-checked={allowExternalSearch}
          aria-label="授权外部学术检索"
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
              allowExternalSearch ? 'translate-x-5' : 'translate-x-1'
            }`}
          />
        </button>
        <div>
          <div className="text-xs font-semibold text-[color:var(--foreground)]">授权外部学术检索</div>
          <div className="text-[10px] leading-5 text-[color:var(--muted)]">仅访问白名单学术来源 · 默认关闭</div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setAllowWebSearch((prev) => !prev)}
          className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
            allowWebSearch ? 'bg-[color:var(--accent)]' : 'bg-[color:var(--border)]'
          }`}
          role="switch"
          aria-checked={allowWebSearch}
          aria-label="授权网页搜索"
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
              allowWebSearch ? 'translate-x-5' : 'translate-x-1'
            }`}
          />
        </button>
        <div>
          <div className="text-xs font-semibold text-[color:var(--foreground)]">授权网页搜索</div>
          <div className="text-[10px] leading-5 text-[color:var(--muted)]">Brave + Tavily · 仅授权后启用 · 默认关闭</div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => allowWebSearch && setAllowIterativeSearch((prev) => !prev)}
          className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
            !allowWebSearch ? 'cursor-not-allowed opacity-40 bg-[color:var(--border)]' :
            allowIterativeSearch ? 'bg-[color:var(--accent)]' : 'bg-[color:var(--border)]'
          }`}
          role="switch"
          aria-checked={allowIterativeSearch}
          aria-label="授权迭代搜索"
          disabled={!allowWebSearch}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
              allowIterativeSearch ? 'translate-x-5' : 'translate-x-1'
            }`}
          />
        </button>
        <div>
          <div className="text-xs font-semibold text-[color:var(--foreground)]">授权迭代搜索</div>
          <div className="text-[10px] leading-5 text-[color:var(--muted)]">多轮搜索+抓取+评估 · 仅在网页搜索启用时可用</div>
        </div>
      </div>

      {allowExternalSearch && extConfig?.allowExternalSearch && (
        <div className="agent-card-soft rounded-xl border border-indigo-400/25 px-4 py-3 text-xs leading-6 text-indigo-400">
          <div className="font-semibold">外部学术检索已授权</div>
          <div className="mt-1 opacity-80">
            Provider: {extConfig.provider || '未知'}
            {' · '}Budget: 调用 {extConfig.budget?.callsUsed || 0}/{extConfig.budget?.callLimit || 0} 次
            {' · '}证据 {extConfig.budget?.evidenceUsed || 0}/{extConfig.budget?.evidenceLimit || 0} 条
          </div>
          {extConfig.degradation && <div className="mt-1 text-amber-400">⚠ {extConfig.degradation}</div>}
        </div>
      )}

      {items.map((item, index) => <div key={item.id || index} className="agent-card grid gap-2 rounded-xl p-3"><input value={item.label || ''} onChange={(event) => setItems((prev) => prev.map((value, i) => i === index ? { ...value, label: event.target.value } : value))} className="agent-body rounded-lg bg-transparent px-2 py-1" /><textarea value={item.detail || ''} onChange={(event) => setItems((prev) => prev.map((value, i) => i === index ? { ...value, detail: event.target.value } : value))} className="agent-body rounded-lg bg-transparent px-2 py-1" /><button type="button" className="agent-secondary-button rounded-lg px-2 py-1 text-xs" onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))}>删除</button></div>)}
      <button type="button" className="agent-secondary-button rounded-lg px-3 py-1 text-xs" onClick={() => setItems((prev) => [...prev, { id: `plan-${prev.length + 1}`, label: '', detail: '' }])}>新增计划项</button>
      <textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} className="agent-card agent-body min-h-16 w-full rounded-xl p-3" placeholder="执行约束" />
      <textarea value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} className="agent-card agent-body min-h-16 w-full rounded-xl p-3" placeholder="审查备注（可选）" />
      <button type="button" className="agent-primary-button rounded-xl px-4 py-2 text-xs font-semibold" onClick={() => onReviewPlan?.({ planItems: items.filter((item) => item.label?.trim()), focusedPaperIds: paperIds, constraints, reviewNotes, allowExternalSearch, allowWebSearch, allowIterativeSearch })}>确认计划并执行</button>
    </div>
  );
};

export const AgentTaskPlanSection = ({ currentTask, activeProject, onReviewPlan }) => (
  <details className="agent-section mt-4 rounded-[18px]" open>
    <summary className="agent-title flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
      <span className="flex items-center gap-2">
        <span className="agent-icon-accent inline-flex h-6 w-6 items-center justify-center rounded-lg">
          <Sparkles size={14} />
        </span>
        执行计划
      </span>
      <span className="agent-chip-success px-2.5 py-1 text-[11px] font-semibold">
        {(currentTask?.planItems || []).length} steps
      </span>
    </summary>
    <div className="space-y-2 px-4 pb-4">
      {(currentTask?.planItems || []).map((item, index) => (
        <div
          key={item.id || item.label || index}
          className="agent-card grid grid-cols-[28px_minmax(0,1fr)_auto] items-start gap-3 rounded-2xl px-3 py-3"
        >
          <div className="agent-chip-accent inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold">
            {index + 1}
          </div>
          <div className="min-w-0">
            <div className="agent-title text-xs font-semibold">{item.label || item.question || item.id}</div>
            <div className="agent-muted mt-1 text-[11px] leading-5">{item.detail || '等待执行'}</div>
          </div>
          <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${getStatusTone(item.status)}`}>
            {item.status || 'pending'}
          </span>
        </div>
      ))}
      {(currentTask?.planItems || []).length === 0 && (
        <div className="agent-empty-state rounded-2xl border-dashed px-4 py-4 text-xs leading-6">
          任务开始后，这里会展示 Agent 的结构化计划和当前阶段。
        </div>
      )}
    </div>
    <AgentPlanReviewForm key={currentTask?.taskId} currentTask={currentTask} activeProject={activeProject} onReviewPlan={onReviewPlan} />
  </details>
);

export const AgentHumanFinalReview = ({ currentTask, onReviewFinal }) => {
  const [statuses, setStatuses] = useState({});
  const [reviewNotes, setReviewNotes] = useState('');
  const risks = currentTask?.reviewRisks || [];
  return <section className="agent-section mt-4 rounded-[18px] p-4"><div className="agent-title text-sm font-semibold">终稿人工审查</div><div className="mt-3 space-y-2">{risks.map((risk) => <div key={risk.riskId} className="agent-card rounded-xl p-3"><div className="agent-title text-xs font-semibold">{risk.label}</div><div className="agent-muted mt-1 text-xs">{risk.detail}</div><select className="agent-card-soft mt-2 rounded-lg px-2 py-1 text-xs" value={statuses[risk.riskId] || 'reviewed'} onChange={(event) => setStatuses((prev) => ({ ...prev, [risk.riskId]: event.target.value }))}><option value="reviewed">已核查</option><option value="needs_follow_up">仍需跟进</option></select></div>)}</div><textarea className="agent-card agent-body mt-3 min-h-16 w-full rounded-xl p-3" value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} placeholder="终稿审查备注（可选）" /><button type="button" className="agent-primary-button mt-3 rounded-xl px-4 py-2 text-xs font-semibold" onClick={() => onReviewFinal?.({ reviewNotes, riskReviews: risks.map((risk) => ({ riskId: risk.riskId, reviewStatus: statuses[risk.riskId] || 'reviewed' })) })}>确认终稿</button></section>;
};

export const AgentIntermediateArtifactsSection = ({ activeProject, currentTask }) => (
  <details className="agent-section mt-4 rounded-[18px]" open>
    <summary className="agent-title flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
      <span className="flex items-center gap-2">
        <span className="agent-icon-accent inline-flex h-6 w-6 items-center justify-center rounded-lg">
          <BookOpen size={14} />
        </span>
        中间产物
      </span>
      <span className="agent-chip-accent px-2.5 py-1 text-[11px] font-semibold">
        live snapshot
      </span>
    </summary>
    <div className="grid gap-3 px-4 pb-4 md:grid-cols-3">
      <div className="agent-card rounded-2xl p-3">
        <div className="agent-title text-xs font-semibold">研究目标</div>
        <div className="agent-muted mt-2 text-[11px] leading-5">{activeProject?.goal || '等待项目目标'}</div>
      </div>
      <div className="agent-card rounded-2xl p-3">
        <div className="agent-title text-xs font-semibold">证据覆盖</div>
        <div className="agent-muted mt-2 text-[11px] leading-5">
          已收集 {(currentTask?.evidenceItems || []).length} 条证据，覆盖 {(activeProject?.paperIds || []).length} 篇项目论文。
        </div>
      </div>
      <div className="agent-card rounded-2xl p-3">
        <div className="agent-title text-xs font-semibold">冲突候选</div>
        <div className="agent-muted mt-2 text-[11px] leading-5">
          当前发现 {(currentTask?.conflicts || []).length} 个冲突或置信度风险候选。
        </div>
      </div>
    </div>
  </details>
);

export const AgentComparisonSection = ({ activeProject, currentTask, activePaperId, onCaptureArtifact }) => {
  const columns = currentTask?.comparisonTable?.columns || [];
  const rows = currentTask?.comparisonTable?.rows || [];
  const saveState = getAgentArtifactSaveState({ activePdfId: activePaperId, content: rows });
  const captureComparison = (event) => {
    event.preventDefault();
    event.stopPropagation();
    const artifact = buildAgentComparisonArtifact({
      activePdfId: activePaperId,
      projectId: activeProject?.projectId || currentTask?.projectId,
      taskId: currentTask?.taskId,
      projectTitle: activeProject?.title,
      comparisonTable: currentTask?.comparisonTable,
    });
    if (artifact) onCaptureArtifact?.(artifact);
  };

  return (
    <details className="agent-section mt-4 rounded-[18px]" open>
      <summary className="agent-title flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
        <span className="flex items-center gap-2">
          <span className="agent-icon-accent inline-flex h-6 w-6 items-center justify-center rounded-lg">
            <GitCompare size={14} />
          </span>
          跨论文判断
        </span>
        <span className="flex items-center gap-2">
          <button
            type="button"
            onClick={captureComparison}
            disabled={!saveState.canSave || !onCaptureArtifact}
            title={saveState.reason || '保存完整对比表'}
            className="agent-secondary-button inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Archive size={12} />
            加入工作台
          </button>
          <span className="agent-chip-info px-2.5 py-1 text-[11px] font-semibold">{rows.length} rows</span>
        </span>
      </summary>
      <div className="px-4 pb-4">
        {rows.length > 0 ? (
          <div className="agent-card overflow-x-auto rounded-2xl">
            <table className="w-full min-w-[720px] text-left text-[11px]">
              <thead className="agent-table-head">
                <tr>
                  {columns.map((column) => (
                    <th key={column} className="px-3 py-2 font-bold">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="agent-body">
                {rows.map((row, rowIndex) => (
                  <tr key={`${row?.[0] || 'row'}-${rowIndex}`} className="agent-table-row border-t">
                    {(Array.isArray(row) ? row : []).map((cell, cellIndex) => (
                      <td key={`${rowIndex}-${cellIndex}`} className="max-w-[320px] px-3 py-2 leading-5">
                        {cell || '-'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="agent-empty-state rounded-2xl border-dashed px-4 py-4 text-xs leading-6">
            完成证据检索后，这里会展示按论文聚合的判断表。
          </div>
        )}
      </div>
    </details>
  );
};

export const AgentConflictSection = ({ currentTask, onJumpToSource }) => {
  const conflicts = currentTask?.conflicts || [];

  return (
    <details className="agent-section mt-4 rounded-[18px]" open>
      <summary className="agent-title flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
        <span className="flex items-center gap-2">
          <span className="agent-chip-warning inline-flex h-6 w-6 items-center justify-center rounded-lg">
            <AlertTriangle size={14} />
          </span>
          冲突检测
        </span>
        <span className="agent-chip-warning px-2.5 py-1 text-[11px] font-semibold">
          {conflicts.length} candidates
        </span>
      </summary>
      <div className="space-y-2 px-4 pb-4">
        {conflicts.map((conflict) => (
          <article key={conflict.id || conflict.claim} className="agent-card rounded-2xl px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <div className="agent-title text-xs font-semibold">{conflict.claim || '冲突候选'}</div>
              <span className="agent-chip-warning px-2 py-1 text-[10px] font-semibold">
                {conflict.severity || 'unknown'}
              </span>
            </div>
            <p className="agent-body mt-2 text-[11px] leading-6">{conflict.summary}</p>
            <div className="mt-2 text-[10px] font-semibold text-[color:var(--accent-strong)]">
              {(conflict.papers || []).filter(Boolean).join(' / ') || '未指定论文'}
            </div>
            {conflict.resolutionHint && (
              <div className="agent-card-soft mt-2 rounded-xl px-2.5 py-2 text-[11px] leading-5">
                建议：{conflict.resolutionHint}
              </div>
            )}
            <div className="mt-2">
              <SourceList sources={conflict.sources} onJumpToSource={onJumpToSource} variant="agent" />
            </div>
          </article>
        ))}
        {conflicts.length === 0 && (
          <div className="agent-empty-state rounded-2xl border-dashed px-4 py-4 text-xs leading-6">
            综合阶段会生成冲突候选，包括证据覆盖不均、检索回退和潜在结论风险。
          </div>
        )}
      </div>
    </details>
  );
};

export const AgentCodeExecutionSection = ({ currentTask }) => {
  const results = currentTask?.executePythonResults || [];
  if (!results.length) return null;

  const statusTone = (status) => {
    switch (status) {
      case 'success': return 'text-emerald-500';
      case 'timeout': return 'text-amber-500';
      case 'error': return 'text-red-500';
      case 'forbidden_import': return 'text-red-500';
      default: return 'text-gray-500';
    }
  };

  return (
    <details className="agent-section mt-4 rounded-[18px]" open>
      <summary className="agent-title flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
        <span className="flex items-center gap-2">
          <span className="agent-icon-accent inline-flex h-6 w-6 items-center justify-center rounded-lg">
            <Terminal size={14} />
          </span>
          代码执行结果
        </span>
        <span className="agent-chip-accent px-2.5 py-1 text-[11px] font-semibold">
          {results.length} 次执行
        </span>
      </summary>
      <div className="space-y-2 px-4 pb-4">
        {results.map((result, index) => (
          <div key={result.id || index} className="agent-card rounded-2xl px-3 py-3">
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-[10px] font-semibold uppercase tracking-[0.14em] ${statusTone(result.status)}`}>
                Run {index + 1} · {result.status || 'unknown'}
              </span>
            </div>
            {result.stdout && (
              <pre className="agent-card-soft mt-1 max-h-48 overflow-auto rounded-xl p-3 text-xs leading-5 font-mono whitespace-pre-wrap">
                {result.stdout}
              </pre>
            )}
            {result.stderr && (
              <pre className="mt-1 max-h-32 overflow-auto rounded-xl border border-amber-400/30 bg-amber-50/5 p-3 text-xs leading-5 font-mono whitespace-pre-wrap text-amber-400">
                {result.stderr}
              </pre>
            )}
            {result.error && (
              <div className="mt-1 rounded-xl border border-red-400/30 bg-red-50/5 px-3 py-2 text-xs text-red-400">
                {result.error}
              </div>
            )}
          </div>
        ))}
      </div>
    </details>
  );
};

export const AgentDraftReportSection = ({ activeProject, currentTask, activePaperId, onCaptureArtifact, onJumpToSource }) => {
  const draftReport = `${currentTask?.draftReport || ''}`.trim();
  const draftSections = draftReport
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
  const saveState = getAgentArtifactSaveState({ activePdfId: activePaperId, content: draftReport });
  const captureReport = (event) => {
    event.preventDefault();
    event.stopPropagation();
    const artifact = buildAgentReportArtifact({
      activePdfId: activePaperId,
      projectId: activeProject?.projectId || currentTask?.projectId,
      taskId: currentTask?.taskId,
      projectTitle: activeProject?.title,
      draftReport,
    });
    if (artifact) onCaptureArtifact?.(artifact);
  };

  return (
    <details className="agent-section mt-4 rounded-[18px]" open>
      <summary className="agent-title flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
        <span className="flex items-center gap-2">
          <span className="agent-icon-accent inline-flex h-6 w-6 items-center justify-center rounded-lg">
            <FileText size={14} />
          </span>
          最终结果草稿
        </span>
        <span className="flex items-center gap-2">
          <button
            type="button"
            onClick={captureReport}
            disabled={!saveState.canSave || !onCaptureArtifact}
            title={saveState.reason || '保存完整报告草稿'}
            className="agent-secondary-button inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Archive size={12} />
            加入工作台
          </button>
          <span className="agent-chip-info px-2.5 py-1 text-[11px] font-semibold">
            {draftSections.length || 0} paragraphs
          </span>
        </span>
      </summary>
      <div className="space-y-2 px-4 pb-4">
        {draftSections.length > 0 ? (
          draftSections.map((line, index) => (
            <div key={`${line}-${index}`} className="agent-card whitespace-pre-wrap rounded-2xl px-3 py-2.5 text-xs leading-6">
              {line}
            </div>
          ))
        ) : (
          <div className="agent-empty-state rounded-2xl border-dashed px-4 py-4 text-xs leading-6">
            这里会显示当前 Agent 任务输出的完整结构化草稿，不再截断前几段。
          </div>
        )}
        <div className="agent-card-soft rounded-2xl px-3 py-3">
          <div className="agent-title mb-2 text-[11px] font-semibold">报告引用</div>
          <SourceList
            sources={currentTask?.reportSources}
            onJumpToSource={onJumpToSource}
            emptyText="当前报告没有可关联的结构化来源。"
            variant="agent"
          />
        </div>
      </div>
    </details>
  );
};
