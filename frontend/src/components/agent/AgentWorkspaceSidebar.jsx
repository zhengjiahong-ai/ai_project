import React, { useMemo, useState } from 'react';
import { BookOpen, ChevronLeft, ChevronRight, FileText, Folder, Plus, Trash2, X } from 'lucide-react';
import { AgentProjectCreateForm } from './AgentWorkspaceSidebarSections.jsx';
import { formatAgentTime, getStatusLabel, getStatusTone } from './agentWorkspaceUi.js';

export const AgentWorkspaceLeftRail = ({ onExpand }) => (
  <button type="button" onClick={onExpand} className="agent-rail flex h-full w-12 flex-col items-center gap-5 border-r py-5" title="展开项目侧栏">
    <ChevronRight size={18} /><Folder size={18} />
  </button>
);

const AgentWorkspaceSidebar = ({
  activeProject, currentTask, projectTasks, activeResearchTaskId, projectOptions, activeProjectId,
  projectTitle, projectGoal, selectedPaperIds, paperLibrary, onProjectTitleChange,
  onProjectGoalChange, onAddSelectedPaper, onRemoveSelectedPaper, onCreateProject,
  onSelectProject, onSelectTask, onStartNewTask, onDeleteProject, onCollapse,
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const paperById = useMemo(() => new Map((paperLibrary || []).map((paper) => [`${paper?.id ?? ''}`, paper])), [paperLibrary]);
  const projectPapers = (activeProject?.paperIds || []).map((id) => paperById.get(`${id}`) || { id, title: id });
  const submitProject = async () => {
    await onCreateProject?.();
    setIsCreating(false);
  };

  return (
    <aside className="agent-panel min-h-0 min-w-0 overflow-hidden border-r">
      <div className="workspace-side-title agent-header flex h-16 items-center justify-between border-b px-5">
        <h2 className="agent-title text-base font-bold">项目</h2>
        <button type="button" onClick={onCollapse} className="pixiu-icon-action" title="收起侧栏"><ChevronLeft size={16} /></button>
      </div>

      <div className="h-[calc(100%-64px)] overflow-y-auto px-4 py-4">
        <button type="button" onClick={() => setIsCreating(true)} className="agent-primary-button mb-4 flex h-10 w-full items-center justify-center gap-2 rounded-md text-sm font-semibold">
          <Plus size={16} />新建项目
        </button>

        <div className="space-y-1">
          {projectOptions.map((project) => {
            const active = project.projectId === activeProjectId;
            return (
              <div key={project.projectId}>
                <div className={`agent-tree-row group ${active ? 'agent-tree-row-active' : ''}`}>
                  <button type="button" onClick={() => onSelectProject(project)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                    <Folder size={16} className="shrink-0" /><span className="truncate text-sm font-semibold">{project.title}</span>
                  </button>
                  <button type="button" onClick={() => onDeleteProject(project)} className="agent-muted invisible p-1 group-hover:visible" aria-label={`删除 ${project.title}`}><Trash2 size={13} /></button>
                </div>
                {active && (
                  <div className="ml-5 border-l pl-2">
                    <button type="button" onClick={onStartNewTask} className={'agent-task-tree-row ' + (!activeResearchTaskId ? 'agent-task-tree-row-active' : '')}>
                      <Plus size={12} /><span className="min-w-0 flex-1 truncate text-left">新研究任务</span>
                    </button>
                    {(projectTasks || []).map((task) => (
                      <button key={task.taskId} type="button" onClick={() => onSelectTask?.(task)} className={'agent-task-tree-row ' + (task.taskId === activeResearchTaskId ? 'agent-task-tree-row-active' : '')}>
                        <span className="min-w-0 flex-1 truncate">{task.title || '未命名研究任务'}</span>
                        <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] ${getStatusTone(task.status)}`}>{getStatusLabel(task.status)}</span>
                      </button>
                    ))}
                    {!projectTasks?.length && <div className="px-2 py-2 text-[11px] text-[color:var(--text-muted)]">暂无任务</div>}
                  </div>
                )}
              </div>
            );
          })}
          {!projectOptions.length && <div className="agent-empty-state px-3 py-5 text-center text-xs">暂无研究项目</div>}
        </div>

        <div className="theme-border mt-5 border-t pt-4">
          <div className="mb-2 flex items-center justify-between">
            <div><div className="agent-title text-sm font-bold">当前项目</div><div className="agent-muted mt-0.5 max-w-[220px] truncate text-[11px]">{activeProject?.title || '尚未选择项目'}</div></div>
            <span className="agent-muted text-[11px]">{projectPapers.length} 篇</span>
          </div>
          <div className="agent-title mb-2 flex items-center gap-2 text-xs font-semibold"><BookOpen size={14} />组成论文（{projectPapers.length}）</div>
          <div className="space-y-0.5">
            {projectPapers.map((paper, index) => (
              <div key={paper.id} className="agent-paper-row"><FileText size={14} /><span className="min-w-0 flex-1 truncate">{paper.title || paper.filename || paper.id}</span><span>{index + 1}</span></div>
            ))}
            {!projectPapers.length && <div className="agent-muted py-3 text-center text-[11px]">当前项目未添加论文</div>}
          </div>
          {currentTask && <div className="agent-muted mt-3 text-[10px]">当前任务更新于 {formatAgentTime(currentTask.updatedAt || currentTask.createdAt)}</div>}
        </div>
      </div>

      {isCreating && (
        <div className="agent-project-dialog absolute inset-0 z-20 flex flex-col bg-[color:var(--panel-bg)]">
          <div className="workspace-side-title flex h-16 items-center justify-between border-b px-5"><h2 className="text-base font-bold">新建项目</h2><button type="button" onClick={() => setIsCreating(false)} className="pixiu-icon-action"><X size={16} /></button></div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4"><AgentProjectCreateForm projectTitle={projectTitle} projectGoal={projectGoal} selectedPaperIds={selectedPaperIds} paperLibrary={paperLibrary} onProjectTitleChange={onProjectTitleChange} onProjectGoalChange={onProjectGoalChange} onAddSelectedPaper={onAddSelectedPaper} onRemoveSelectedPaper={onRemoveSelectedPaper} /></div>
          <div className="border-t p-4"><button type="button" onClick={submitProject} className="agent-primary-button h-10 w-full rounded-md text-sm font-semibold">创建项目</button></div>
        </div>
      )}
    </aside>
  );
};

export default AgentWorkspaceSidebar;
