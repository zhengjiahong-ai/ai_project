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
    className="agent-rail flex h-full w-12 flex-col items-center justify-between rounded-[24px] py-4"
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
  onDeleteProject,
  onCollapse,
}) => (
  <aside className="agent-panel min-h-0 min-w-0 overflow-hidden rounded-[24px]">
    <div className="agent-header flex items-center justify-between border-b px-4 py-3">
      <div>
        <div className="agent-title text-sm font-semibold">Project / Papers</div>
        <div className="agent-muted text-[11px]">多论文研究工作区</div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCreateProject}
          className="agent-secondary-button agent-icon-accent inline-flex h-8 w-8 items-center justify-center rounded-xl"
          title="创建项目"
        >
          <Plus size={14} />
        </button>
        <button
          type="button"
          onClick={onCollapse}
          className="agent-secondary-button inline-flex h-8 w-8 items-center justify-center rounded-xl"
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
        onDeleteProject={onDeleteProject}
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
