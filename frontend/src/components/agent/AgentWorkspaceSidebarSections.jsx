import React from 'react';
import { FileText, X } from 'lucide-react';

import { formatRelativeMeta, getStatusLabel, getStatusTone } from './agentWorkspaceUi.js';

export const AgentProjectHeroCard = ({ activeProject, currentTask }) => (
  <section className="agent-hero-card rounded-[20px] p-4">
    <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[color:var(--accent-strong)]">Research Project</div>
    <h2 className="agent-title text-base font-semibold leading-6">
      {activeProject?.title || 'Agent 学术研究工作台'}
    </h2>
    <p className="agent-body mt-2 line-clamp-4 text-xs leading-6">
      {activeProject?.goal || '创建项目后，这里会展示项目目标、论文规模和最新任务状态。'}
    </p>
    <div className="mt-3 flex flex-wrap gap-2">
      <span className="agent-chip-accent px-2.5 py-1 text-[11px] font-semibold">
        {(activeProject?.paperIds || []).length} 篇论文
      </span>
      <span className="agent-chip-success px-2.5 py-1 text-[11px] font-semibold">
        链路已接通
      </span>
      <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${getStatusTone(currentTask?.status)}`}>
        {getStatusLabel(currentTask?.status || 'pending')}
      </span>
    </div>
  </section>
);

const AgentProjectListItem = ({ project, isActive, taskCount, onSelect, onDelete }) => (
  <div className="relative">
    <button
      type="button"
      onClick={() => onSelect(project)}
      className={`w-full rounded-[18px] border p-3 pr-9 text-left transition ${
        isActive
          ? 'agent-card'
          : 'agent-card-soft hover:border-[color:var(--accent)]'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="agent-icon-accent mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
          <FileText size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="agent-title truncate text-[13px] font-semibold">{project.title}</div>
          <div className="agent-muted mt-1 line-clamp-2 text-[11px] leading-5">
            {project.goal || '未填写项目目标'}
          </div>
          <div className="agent-muted mt-2 flex items-center justify-between gap-2 text-[11px]">
            <span className="truncate">{formatRelativeMeta(project)}</span>
            <span className="agent-chip-accent shrink-0 px-2 py-0.5 font-semibold">
              {taskCount} 轮
            </span>
          </div>
        </div>
      </div>
    </button>
    <button
      type="button"
      onClick={() => onDelete(project)}
      className="agent-secondary-button absolute right-2 top-2 inline-flex h-6 w-6 items-center justify-center rounded-lg"
      title={`删除 ${project.title}`}
      aria-label={`删除 ${project.title}`}
    >
      <X size={13} />
    </button>
  </div>
);

export const AgentProjectListSection = ({
  projectOptions,
  activeProjectId,
  taskCountsByProjectId = {},
  onSelectProject,
  onDeleteProject,
}) => (
  <>
    <div className="agent-section-label mt-5 flex items-center justify-between text-[11px]">
      <span>Projects</span>
      <span>{projectOptions.length} items</span>
    </div>

    <div className="mt-3 space-y-2">
      {projectOptions.map((project) => (
        <AgentProjectListItem
          key={project.projectId}
          project={project}
          isActive={project.projectId === activeProjectId}
          taskCount={taskCountsByProjectId[project.projectId] || 0}
          onSelect={onSelectProject}
          onDelete={onDeleteProject}
        />
      ))}
      {projectOptions.length === 0 && (
        <div className="agent-empty-state rounded-[18px] border-dashed px-4 py-5 text-xs leading-6">
          还没有 Agent 项目。你可以在下面填写标题、目标和论文 ID，先创建一个研究项目。
        </div>
      )}
    </div>
  </>
);

export const AgentProjectCreateForm = ({
  projectTitle,
  projectGoal,
  selectedPaperIds,
  onProjectTitleChange,
  onProjectGoalChange,
  onSelectedPaperIdsChange,
}) => (
  <>
    <div className="agent-section-label mt-5 flex items-center justify-between text-[11px]">
      <span>Create</span>
      <span>Draft</span>
    </div>

    <div className="mt-3 space-y-2">
      <input
        value={projectTitle}
        onChange={(event) => onProjectTitleChange(event.target.value)}
        className="agent-input w-full rounded-2xl px-3 py-2.5 text-xs outline-none transition"
        placeholder="项目标题"
      />
      <textarea
        value={projectGoal}
        onChange={(event) => onProjectGoalChange(event.target.value)}
        className="agent-input min-h-[82px] w-full rounded-2xl px-3 py-2.5 text-xs outline-none transition"
        placeholder="项目目标"
      />
      <textarea
        value={selectedPaperIds}
        onChange={(event) => onSelectedPaperIdsChange(event.target.value)}
        className="agent-input min-h-[82px] w-full rounded-2xl px-3 py-2.5 text-xs outline-none transition"
        placeholder="论文 ID，支持逗号、空格或换行分隔"
      />
    </div>
  </>
);
