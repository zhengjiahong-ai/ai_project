import React from 'react';
import { RefreshCw, Send } from 'lucide-react';

import { QUICK_PROMPTS } from './agentWorkspaceUi.js';

export const AgentWorkspaceHeader = ({
  activeProject,
  currentTask,
  currentStageLabel,
  projectTaskCount = 0,
  onRefresh,
  extraActions,
}) => (
  <div className="agent-header flex items-center justify-between border-b px-5 py-3">
    <div>
      <div className="agent-title text-sm font-semibold">Pixiu Research Agent</div>
      <div className="agent-muted mt-1 text-[11px]">
        {activeProject?.title || '等待项目'} · {currentStageLabel} · {projectTaskCount} 条研究记录
      </div>
    </div>
    <div className="flex items-center gap-2">
      <span className="agent-chip-accent px-2.5 py-1 text-[11px] font-semibold">
        {currentTask?.traceId ? '可追踪' : '原型阶段'}
      </span>
      {extraActions}
      <button
        type="button"
        onClick={onRefresh}
        className="agent-secondary-button inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition"
      >
        <RefreshCw size={14} />
        刷新
      </button>
    </div>
  </div>
);

export const AgentResponseCard = ({ currentTask, currentStageLabel, children }) => (
  <div className="agent-card rounded-[24px]">
    <div className="agent-header flex items-center justify-between gap-4 border-b px-4 py-3">
      <div className="agent-title flex items-center gap-2 text-xs font-semibold">
        <span className="agent-primary-button inline-flex h-7 w-7 items-center justify-center rounded-xl">
          A
        </span>
        Pixiu Research Agent
      </div>
      <div className="agent-muted text-[11px]">
        {currentTask?.status || 'idle'} · {currentStageLabel}
      </div>
    </div>

    <div className="px-4 py-4">
      <p className="agent-body whitespace-pre-wrap text-sm leading-7">
        {currentTask?.findings?.[0]?.summary ||
          currentTask?.draftReport ||
          '任务启动后，Agent 会把计划、工具调用、证据片段和阶段结论持续汇总在这里。'}
      </p>
      {children}
    </div>
  </div>
);

const DOMAIN_OPTIONS = [
  { value: '', label: '通用 (无领域特化)' },
  { value: 'cs', label: '计算机科学' },
  { value: 'medical', label: '医学' },
  { value: 'bio', label: '生物学' },
  { value: 'physics', label: '物理学' },
  { value: 'econ', label: '经济学' },
];

const AgentTaskComposer = ({ activeProject, prompt, onPromptChange, onQuickPrompt, onCreateTask, allowExternalSearch = false, onAllowExternalSearchChange, allowWebSearch = false, onAllowWebSearchChange, allowIterativeSearch = false, onAllowIterativeSearchChange, allowKnowledgeGraph = true, onAllowKnowledgeGraphChange, domain = '', onDomainChange }) => (
  <div className="agent-composer border-t px-5 py-4 backdrop-blur">
    <div className="mb-3 flex flex-wrap gap-2">
      {QUICK_PROMPTS.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onQuickPrompt(item)}
          className="agent-secondary-button rounded-full px-3 py-1.5 text-[11px] font-semibold transition"
        >
          {item}
        </button>
      ))}
    </div>
    <div className="agent-card grid gap-3 rounded-[22px] p-3 md:grid-cols-[1fr_150px_48px]">
      <textarea
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        className="agent-body min-h-[74px] w-full resize-none bg-transparent text-sm leading-7 outline-none"
        aria-label="创建研究任务"
        placeholder="让 Agent 比较这些论文的研究问题、方法设计、实验指标与局限性，并返回可追踪证据。"
      />
      <div className="flex flex-col gap-2">
        <div className="agent-card-soft w-full rounded-2xl px-3 py-2 text-xs leading-6">
          <div className="font-semibold">当前模式</div>
          <div>多论文研究</div>
          <div className="agent-muted">{(activeProject?.paperIds || []).length || 0} papers</div>
        </div>
        {onDomainChange && (
          <select
            className="agent-card-soft w-full rounded-xl px-3 py-2 text-xs outline-none"
            value={domain}
            onChange={(e) => onDomainChange(e.target.value)}
            title="选择研究领域以获得领域特化的工具和搜索策略"
          >
            {DOMAIN_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        )}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onAllowExternalSearchChange?.(!allowExternalSearch)}
            className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
              allowExternalSearch ? 'bg-[color:var(--accent)]' : 'bg-[color:var(--border)]'
            }`}
            role="switch"
            aria-checked={allowExternalSearch}
            aria-label="授权外部学术检索"
            title="授权外部学术检索 · 仅白名单来源"
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
                allowExternalSearch ? 'translate-x-5' : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-[10px] leading-4 text-[color:var(--muted)]">外部检索</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onAllowWebSearchChange?.(!allowWebSearch)}
            className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
              allowWebSearch ? 'bg-[color:var(--accent)]' : 'bg-[color:var(--border)]'
            }`}
            role="switch"
            aria-checked={allowWebSearch}
            aria-label="授权网页搜索"
            title="授权网页搜索 · Brave + Tavily · 默认关闭"
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
                allowWebSearch ? 'translate-x-5' : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-[10px] leading-4 text-[color:var(--muted)]">网页搜索</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => allowWebSearch && onAllowIterativeSearchChange?.(!allowIterativeSearch)}
            className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
              !allowWebSearch ? 'cursor-not-allowed opacity-40 bg-[color:var(--border)]' :
              allowIterativeSearch ? 'bg-[color:var(--accent)]' : 'bg-[color:var(--border)]'
            }`}
            role="switch"
            aria-checked={allowIterativeSearch}
            aria-label="授权迭代搜索"
            title={allowWebSearch ? "多轮搜索+抓取+评估 · 仅在网页搜索启用时可用" : "需要先启用网页搜索"}
            disabled={!allowWebSearch}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
                allowIterativeSearch ? 'translate-x-5' : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-[10px] leading-4 text-[color:var(--muted)]">迭代搜索</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onAllowKnowledgeGraphChange?.(!allowKnowledgeGraph)}
            className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
              allowKnowledgeGraph ? 'bg-[color:var(--accent)]' : 'bg-[color:var(--border)]'
            }`}
            role="switch"
            aria-checked={allowKnowledgeGraph}
            aria-label="使用知识图谱补充证据"
            title="使用知识图谱补充证据 · 来自本地已解析论文 · 默认开启"
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
                allowKnowledgeGraph ? 'translate-x-5' : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-[10px] leading-4 text-[color:var(--muted)]">图谱补充</span>
        </div>
      </div>
      <button
        type="button"
        onClick={onCreateTask}
        disabled={!activeProject?.projectId || !prompt.trim()}
        className="agent-primary-button inline-flex h-12 w-12 items-center justify-center self-end rounded-2xl transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-50"
        title="启动 Agent 任务"
      >
        <Send size={16} />
      </button>
    </div>
  </div>
);

export default AgentTaskComposer;
