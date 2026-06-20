import React, { useEffect, useMemo, useRef, useState } from 'react';

import { apiService } from '../../services/api';
import AgentWorkspaceEvidencePanel, { AgentWorkspaceRightRail } from './AgentWorkspaceEvidencePanel.jsx';
import AgentWorkspaceMain from './AgentWorkspaceMain.jsx';
import AgentWorkspaceSidebar, { AgentWorkspaceLeftRail } from './AgentWorkspaceSidebar.jsx';
import {
  addSelectedAgentPaperId,
  buildAgentProjectPayload,
  appendAgentTaskForProject,
  createEmptyAgentWorkspaceState,
  getProjectTasks,
  normalizeAgentProject,
  normalizeAgentProjectListResponse,
  normalizeAgentProjectResponse,
  normalizeAgentTask,
  normalizeAgentTaskListResponse,
  normalizeAgentTaskResponse,
  removeAgentProjectFromState,
  removeSelectedAgentPaperId,
  resolveInitialAgentPaperSelection,
  resolveNextAgentProjectNumber,
} from './agentWorkspaceModel.js';
import { loadAgentWorkspaceSnapshot, saveAgentWorkspaceSnapshot } from './agentWorkspaceStore.js';
import { PAUSED_AGENT_STATUSES, STAGE_LABELS, TERMINAL_AGENT_STATUSES } from './agentWorkspaceUi.js';

const AGENT_TASK_POLL_INTERVAL_MS = 1200;

const createTimestamp = () => new Date().toISOString();

const upsertProject = (projects, project) => [
  project,
  ...(projects || []).filter((item) => item.projectId !== project.projectId),
];

const updateProject = (projects, projectId, patch) =>
  (projects || []).map((item) => (item.projectId === projectId ? { ...item, ...patch } : item));

const replaceProjectTasks = (tasksByProjectId, projectId, tasks = []) => ({
  ...(tasksByProjectId || {}),
  [projectId]: [...tasks].sort((a, b) => {
    const left = new Date(a.updatedAt || a.createdAt || 0).getTime();
    const right = new Date(b.updatedAt || b.createdAt || 0).getTime();
    return right - left;
  }),
});

const resolveInitialState = () => {
  const snapshot = loadAgentWorkspaceSnapshot();
  const projects = (snapshot?.projects || []).map(normalizeAgentProject);
  const tasksByProjectId = Object.fromEntries(
    Object.entries(snapshot?.tasksByProjectId || {}).map(([projectId, tasks]) => [
      projectId,
      (Array.isArray(tasks) ? tasks : []).map(normalizeAgentTask).filter((task) => task.taskId),
    ]),
  );
  return {
    ...createEmptyAgentWorkspaceState(),
    ...(snapshot || {}),
    projects,
    activeProject: snapshot?.activeProject ? normalizeAgentProject(snapshot.activeProject) : null,
    latestTask: snapshot?.latestTask ? normalizeAgentTask(snapshot.latestTask) : null,
    currentTask: snapshot?.currentTask ? normalizeAgentTask(snapshot.currentTask) : null,
    tasksByProjectId,
    nextProjectNumber: resolveNextAgentProjectNumber(projects, snapshot?.nextProjectNumber),
  };
};

