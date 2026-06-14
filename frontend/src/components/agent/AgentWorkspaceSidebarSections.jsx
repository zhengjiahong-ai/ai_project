import React from 'react';
import { FileText } from 'lucide-react';

import { formatRelativeMeta, getStatusLabel, getStatusTone } from './agentWorkspaceUi.js';

export const AgentProjectHeroCard = ({ activeProject, currentTask }) => (
  <section className="rounded-[20px] border border-[#ded1ef] bg-[radial-gradient(circle_at_92%_12%,rgba(249,115,22,0.12),transparent_52px),linear-gradient(135deg,#ffffff,#f8f2ff)] p-4 shadow-[0_10px_20px_rgba(84,43,140,0.05)]">
    <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#6b36d9]">Research Project</div>
    <h2 className="text-base font-semibold leading-6 text-slate-900">
      {activeProject?.title || 'Agent 学术研究工作台'}
    </h2>
    <p className="mt-2 line-clamp-4 text-xs leading-6 text-slate-600">
      {activeProject?.goal || '创建项目后，这里会展示项目目标、论文规模和最新任务状态。'}
    </p>
    <div className="mt-3 flex flex-wrap gap-2">
      <span className="rounded-full border border-[#dcc8f6] bg-[#f5eeff] px-2.5 py-1 text-[11px] font-semibold text-[#6b36d9]">
        {(activeProject?.paperIds || []).length} 篇论文
      </span>
      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
        链路已接通
      </span>
      <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${getStatusTone(currentTask?.status)}`}>
        {getStatusLabel(currentTask?.status || 'pending')}
      </span>
    </div>
  </section>
);

const AgentProjectListItem = ({ project, isActive, taskCount, onSelect }) => (
  <button
    type="button"
    onClick={() => onSelect(project)}
    className={`w-full rounded-[18px] border p-3 text-left transition ${
      isActive
        ? 'border-[#d4c0f0] bg-[#fbf8ff] shadow-[0_10px_24px_rgba(96,52,170,0.08)]'
        : 'border-[#ece5f3] bg-white hover:border-[#dbc8f2] hover:bg-[#fcf9ff]'
    }`}
  >
    <div className="flex items-start gap-3">
      <div className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#f2eaff] text-[#6b36d9]">
        <FileText size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold text-slate-900">{project.title}</div>
        <div className="mt-1 line-clamp-2 text-[11px] leading-5 text-slate-500">
          {project.goal || '未填写项目目标'}
        </div>
        <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-slate-400">
          <span className="truncate">{formatRelativeMeta(project)}</span>
          <span className="shrink-0 rounded-full bg-[#f5eeff] px-2 py-0.5 font-semibold text-[#6b36d9]">
            {taskCount} 轮
          </span>
        </div>
      </div>
    </div>
  </button>
);

export const AgentProjectListSection = ({ projectOptions, activeProjectId, taskCountsByProjectId = {}, onSelectProject }) => (
  <>
    <div className="mt-5 flex items-center justify-between text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
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
        />
      ))}
      {projectOptions.length === 0 && (
        <div className="rounded-[18px] border border-dashed border-[#dacfed] bg-white/70 px-4 py-5 text-xs leading-6 text-slate-500">
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
    <div className="mt-5 flex items-center justify-between text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
      <span>Create</span>
      <span>Draft</span>
    </div>

    <div className="mt-3 space-y-2">
      <input
        value={projectTitle}
        onChange={(event) => onProjectTitleChange(event.target.value)}
        className="w-full rounded-2xl border border-[#dfd6ea] bg-white px-3 py-2.5 text-xs text-slate-700 outline-none transition focus:border-[#cbb4f0] focus:ring-2 focus:ring-[#efe6ff]"
        placeholder="项目标题"
      />
      <textarea
        value={projectGoal}
        onChange={(event) => onProjectGoalChange(event.target.value)}
        className="min-h-[82px] w-full rounded-2xl border border-[#dfd6ea] bg-white px-3 py-2.5 text-xs text-slate-700 outline-none transition focus:border-[#cbb4f0] focus:ring-2 focus:ring-[#efe6ff]"
        placeholder="项目目标"
      />
      <textarea
        value={selectedPaperIds}
        onChange={(event) => onSelectedPaperIdsChange(event.target.value)}
        className="min-h-[82px] w-full rounded-2xl border border-[#dfd6ea] bg-white px-3 py-2.5 text-xs text-slate-700 outline-none transition focus:border-[#cbb4f0] focus:ring-2 focus:ring-[#efe6ff]"
        placeholder="论文 ID，支持逗号、空格或换行分隔"
      />
    </div>
  </>
);
