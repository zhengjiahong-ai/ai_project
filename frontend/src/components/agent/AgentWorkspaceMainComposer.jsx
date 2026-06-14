import React from 'react';
import { RefreshCw, Send } from 'lucide-react';

import { QUICK_PROMPTS } from './agentWorkspaceUi.js';

export const AgentWorkspaceHeader = ({
  activeProject,
  currentTask,
  currentStageLabel,
  projectTaskCount = 0,
  onRefresh,
}) => (
  <div className="flex items-center justify-between border-b border-[#eee7f5] px-5 py-3">
    <div>
      <div className="text-sm font-semibold text-slate-900">Pixiu Research Agent</div>
      <div className="mt-1 text-[11px] text-slate-500">
        {activeProject?.title || '等待项目'} · {currentStageLabel} · {projectTaskCount} 条研究记录
      </div>
    </div>
    <div className="flex items-center gap-2">
      <span className="rounded-full border border-[#dcc8f6] bg-[#f6efff] px-2.5 py-1 text-[11px] font-semibold text-[#6b36d9]">
        {currentTask?.traceId ? '可追踪' : '原型阶段'}
      </span>
      <button
        type="button"
        onClick={onRefresh}
        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-[#d7c7ef] hover:text-[#5b2ea6]"
      >
        <RefreshCw size={14} />
        刷新
      </button>
    </div>
  </div>
);

export const AgentResponseCard = ({ currentTask, currentStageLabel, children }) => (
  <div className="rounded-[24px] border border-[#e6dff1] bg-white shadow-[0_10px_28px_rgba(50,24,85,0.05)]">
    <div className="flex items-center justify-between gap-4 border-b border-[#efe8f7] px-4 py-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-xl bg-[linear-gradient(135deg,#5b2ea6,#7d57e6)] text-white">
          A
        </span>
        Pixiu Research Agent
      </div>
      <div className="text-[11px] text-slate-500">
        {currentTask?.status || 'idle'} · {currentStageLabel}
      </div>
    </div>

    <div className="px-4 py-4">
      <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700">
        {currentTask?.findings?.[0]?.summary ||
          currentTask?.draftReport ||
          '任务启动后，Agent 会把计划、工具调用、证据片段和阶段结论持续汇总在这里。'}
      </p>
      {children}
    </div>
  </div>
);

const AgentTaskComposer = ({ activeProject, prompt, onPromptChange, onQuickPrompt, onCreateTask }) => (
  <div className="border-t border-[#eee7f5] bg-white/90 px-5 py-4 backdrop-blur">
    <div className="mb-3 flex flex-wrap gap-2">
      {QUICK_PROMPTS.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onQuickPrompt(item)}
          className="rounded-full border border-[#e5def0] bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-600 transition hover:border-[#d5c2f2] hover:bg-[#fbf8ff] hover:text-[#5b2ea6]"
        >
          {item}
        </button>
      ))}
    </div>
    <div className="grid gap-3 rounded-[22px] border border-[#e6deef] bg-white p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_10px_28px_rgba(84,42,140,0.06)] md:grid-cols-[1fr_150px_48px]">
      <textarea
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        className="min-h-[74px] w-full resize-none bg-transparent text-sm leading-7 text-slate-700 outline-none"
        placeholder="让 Agent 比较这些论文的研究问题、方法设计、实验指标与局限性，并返回可追踪证据。"
      />
      <div className="flex items-end">
        <div className="w-full rounded-2xl border border-[#e6deef] bg-[#fbf9ff] px-3 py-2 text-xs leading-6 text-[#5b2ea6]">
          <div className="font-semibold">当前模式</div>
          <div>多论文研究</div>
          <div className="text-slate-500">{(activeProject?.paperIds || []).length || 0} papers</div>
        </div>
      </div>
      <button
        type="button"
        onClick={onCreateTask}
        disabled={!activeProject?.projectId || !prompt.trim()}
        className="inline-flex h-12 w-12 items-center justify-center self-end rounded-2xl bg-[linear-gradient(135deg,#5b2ea6,#7d57e6)] text-white shadow-[0_10px_24px_rgba(91,46,166,0.24)] transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-50"
        title="启动 Agent 任务"
      >
        <Send size={16} />
      </button>
    </div>
  </div>
);

export default AgentTaskComposer;
