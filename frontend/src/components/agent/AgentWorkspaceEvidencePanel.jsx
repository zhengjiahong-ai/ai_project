import React from 'react';
import { ChevronLeft, ChevronRight, Square, Wrench } from 'lucide-react';

import {
  AgentEvidenceListSection,
  AgentTaskSummaryCard,
  AgentToolTraceSection,
} from './AgentWorkspaceEvidenceSections.jsx';

const AgentWorkspaceRightRail = ({ onExpand }) => (
  <button
    type="button"
    onClick={onExpand}
    className="flex h-full w-12 flex-col items-center justify-between rounded-[24px] border border-[#ddcfee] bg-white/90 py-4 text-[#5b2ea6] shadow-[0_10px_30px_rgba(70,36,120,0.08)]"
    title="展开工具侧栏"
  >
    <ChevronLeft size={18} />
    <span className="rotate-180 text-[11px] font-bold tracking-[0.3em]" style={{ writingMode: 'vertical-rl' }}>
      TOOLS
    </span>
    <Wrench size={18} />
  </button>
);

const AgentWorkspaceEvidencePanel = ({
  activeProject,
  currentTask,
  activePaperId,
  stateError,
  onCancelTask,
  onCollapse,
}) => (
  <aside className="min-h-0 min-w-0 overflow-hidden rounded-[24px] border border-[#e6deef] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(251,249,255,0.96))] shadow-[0_16px_40px_rgba(49,24,82,0.08)]">
    <div className="flex items-center justify-between border-b border-[#eee7f5] px-4 py-3">
      <div>
        <div className="text-sm font-semibold text-slate-900">Tools & Evidence</div>
        <div className="text-[11px] text-slate-500">调用记录与可追踪证据</div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCancelTask}
          className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-[11px] font-semibold text-slate-600 transition hover:border-[#dcc8f6] hover:text-[#5b2ea6]"
        >
          <Square size={12} />
          取消
        </button>
        <button
          type="button"
          onClick={onCollapse}
          className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500"
          title="收起侧栏"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>

    <div className="h-[calc(100%-61px)] overflow-y-auto px-4 py-4">
      <AgentToolTraceSection currentTask={currentTask} />
      <AgentEvidenceListSection currentTask={currentTask} />
      <AgentTaskSummaryCard activeProject={activeProject} currentTask={currentTask} activePaperId={activePaperId} />

      {stateError && (
        <div className="mt-4 rounded-[18px] border border-rose-200 bg-rose-50 px-4 py-3 text-xs leading-6 text-rose-700">
          {stateError}
        </div>
      )}
    </div>
  </aside>
);

export default AgentWorkspaceEvidencePanel;
export { AgentWorkspaceRightRail };