const AgentWorkspace = ({ paperLibrary = [], activePaperId = '', onCaptureArtifact, onJumpToSource }) => {
  const [state, setState] = useState(resolveInitialState);
  const initialWorkspaceStateRef = useRef(state);
  const [projectTitle, setProjectTitle] = useState('');
  const [projectGoal, setProjectGoal] = useState('');
  const [selectedPaperIds, setSelectedPaperIds] = useState(() =>
    resolveInitialAgentPaperSelection(paperLibrary, activePaperId),
  );
  const [prompt, setPrompt] = useState('');
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const activeProject = state.activeProject;
  const projectTasks = useMemo(
    () => getProjectTasks(state.tasksByProjectId, state.activeProjectId),
    [state.tasksByProjectId, state.activeProjectId],
  );
  const currentTask = state.currentTask || projectTasks[0] || null;

  useEffect(() => {
    saveAgentWorkspaceSnapshot({
      projects: state.projects,
      activeProjectId: state.activeProjectId,
      activeProject: state.activeProject,
      latestTask: state.latestTask,
      currentTask: state.currentTask,
      tasksByProjectId: state.tasksByProjectId,
      nextProjectNumber: state.nextProjectNumber,
    });
  }, [state]);

  useEffect(() => {
    const validPaperIds = new Set((paperLibrary || []).map((paper) => `${paper?.id ?? ''}`.trim()).filter(Boolean));
    setSelectedPaperIds((prev) => {
      const retainedPaperIds = (prev || []).filter((paperId) => validPaperIds.has(paperId));
      return retainedPaperIds.length ? retainedPaperIds : resolveInitialAgentPaperSelection(paperLibrary, activePaperId);
    });
  }, [paperLibrary, activePaperId]);

  const cacheTask = (task, makeCurrent = true) => {
    if (!task?.taskId || !task?.projectId) return;

    setState((prev) => {
      const taskProjectPatch = {
        latestTaskId: task.taskId,
        updatedAt: task.updatedAt || createTimestamp(),
      };
      const nextProjects = updateProject(prev.projects, task.projectId, taskProjectPatch);
      const nextActiveProject =
        prev.activeProject?.projectId === task.projectId
          ? { ...prev.activeProject, ...taskProjectPatch }
          : prev.activeProject;

      return {
        ...prev,
        projects: nextProjects,
        activeProject: nextActiveProject,
        latestTask: task,
        currentTask: makeCurrent || prev.currentTask?.taskId === task.taskId ? task : prev.currentTask,
        tasksByProjectId: appendAgentTaskForProject(prev.tasksByProjectId, task),
      };
    });
  };

  const loadProjectTaskHistory = async (projectId, preferredTaskId = '') => {
    if (!projectId) return [];

    const response = await apiService.listAgentProjectTasks(projectId, 20);
    const normalized = normalizeAgentTaskListResponse(response);
    const tasks = normalized.tasks;

    setState((prev) => {
      const previousCurrentTaskId = preferredTaskId || prev.currentTask?.taskId || '';
      const selectedTask = tasks.find((task) => task.taskId === previousCurrentTaskId) || tasks[0] || null;
      const latestTaskPatch = tasks[0]
        ? {
            latestTaskId: tasks[0].taskId,
            updatedAt: tasks[0].updatedAt || createTimestamp(),
          }
        : {};
      const nextProjects = Object.keys(latestTaskPatch).length
        ? updateProject(prev.projects, projectId, latestTaskPatch)
        : prev.projects;
      const nextActiveProject =
        prev.activeProject?.projectId === projectId && Object.keys(latestTaskPatch).length
          ? { ...prev.activeProject, ...latestTaskPatch }
          : prev.activeProject;

      return {
        ...prev,
        projects: nextProjects,
        activeProject: nextActiveProject,
        currentTask: prev.activeProjectId === projectId ? selectedTask : prev.currentTask,
        latestTask: selectedTask || prev.latestTask,
        tasksByProjectId: replaceProjectTasks(prev.tasksByProjectId, projectId, tasks),
        error: '',
      };
    });

    return tasks;
  };

  useEffect(() => {
    let cancelled = false;

    const loadProjects = async () => {
      setState((prev) => ({ ...prev, loading: true, error: '' }));
      try {
        const response = await apiService.listAgentProjects();
        if (cancelled) return;

        const normalized = normalizeAgentProjectListResponse(response);
        const initialWorkspaceState = initialWorkspaceStateRef.current;
        const previousProjectId = initialWorkspaceState.activeProjectId;
        const nextProjectId = previousProjectId || normalized.projects[0]?.projectId || '';
        const nextProject =
          normalized.projects.find((item) => item.projectId === nextProjectId) || normalized.projects[0] || null;
        const cachedTasks = getProjectTasks(initialWorkspaceState.tasksByProjectId, nextProject?.projectId);

        setState((prev) => ({
          ...prev,
          loading: false,
          projects: normalized.projects,
          nextProjectNumber: resolveNextAgentProjectNumber(normalized.projects, prev.nextProjectNumber),
          activeProjectId: nextProject?.projectId || '',
          activeProject: nextProject,
          currentTask: cachedTasks[0] || null,
          latestTask: cachedTasks[0] || prev.latestTask,
          error: '',
        }));

        if (nextProject?.projectId) {
          try {
            await loadProjectTaskHistory(nextProject.projectId, cachedTasks[0]?.taskId || '');
          } catch {
            // Keep the local snapshot as a fallback when the project task-history endpoint is unavailable.
          }
        }
      } catch (error) {
        if (cancelled) return;
        setState((prev) => ({
          ...prev,
          loading: false,
          error: error?.response?.data?.message || error?.message || '加载 Agent 项目失败',
        }));
      }
    };

    loadProjects();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const projectId = state.activeProjectId;
    if (!projectId) return undefined;

    let cancelled = false;

    const loadProjectDetail = async () => {
      try {
        const response = await apiService.getAgentProject(projectId);
        if (cancelled) return;

        const project = normalizeAgentProjectResponse(response).project;
        setState((prev) => ({
          ...prev,
          activeProject: project,
          projects: upsertProject(prev.projects, project),
          error: '',
        }));

        try {
          await loadProjectTaskHistory(project.projectId);
          return;
        } catch {
          // Fall back to the pre-P1-13 latest-task path for older backends or offline snapshots.
        }

        if (!project.latestTaskId) {
          setState((prev) => ({
            ...prev,
            currentTask: getProjectTasks(prev.tasksByProjectId, project.projectId)[0] || null,
          }));
          return;
        }

        const taskResponse = await apiService.getAgentTask(project.latestTaskId);
        if (cancelled) return;
        cacheTask(normalizeAgentTaskResponse(taskResponse).task, true);
      } catch (error) {
        if (cancelled || error?.response?.status === 404) return;
        setState((prev) => ({
          ...prev,
          error: error?.response?.data?.message || error?.message || '加载 Agent 项目详情失败',
        }));
      }
    };

    loadProjectDetail();
    return () => {
      cancelled = true;
    };
  }, [state.activeProjectId]);

  useEffect(() => {
    const taskId = currentTask?.taskId;
    if (!taskId || TERMINAL_AGENT_STATUSES.has(currentTask?.status) || PAUSED_AGENT_STATUSES.has(currentTask?.status)) return undefined;

    let stopped = false;

    const pollTask = async () => {
      try {
        const response = await apiService.getAgentTask(taskId);
        if (stopped) return;
        cacheTask(normalizeAgentTaskResponse(response).task, true);
      } catch (error) {
        if (stopped || error?.response?.status === 404) return;
        setState((prev) => ({
          ...prev,
          error: error?.response?.data?.message || error?.message || '轮询 Agent 任务失败',
        }));
      }
    };

    const intervalId = setInterval(pollTask, AGENT_TASK_POLL_INTERVAL_MS);
    pollTask();

    return () => {
      stopped = true;
      clearInterval(intervalId);
    };
  }, [currentTask?.taskId, currentTask?.status]);

  const projectOptions = useMemo(() => state.projects, [state.projects]);
  const taskCountsByProjectId = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(state.tasksByProjectId || {}).map(([projectId, tasks]) => [projectId, tasks.length]),
      ),
    [state.tasksByProjectId],
  );
  const currentStageLabel = STAGE_LABELS[currentTask?.stage] || '等待中';

  const handleCreateProject = async () => {
    const payload = buildAgentProjectPayload({
      projectTitle,
      fallbackTitle: `Agent 项目 ${state.nextProjectNumber}`,
      projectGoal,
      selectedPaperIds,
    });

    try {
      const response = await apiService.createAgentProject(payload);
      const project = normalizeAgentProjectResponse(response).project;
      setState((prev) => ({
        ...prev,
        projects: upsertProject(prev.projects, project),
        nextProjectNumber: resolveNextAgentProjectNumber(
          upsertProject(prev.projects, project),
          Number(prev.nextProjectNumber || 1) + 1,
        ),
        activeProjectId: project.projectId,
        activeProject: project,
        currentTask: null,
        error: '',
      }));
      setProjectTitle('');
      setProjectGoal('');
      setSelectedPaperIds(resolveInitialAgentPaperSelection(paperLibrary, activePaperId));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error?.response?.data?.message || error?.message || '创建 Agent 项目失败',
      }));
    }
  };

  const handleDeleteProject = async (project) => {
    const normalizedProject = normalizeAgentProject(project);
    if (!normalizedProject.projectId) return;
    const confirmed = window.confirm(`确定删除项目“${normalizedProject.title}”吗？此操作会删除该项目的任务历史。`);
    if (!confirmed) return;

    try {
      await apiService.deleteAgentProject(normalizedProject.projectId);
      setState((prev) => ({
        ...removeAgentProjectFromState(prev, normalizedProject.projectId),
        error: '',
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error?.response?.data?.message || error?.message || '删除 Agent 项目失败',
      }));
    }
  };

  const handleCreateTask = async () => {
    const nextPrompt = prompt.trim();
    if (!activeProject?.projectId || !nextPrompt) return;

    try {
      const response = await apiService.createAgentTask(activeProject.projectId, {
        prompt: nextPrompt,
        focusedPaperIds: activeProject.paperIds,
        constraints: activeProject.defaultConstraints || '',
        context: {
          activePaperId,
        },
      });
      const task = normalizeAgentTaskResponse(response).task;
      cacheTask(task, true);
      setPrompt('');
      setState((prev) => ({ ...prev, error: '' }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error?.response?.data?.message || error?.message || '创建 Agent 任务失败',
      }));
    }
  };

  const handleRefresh = async () => {
    if (!state.activeProjectId) return;

    try {
      const projectResponse = await apiService.getAgentProject(state.activeProjectId);
      const project = normalizeAgentProjectResponse(projectResponse).project;
      setState((prev) => ({
        ...prev,
        activeProject: project,
        projects: upsertProject(prev.projects, project),
          error: '',
        }));

      try {
        await loadProjectTaskHistory(project.projectId, currentTask?.taskId || '');
        return;
      } catch {
        // Older Java/Python runtimes may not expose the task-history endpoint yet.
      }

      if (currentTask?.taskId) {
        const taskResponse = await apiService.getAgentTask(currentTask.taskId);
        cacheTask(normalizeAgentTaskResponse(taskResponse).task, true);
      } else if (project.latestTaskId) {
        const taskResponse = await apiService.getAgentTask(project.latestTaskId);
        cacheTask(normalizeAgentTaskResponse(taskResponse).task, true);
      }
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error?.response?.data?.message || error?.message || '刷新 Agent 项目失败',
      }));
    }
  };

  const handleCancelTask = async () => {
    if (!currentTask?.taskId) return;

    try {
      const response = await apiService.cancelAgentTask(currentTask.taskId);
      cacheTask(normalizeAgentTaskResponse(response).task, true);
      setState((prev) => ({ ...prev, error: '' }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error?.response?.data?.message || error?.message || '取消 Agent 任务失败',
      }));
    }
  };

  const handleQuickPrompt = (label) => {
    const base = activeProject?.paperIds?.length
      ? `请围绕当前项目中的论文执行“${label}”，输出可追踪证据、阶段结论和下一步研究建议。`
      : `请帮我执行“${label}”，并说明还需要补充哪些论文或上下文。`;
    setPrompt(base);
  };

  const handleSelectProject = (project) => {
    const normalizedProject = normalizeAgentProject(project);
    setState((prev) => {
      const nextTasks = getProjectTasks(prev.tasksByProjectId, normalizedProject.projectId);
      return {
        ...prev,
        activeProjectId: normalizedProject.projectId,
        activeProject: normalizedProject,
        currentTask: nextTasks[0] || null,
        latestTask: nextTasks[0] || prev.latestTask,
        error: '',
      };
    });
  };

  const handleSelectTask = (task) => {
    setState((prev) => ({
      ...prev,
      currentTask: task,
      latestTask: task,
    }));
  };

  const handleReviewPlan = async (payload) => {
    if (!currentTask?.taskId) return;
    try {
      const response = await apiService.reviewAgentPlan(currentTask.taskId, payload);
      cacheTask(normalizeAgentTaskResponse(response).task, true);
      setState((prev) => ({ ...prev, error: '' }));
    } catch (error) {
      setState((prev) => ({ ...prev, error: error?.response?.data?.message || error?.message || 'Agent 计划确认失败' }));
    }
  };

  const handleReviewFinal = async (payload) => {
    if (!currentTask?.taskId) return;
    try {
      const response = await apiService.reviewAgentFinal(currentTask.taskId, payload);
      cacheTask(normalizeAgentTaskResponse(response).task, true);
      setState((prev) => ({ ...prev, error: '' }));
    } catch (error) {
      setState((prev) => ({ ...prev, error: error?.response?.data?.message || error?.message || 'Agent 终稿确认失败' }));
    }
  };

  const handleAddSelectedPaper = (paperId) => {
    setSelectedPaperIds((prev) => addSelectedAgentPaperId(prev, paperId));
  };

  const handleRemoveSelectedPaper = (paperId) => {
    setSelectedPaperIds((prev) => removeSelectedAgentPaperId(prev, paperId));
  };

  return (
    <div className="agent-shell flex h-full min-h-0 min-w-0 flex-1 overflow-hidden p-3">
      <div
        className="grid h-full min-h-0 min-w-0 flex-1 gap-3 overflow-hidden"
        style={{
          gridTemplateColumns: `${leftCollapsed ? '48px' : '300px'} minmax(0,1fr) ${rightCollapsed ? '48px' : '360px'}`,
        }}
      >
        {leftCollapsed ? (
          <AgentWorkspaceLeftRail onExpand={() => setLeftCollapsed(false)} />
        ) : (
          <AgentWorkspaceSidebar
            activeProject={activeProject}
            currentTask={currentTask}
            projectOptions={projectOptions}
            activeProjectId={state.activeProjectId}
            taskCountsByProjectId={taskCountsByProjectId}
            projectTitle={projectTitle}
            projectGoal={projectGoal}
            selectedPaperIds={selectedPaperIds}
            paperLibrary={paperLibrary}
            onProjectTitleChange={setProjectTitle}
            onProjectGoalChange={setProjectGoal}
            onAddSelectedPaper={handleAddSelectedPaper}
            onRemoveSelectedPaper={handleRemoveSelectedPaper}
            onCreateProject={handleCreateProject}
            onSelectProject={handleSelectProject}
            onDeleteProject={handleDeleteProject}
            onCollapse={() => setLeftCollapsed(true)}
          />
        )}

        <AgentWorkspaceMain
          activeProject={activeProject}
          currentTask={currentTask}
          projectTasks={projectTasks}
          currentStageLabel={currentStageLabel}
          prompt={prompt}
          onPromptChange={setPrompt}
          onQuickPrompt={handleQuickPrompt}
          onCreateTask={handleCreateTask}
          onRefresh={handleRefresh}
          onSelectTask={handleSelectTask}
          onReviewPlan={handleReviewPlan}
          onReviewFinal={handleReviewFinal}
          activePaperId={activePaperId}
          onCaptureArtifact={onCaptureArtifact}
          onJumpToSource={onJumpToSource}
        />

        {rightCollapsed ? (
          <AgentWorkspaceRightRail onExpand={() => setRightCollapsed(false)} />
        ) : (
          <AgentWorkspaceEvidencePanel
            activeProject={activeProject}
            currentTask={currentTask}
            activePaperId={activePaperId}
            stateError={state.error}
            onCancelTask={handleCancelTask}
            onCaptureArtifact={onCaptureArtifact}
            onJumpToSource={onJumpToSource}
            onCollapse={() => setRightCollapsed(true)}
          />
        )}
      </div>
    </div>
  );
};

export default AgentWorkspace;
