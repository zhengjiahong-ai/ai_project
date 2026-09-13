import React from 'react';
import { MoreHorizontal, RefreshCw, RotateCcw, Send, Settings2, Square } from 'lucide-react';
import { QUICK_PROMPTS } from './agentWorkspaceUi.js';
import { getStatusLabel } from './agentWorkspaceUi.js';

export const AgentWorkspaceHeader = ({ activeProject, currentTask, currentStageLabel, projectTaskCount = 0, onRefresh, onCancelTask, onRetryTask, extraActions }) => (
  <div className="agent-header flex h-16 items-center justify-between border-b px-6">
    <div className="min-w-0">
      <div className="agent-title truncate text-base font-bold">
        {activeProject?.title || '等待项目'} <span className="agent-muted px-1 font-normal">/</span> {currentTask?.prompt || '新研究任务'}
      </div>
      <div className="agent-muted mt-0.5 text-[11px]">{currentStageLabel} · {projectTaskCount} 个任务</div>
    </div>
    <div className="flex items-center gap-2">
      <span className="agent-chip-accent px-2.5 py-1 text-[11px] font-semibold">{currentTask?.traceId ? '可追踪' : '原型阶段'}</span>
      {extraActions}
      {currentTask && ['failed', 'cancelled'].includes(currentTask.status) && (
        <button type="button" onClick={onRetryTask} className="agent-secondary-button inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-semibold"><RotateCcw size={12} />重试</button>
      )}
      {currentTask && !['done', 'completed', 'succeeded', 'failed', 'cancelled'].includes(currentTask.status) && (
        <button type="button" onClick={onCancelTask} className="agent-secondary-button inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-semibold"><Square size={12} />停止</button>
      )}
      <button type="button" onClick={onRefresh} className="agent-secondary-button inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-semibold"><RefreshCw size={14} />刷新</button>
      <button type="button" className="pixiu-icon-action" title="更多"><MoreHorizontal size={16} /></button>
    </div>
  </div>
);

export const AgentResponseCard = ({ currentTask, currentStageLabel, children }) => (
  <article className="agent-response-message">
    <div className="mb-2 flex items-center justify-between gap-3">
      <div className="agent-title flex items-center gap-2 text-xs font-semibold"><span className="agent-avatar">貔</span>Pixiu Academic Assistant</div>
      <span className="agent-muted text-[11px]"><span>{getStatusLabel(currentTask?.status || 'idle')}</span><span> · {currentStageLabel}</span></span>
    </div>
    <div className="agent-card rounded-md px-5 py-4">
      <p className="agent-body whitespace-pre-wrap text-sm leading-7">{currentTask?.draftReport || currentTask?.findings?.[0]?.summary || '任务启动后，Agent 会在这里汇总研究计划、证据和阶段结论。'}</p>
      {children}
    </div>
  </article>
);

const DOMAIN_OPTIONS = [
  { value: '', label: '通用' }, { value: 'cs', label: '计算机科学' }, { value: 'medical', label: '医学' },
  { value: 'bio', label: '生物学' }, { value: 'physics', label: '物理学' }, { value: 'econ', label: '经济学' },
];

const Toggle = ({ label, checked, onChange, disabled = false }) => (
  <label className={`flex items-center gap-2 text-[11px] ${disabled ? 'opacity-40' : ''}`}>
    <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange?.(event.target.checked)} className="accent-[color:var(--accent-strong)]" />{label}
  </label>
);

const AgentTaskComposer = ({ activeProject, prompt, onPromptChange, onQuickPrompt, onCreateTask, allowExternalSearch = false, onAllowExternalSearchChange, allowWebSearch = false, onAllowWebSearchChange, allowIterativeSearch = false, onAllowIterativeSearchChange, allowKnowledgeGraph = true, onAllowKnowledgeGraphChange, domain = '', onDomainChange }) => (
  <div className="agent-composer border-t px-5 py-3">
    <div className="mx-auto max-w-[1120px]">
      <div className="mb-2 flex gap-2 overflow-x-auto">
        {QUICK_PROMPTS.map((item) => <button key={item} type="button" onClick={() => onQuickPrompt(item)} className="agent-secondary-button shrink-0 rounded-full px-3 py-1 text-[11px] font-semibold">{item}</button>)}
      </div>
      <div className="agent-card flex items-end gap-3 rounded-lg p-3">
        <textarea value={prompt} onChange={(event) => onPromptChange(event.target.value)} className="agent-body max-h-32 min-h-[52px] flex-1 resize-none bg-transparent text-sm leading-6 outline-none" aria-label="创建研究任务" placeholder="继续当前项目，或提出新的研究问题…" />
        <details className="relative self-center">
          <summary className="pixiu-icon-action cursor-pointer list-none" title="研究设置"><Settings2 size={17} /></summary>
          <div className="agent-settings-popover agent-card absolute bottom-11 right-0 z-30 w-64 rounded-lg p-4">
            <div className="mb-3 flex items-center justify-between"><span className="text-xs font-bold">研究设置</span><span className="agent-muted text-[10px]">{(activeProject?.paperIds || []).length} 篇论文</span></div>
            <select className="agent-input mb-3 w-full rounded-md px-2 py-2 text-xs" value={domain} onChange={(event) => onDomainChange?.(event.target.value)}>{DOMAIN_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
            <div className="grid grid-cols-2 gap-3"><Toggle label="外部检索" checked={allowExternalSearch} onChange={onAllowExternalSearchChange} /><Toggle label="网页搜索" checked={allowWebSearch} onChange={onAllowWebSearchChange} /><Toggle label="迭代搜索" checked={allowIterativeSearch} disabled={!allowWebSearch} onChange={onAllowIterativeSearchChange} /><Toggle label="图谱补充" checked={allowKnowledgeGraph} onChange={onAllowKnowledgeGraphChange} /></div>
          </div>
        </details>
        <button type="button" onClick={onCreateTask} disabled={!activeProject?.projectId || !prompt.trim()} className="agent-primary-button inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-40" title="启动 Agent 任务"><Send size={16} /></button>
      </div>
    </div>
  </div>
);

export default AgentTaskComposer;
