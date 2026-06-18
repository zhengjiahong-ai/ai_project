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
    className="agent-rail flex h-full w-12 flex-col items-center justify-between rounded-[24px] py-4"
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
  onCaptureArtifact,
  onCollapse,
}) => (
  <aside className="agent-panel min-h-0 min-w-0 overflow-hidden rounded-[24px]">
    <div className="agent-header flex items-center justify-between border-b px-4 py-3">
      <div>
        <div className="agent-title text-sm font-semibold">Tools & Evidence</div>
        <div className="agent-muted text-[11px]">调用记录与可追踪证据</div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCancelTask}
          className="agent-secondary-button inline-flex items-center gap-1 rounded-xl px-2.5 py-2 text-[11px] font-semibold transition"
        >
          <Square size={12} />
          取消
        </button>
        <button
          type="button"
          onClick={onCollapse}
          className="agent-secondary-button inline-flex h-8 w-8 items-center justify-center rounded-xl"
          title="收起侧栏"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>

    <div className="h-[calc(100%-61px)] overflow-y-auto px-4 py-4">
      <AgentToolTraceSection currentTask={currentTask} />
      <AgentEvidenceListSection
        activeProject={activeProject}
        currentTask={currentTask}
        activePaperId={activePaperId}
        onCaptureArtifact={onCaptureArtifact}
      />
      <AgentTaskSummaryCard activeProject={activeProject} currentTask={currentTask} activePaperId={activePaperId} />

      {stateError && (
        <div className="agent-chip-danger mt-4 rounded-[18px] px-4 py-3 text-xs leading-6">
          {stateError}
        </div>
      )}
    </div>
  </aside>
);

export default AgentWorkspaceEvidencePanel;
export { AgentWorkspaceRightRail };
