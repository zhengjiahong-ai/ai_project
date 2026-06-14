import React, { useEffect, useMemo, useState } from 'react';

import { apiService } from '../../services/api';
import AgentWorkspaceEvidencePanel, { AgentWorkspaceRightRail } from './AgentWorkspaceEvidencePanel.jsx';
import AgentWorkspaceMain from './AgentWorkspaceMain.jsx';
import AgentWorkspaceSidebar, { AgentWorkspaceLeftRail } from './AgentWorkspaceSidebar.jsx';
import {
  appendAgentTaskForProject,
  createEmptyAgentWorkspaceState,
  getProjectTasks,
  normalizeAgentProject,
  normalizeAgentProjectListResponse,
  normalizeAgentProjectResponse,
  normalizeAgentTaskResponse,
} from './agentWorkspaceModel.js';
import { loadAgentWorkspaceSnapshot, saveAgentWorkspaceSnapshot } from './agentWorkspaceStore.js';
import { STAGE_LABELS, TERMINAL_AGENT_STATUSES } from './agentWorkspaceUi.js';

const AGENT_TASK_POLL_INTERVAL_MS = 1200;

const createTimestamp = () => new Date().toISOString();

const upsertProject = (projects, project) => [
  project,
  ...(projects || []).filter((item) => item.projectId !== project.projectId),
];

const updateProject = (projects, projectId, patch) =>
  (projects || []).map((item) => (item.projectId === projectId ? { ...item, ...patch } : item));

const resolveInitialState = () => {
  const snapshot = loadAgentWorkspaceSnapshot();
  return {
    ...createEmptyAgentWorkspaceState(),
    ...(snapshot || {}),
    tasksByProjectId: snapshot?.tasksByProjectId || {},
  };
};

const AgentWorkspace = ({ initialPaperIds = [], activePaperId = '' }) => {
  const [state, setState] = useState(resolveInitialState);
  const [projectTitle, setProjectTitle] = useState('');
  const [projectGoal, setProjectGoal] = useState('');
  const [selectedPaperIds, setSelectedPaperIds] = useState(initialPaperIds.join(', '));
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
    });
  }, [state]);

  useEffect(() => {
    setSelectedPaperIds((prev) => prev || initialPaperIds.join(', '));
  }, [initialPaperIds]);

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

  useEffect(() => {
    let cancelled = false;

    const loadProjects = async () => {
      setState((prev) => ({ ...prev, loading: true, error: '' }));
      try {
        const response = await apiService.listAgentProjects();
        if (cancelled) return;

        const normalized = normalizeAgentProjectListResponse(response);
        const previousProjectId = state.activeProjectId;
        const nextProjectId = previousProjectId || normalized.projects[0]?.projectId || '';
        const nextProject =
          normalized.projects.find((item) => item.projectId === nextProjectId) || normalized.projects[0] || null;
        const cachedTasks = getProjectTasks(state.tasksByProjectId, nextProject?.projectId);

        setState((prev) => ({
          ...prev,
          loading: false,
          projects: normalized.projects,
          activeProjectId: nextProject?.projectId || '',
          activeProject: nextProject,
          currentTask: cachedTasks[0] || null,
          latestTask: cachedTasks[0] || prev.latestTask,
          error: '',
        }));
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
    if (!taskId || TERMINAL_AGENT_STATUSES.has(currentTask?.status)) return undefined;

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
    const paperIds = selectedPaperIds
      .split(/[\n,\s，；]+/)
      .map((item) => item.trim())
      .filter(Boolean);

    const payload = {
      title: projectTitle || `Agent 项目 ${projectOptions.length + 1}`,
      goal: projectGoal,
      paperIds,
    };

    try {
      const response = await apiService.createAgentProject(payload);
      const project = normalizeAgentProjectResponse(response).project;
      setState((prev) => ({
        ...prev,
        projects: upsertProject(prev.projects, project),
        activeProjectId: project.projectId,
        activeProject: project,
        currentTask: null,
        error: '',
      }));
      setProjectTitle('');
      setProjectGoal('');
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error?.response?.data?.message || error?.message || '创建 Agent 项目失败',
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

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 overflow-hidden bg-[radial-gradient(circle_at_18%_-10%,rgba(109,61,242,0.12),transparent_34%),linear-gradient(180deg,#fbfaff,#f5f1fa)] p-3">
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
            onProjectTitleChange={setProjectTitle}
            onProjectGoalChange={setProjectGoal}
            onSelectedPaperIdsChange={setSelectedPaperIds}
            onCreateProject={handleCreateProject}
            onSelectProject={handleSelectProject}
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
            onCollapse={() => setRightCollapsed(true)}
          />
        )}
      </div>
    </div>
  );
};

export default AgentWorkspace;
