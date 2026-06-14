import React from 'react';
import { BookOpen, ChevronLeft, ChevronRight, Plus } from 'lucide-react';

import {
  AgentProjectCreateForm,
  AgentProjectHeroCard,
  AgentProjectListSection,
} from './AgentWorkspaceSidebarSections.jsx';

export const AgentWorkspaceLeftRail = ({ onExpand }) => (
  <button
    type="button"
    onClick={onExpand}
    className="flex h-full w-12 flex-col items-center justify-between rounded-[24px] border border-[#ddcfee] bg-white/90 py-4 text-[#5b2ea6] shadow-[0_10px_30px_rgba(70,36,120,0.08)]"
    title="展开项目侧栏"
  >
    <ChevronRight size={18} />
    <span className="rotate-180 text-[11px] font-bold tracking-[0.3em]" style={{ writingMode: 'vertical-rl' }}>
      PROJECT
    </span>
    <BookOpen size={18} />
  </button>
);

const AgentWorkspaceSidebar = ({
  activeProject,
  currentTask,
  projectOptions,
  activeProjectId,
  taskCountsByProjectId,
  projectTitle,
  projectGoal,
  selectedPaperIds,
  onProjectTitleChange,
  onProjectGoalChange,
  onSelectedPaperIdsChange,
  onCreateProject,
  onSelectProject,
  onCollapse,
}) => (
  <aside className="min-h-0 min-w-0 overflow-hidden rounded-[24px] border border-[#e6deef] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(251,249,255,0.96))] shadow-[0_16px_40px_rgba(49,24,82,0.08)]">
    <div className="flex items-center justify-between border-b border-[#eee7f5] px-4 py-3">
      <div>
        <div className="text-sm font-semibold text-slate-900">Project / Papers</div>
        <div className="text-[11px] text-slate-500">多论文研究工作区</div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCreateProject}
          className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-[#d9c8ef] bg-[#f6efff] text-[#6b36d9]"
          title="创建项目"
        >
          <Plus size={14} />
        </button>
        <button
          type="button"
          onClick={onCollapse}
          className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500"
          title="收起侧栏"
        >
          <ChevronLeft size={14} />
        </button>
      </div>
    </div>

    <div className="h-[calc(100%-61px)] overflow-y-auto px-4 py-4">
      <AgentProjectHeroCard activeProject={activeProject} currentTask={currentTask} />

      <AgentProjectListSection
        projectOptions={projectOptions}
        activeProjectId={activeProjectId}
        taskCountsByProjectId={taskCountsByProjectId}
        onSelectProject={onSelectProject}
      />

      <AgentProjectCreateForm
        projectTitle={projectTitle}
        projectGoal={projectGoal}
        selectedPaperIds={selectedPaperIds}
        onProjectTitleChange={onProjectTitleChange}
        onProjectGoalChange={onProjectGoalChange}
        onSelectedPaperIdsChange={onSelectedPaperIdsChange}
      />
    </div>
  </aside>
);

export default AgentWorkspaceSidebar;
