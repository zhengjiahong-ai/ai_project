import React, { useEffect, useMemo, useRef, useState } from 'react';

import { apiService } from '../../services/api';
import AgentWorkspaceEvidencePanel, { AgentWorkspaceRightRail } from './AgentWorkspaceEvidencePanel.jsx';
import AgentWorkspaceMain from './AgentWorkspaceMain.jsx';
import AgentWorkspaceSidebar, { AgentWorkspaceLeftRail } from './AgentWorkspaceSidebar.jsx';
import {
  addSelectedAgentPaperId,
  buildAgentProjectPayload,
  buildAgentPlanReviewPayload,
  appendAgentTaskForProject,
  buildTaskFromRunWorkspace,
  createEmptyAgentWorkspaceState,
  getProjectTasks,
  normalizeAgentProject,
  normalizeAgentProjectListResponse,
  normalizeAgentProjectResponse,
  normalizeAgentTask,
  normalizeAgentTaskListResponse,
  normalizeAgentTaskResponse,
  normalizeAgentWorkspaceResponse,
  removeAgentProjectFromState,
  removeSelectedAgentPaperId,
  resolveInitialAgentPaperSelection,
  resolveNextAgentProjectNumber,
  type AgentProject,
  type AgentTask,
  type AgentWorkspaceState,
} from './agentWorkspaceModel.ts';
import { loadAgentWorkspaceSnapshot, saveAgentWorkspaceSnapshot } from './agentWorkspaceStore.js';
import { PAUSED_AGENT_STATUSES, STAGE_LABELS, TERMINAL_AGENT_STATUSES } from './agentWorkspaceUi.js';

// ── Types ──────────────────────────────────────────────────────────────────

interface AgentWorkspaceProps {
  paperLibrary?: PaperLibraryItem[];
  activePaperId?: string;
  onCaptureArtifact?: (payload: Record<string, unknown>) => void;
  onJumpToSource?: (source: Record<string, unknown>) => void;
}

interface PaperLibraryItem {
  id?: string;
  [key: string]: unknown;
}

// ── Constants ──────────────────────────────────────────────────────────────

const AGENT_TASK_POLL_INTERVAL_MS: number = 1200;

const createTimestamp = (): string => new Date().toISOString();

const upsertProject = (projects: AgentProject[], project: AgentProject): AgentProject[] => [
  project,
  ...(projects || []).filter((item: AgentProject) => item.projectId !== project.projectId),
];

const updateProject = (
  projects: AgentProject[],
  projectId: string,
  patch: Partial<AgentProject>,
): AgentProject[] =>
  (projects || []).map((item: AgentProject) =>
    item.projectId === projectId ? { ...item, ...patch } : item,
  );

const replaceProjectTasks = (
  tasksByProjectId: Record<string, AgentTask[]>,
  projectId: string,
  tasks: AgentTask[] = [],
): Record<string, AgentTask[]> => ({
  ...(tasksByProjectId || {}),
  [projectId]: [...tasks].sort((a: AgentTask, b: AgentTask) => {
    const left: number = new Date(a.updatedAt || a.createdAt || 0).getTime();
    const right: number = new Date(b.updatedAt || b.createdAt || 0).getTime();
    return right - left;
  }),
});

const resolveInitialState = (): AgentWorkspaceState => {
  const snapshot = loadAgentWorkspaceSnapshot();
  const projects: AgentProject[] = (snapshot?.projects || []).map(normalizeAgentProject);
  const tasksByProjectId: Record<string, AgentTask[]> = Object.fromEntries(
    Object.entries(snapshot?.tasksByProjectId || {}).map(([projectId, tasks]: [string, unknown]) => [
      projectId,
      (Array.isArray(tasks) ? tasks : []).map((t: unknown) => normalizeAgentTask(t) as AgentTask).filter((task: AgentTask) => task.taskId),
    ]),
  ) as Record<string, AgentTask[]>;
  return {
    ...createEmptyAgentWorkspaceState(),
    ...(snapshot || {}),
    projects,
    activeProject: snapshot?.activeProject ? normalizeAgentProject(snapshot.activeProject) : null,
    activeWorkspace: snapshot?.activeWorkspace ?? null,
    latestTask: snapshot?.latestTask ? normalizeAgentTask(snapshot.latestTask) : null,
    currentTask: snapshot?.currentTask ? normalizeAgentTask(snapshot.currentTask) : null,
    tasksByProjectId,
    nextProjectNumber: resolveNextAgentProjectNumber(projects, snapshot?.nextProjectNumber),
  } as AgentWorkspaceState;
};

// ── Component ──────────────────────────────────────────────────────────────

const AgentWorkspace: React.FC<AgentWorkspaceProps> = ({
  paperLibrary = [],
  activePaperId = '',
  onCaptureArtifact,
  onJumpToSource,
}) => {
  const [state, setState] = useState<AgentWorkspaceState>(resolveInitialState);
  const initialWorkspaceStateRef = useRef<AgentWorkspaceState>(state);
  const [projectTitle, setProjectTitle] = useState<string>('');
  const [projectGoal, setProjectGoal] = useState<string>('');
  const [selectedPaperIds, setSelectedPaperIds] = useState<string[]>(() =>
    resolveInitialAgentPaperSelection(paperLibrary, activePaperId) as string[],
  );
  const [prompt, setPrompt] = useState<string>('');
  const [allowExternalSearch, setAllowExternalSearch] = useState<boolean>(false);
  const [allowWebSearch, setAllowWebSearch] = useState<boolean>(false);
  const [domain, setDomain] = useState<string>('');
  const [allowIterativeSearch, setAllowIterativeSearch] = useState<boolean>(false);
  const [leftCollapsed, setLeftCollapsed] = useState<boolean>(false);
  const [rightCollapsed, setRightCollapsed] = useState<boolean>(false);

  const activeProject: AgentProject | null = state.activeProject;
  const projectTasks: AgentTask[] = useMemo(
    () => getProjectTasks(state.tasksByProjectId, state.activeProjectId),
    [state.tasksByProjectId, state.activeProjectId],
  );
  const currentTask: AgentTask | null = state.currentTask || projectTasks[0] || null;

  useEffect(() => {
    saveAgentWorkspaceSnapshot({
      projects: state.projects,
      activeProjectId: state.activeProjectId,
      activeProject: state.activeProject,
      activeWorkspace: state.activeWorkspace,
      latestTask: state.latestTask,
      currentTask: state.currentTask,
      tasksByProjectId: state.tasksByProjectId,
      nextProjectNumber: state.nextProjectNumber,
    });
  }, [state]);

  useEffect(() => {
    const validPaperIds: Set<string> = new Set(
      (paperLibrary || []).map((paper: PaperLibraryItem) => `${paper?.id ?? ''}`.trim()).filter(Boolean),
    );
    setSelectedPaperIds((prev: string[]) => {
      const retainedPaperIds: string[] = (prev || []).filter((paperId: string) => validPaperIds.has(paperId));
      return retainedPaperIds.length ? retainedPaperIds : resolveInitialAgentPaperSelection(paperLibrary, activePaperId);
    });
  }, [paperLibrary, activePaperId]);

  const cacheTask = (task: AgentTask, makeCurrent: boolean = true): void => {
    if (!task?.taskId || !task?.projectId) return;

    setState((prev: AgentWorkspaceState) => {
      const taskProjectPatch: Partial<AgentProject> = {
        latestTaskId: task.taskId,
        updatedAt: task.updatedAt || createTimestamp(),
      };
      const nextProjects: AgentProject[] = updateProject(prev.projects, task.projectId, taskProjectPatch);
      const nextActiveProject: AgentProject | null =
        prev.activeProject?.projectId === task.projectId
          ? { ...prev.activeProject, ...taskProjectPatch }
          : prev.activeProject;

      return {
        ...prev,
        projects: nextProjects,
        activeProject: nextActiveProject,
        latestTask: task,
        currentTask: makeCurrent || prev.currentTask?.taskId === task.taskId ? task : prev.currentTask,
        tasksByProjectId: appendAgentTaskForProject(prev.tasksByProjectId, task) as Record<string, AgentTask[]>,
      };
    });
  };

  const applyWorkspaceState = (
    workspaceResponse: unknown,
    preferredTaskId: string = '',
  ): { workspace: Record<string, unknown>; activeTask: AgentTask | null; recentTasks: AgentTask[] } | undefined => {
    const normalized = normalizeAgentWorkspaceResponse(workspaceResponse);
    const workspace: Record<string, unknown> = normalized.workspace;
    const activeTask: AgentTask | null = buildTaskFromRunWorkspace({
      run: workspace.activeRun,
      pendingReview: workspace.pendingReview,
      latestArtifacts: workspace.latestArtifacts,
      timeline: workspace.timeline,
    }) as AgentTask | null;
    const recentTasks: AgentTask[] = ((workspace.recentRuns as unknown[]) || []).map((run: unknown) =>
      buildTaskFromRunWorkspace({
        run,
        pendingReview:
          (run as Record<string, unknown>).runId === (workspace.activeRun as Record<string, unknown>)?.runId
            ? workspace.pendingReview
            : null,
        latestArtifacts:
          (run as Record<string, unknown>).runId === (workspace.activeRun as Record<string, unknown>)?.runId
            ? workspace.latestArtifacts
            : null,
        timeline:
          (run as Record<string, unknown>).runId === (workspace.activeRun as Record<string, unknown>)?.runId
            ? (workspace.timeline as unknown[]) || []
            : [],
      }) as AgentTask,
    ).filter(Boolean) as AgentTask[];

    setState((prev: AgentWorkspaceState) => {
      const selectedTask: AgentTask | null =
        recentTasks.find((task: AgentTask) => task.taskId === preferredTaskId) ||
        activeTask ||
        recentTasks[0] ||
        null;
      return {
        ...prev,
        activeWorkspace: workspace,
        activeProject: (workspace.project as { projectId?: string })?.projectId
          ? (workspace.project as AgentProject)
          : prev.activeProject,
        currentTask: selectedTask,
        latestTask: activeTask || selectedTask || prev.latestTask,
        tasksByProjectId: (workspace.project as { projectId?: string })?.projectId
          ? replaceProjectTasks(prev.tasksByProjectId, (workspace.project as { projectId: string }).projectId, recentTasks)
          : prev.tasksByProjectId,
        error: '',
      };
    });

    return { workspace, activeTask, recentTasks };
  };

  const loadWorkspace = async (
    projectId: string,
    preferredTaskId: string = '',
  ): Promise<{ workspace: Record<string, unknown>; activeTask: AgentTask | null; recentTasks: AgentTask[] } | null> => {
    if (!projectId) return null;
    const workspaceResponse = await apiService.getAgentWorkspace(projectId);
    const result = applyWorkspaceState(workspaceResponse, preferredTaskId);
    return result || null;
  };

  const loadProjectTaskHistory = async (
    projectId: string,
    preferredTaskId: string = '',
  ): Promise<AgentTask[]> => {
    if (!projectId) return [];

    const response = await apiService.listAgentProjectTasks(projectId, 20);
    const normalized = normalizeAgentTaskListResponse(response);
    const tasks: AgentTask[] = normalized.tasks;

    setState((prev: AgentWorkspaceState) => {
      const previousCurrentTaskId: string = preferredTaskId || prev.currentTask?.taskId || '';
      const selectedTask: AgentTask | null =
        tasks.find((task: AgentTask) => task.taskId === previousCurrentTaskId) || tasks[0] || null;
      const latestTaskPatch: Partial<AgentProject> = tasks[0]
        ? {
            latestTaskId: tasks[0].taskId,
            updatedAt: tasks[0].updatedAt || createTimestamp(),
          }
        : {};
      const nextProjects: AgentProject[] = Object.keys(latestTaskPatch).length
        ? updateProject(prev.projects, projectId, latestTaskPatch)
        : prev.projects;
      const nextActiveProject: AgentProject | null =
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
    let cancelled: boolean = false;

    const loadProjects = async (): Promise<void> => {
      setState((prev: AgentWorkspaceState) => ({ ...prev, loading: true, error: '' }));
      try {
        const response = await apiService.listAgentProjects();
        if (cancelled) return;

        const normalized = normalizeAgentProjectListResponse(response);
        const initialWorkspaceState: AgentWorkspaceState = initialWorkspaceStateRef.current;
        const previousProjectId: string = initialWorkspaceState.activeProjectId;
        const nextProjectId: string = previousProjectId || normalized.projects[0]?.projectId || '';
        const nextProject: AgentProject | null =
          normalized.projects.find((item: AgentProject) => item.projectId === nextProjectId) ||
          normalized.projects[0] ||
          null;
        const cachedTasks: AgentTask[] = getProjectTasks(
          initialWorkspaceState.tasksByProjectId,
          nextProject?.projectId,
        );

        setState((prev: AgentWorkspaceState) => ({
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
            await loadWorkspace(nextProject.projectId, cachedTasks[0]?.taskId || '');
          } catch {
            try {
              await loadProjectTaskHistory(nextProject.projectId, cachedTasks[0]?.taskId || '');
            } catch {
              // Keep the local snapshot as a fallback when the project task-history endpoint is unavailable.
            }
          }
        }
      } catch (error: unknown) {
        if (cancelled) return;
        setState((prev: AgentWorkspaceState) => ({
          ...prev,
          loading: false,
          error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
            (error as { message?: string })?.message ||
            '加载 Agent 项目失败',
        }));
      }
    };

    loadProjects();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const projectId: string = state.activeProjectId;
    if (!projectId) return undefined;

    let cancelled: boolean = false;

    const loadProjectDetail = async (): Promise<void> => {
      try {
        const response = await apiService.getAgentProject(projectId);
        if (cancelled) return;

        const project: AgentProject = normalizeAgentProjectResponse(response).project;
        setState((prev: AgentWorkspaceState) => ({
          ...prev,
          activeProject: project,
          projects: upsertProject(prev.projects, project),
          error: '',
        }));

        try {
          await loadWorkspace(project.projectId);
          return;
        } catch {
          // Fall back to legacy task-shaped reads for older backends or offline snapshots.
        }

        try {
          await loadProjectTaskHistory(project.projectId);
          return;
        } catch {
          // Fall back to the pre-P1-13 latest-task path for older backends or offline snapshots.
        }

        if (!project.latestTaskId) {
          setState((prev: AgentWorkspaceState) => ({
            ...prev,
            currentTask: getProjectTasks(prev.tasksByProjectId, project.projectId)[0] || null,
          }));
          return;
        }

        const taskResponse = await apiService.getAgentTask(project.latestTaskId);
        if (cancelled) return;
        cacheTask(normalizeAgentTaskResponse(taskResponse).task as unknown as AgentTask, true);
      } catch (error: unknown) {
        if (cancelled || (error as { response?: { status?: number } })?.response?.status === 404) return;
        setState((prev: AgentWorkspaceState) => ({
          ...prev,
          error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
            (error as { message?: string })?.message ||
            '加载 Agent 项目详情失败',
        }));
      }
    };

    loadProjectDetail();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.activeProjectId]);

  useEffect(() => {
    const projectId: string = activeProject?.projectId || state.activeProjectId;
    if (
      !projectId ||
      !currentTask?.taskId ||
      TERMINAL_AGENT_STATUSES.has(currentTask?.status) ||
      PAUSED_AGENT_STATUSES.has(currentTask?.status)
    ) {
      return undefined;
    }

    let stopped: boolean = false;
    let stablePolls: number = 0;
    let currentDelay: number = 800;

    const scheduleNext = (delay: number): void => {
      if (stopped) return;
      timeoutId = setTimeout(pollTask, delay);
    };

    const pollTask = async (): Promise<void> => {
      let prevStatus: string | null = null;
      try {
        const workspaceResponse = await apiService.getAgentWorkspace(projectId);
        if (stopped) return;
        const activeRun = (workspaceResponse as { workspace?: { activeRun?: { status?: string; taskStatus?: string } } })
          ?.workspace?.activeRun;
        prevStatus = activeRun?.status ?? activeRun?.taskStatus ?? null;
        applyWorkspaceState(workspaceResponse, currentTask.taskId);
      } catch {
        try {
          const response = await apiService.getAgentTask(currentTask.taskId);
          if (stopped) return;
          const task: AgentTask = normalizeAgentTaskResponse(response).task as unknown as AgentTask;
          prevStatus = task?.status;
          cacheTask(task, true);
        } catch (error: unknown) {
          if (stopped || (error as { response?: { status?: number } })?.response?.status === 404) return;
          setState((prev: AgentWorkspaceState) => ({
            ...prev,
            error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
              (error as { message?: string })?.message ||
              '轮询 Agent 任务失败',
          }));
        }
      }

      if (stopped) return;

      // Dynamic backoff: double delay after N stable polls, reset on status change
      const nextStatus: string | undefined = currentTask?.status;
      if (nextStatus === prevStatus || !prevStatus) {
        stablePolls += 1;
        if (stablePolls >= 5) {
          currentDelay = Math.min(currentDelay * 2, 8000);
          stablePolls = 0;
        }
      } else {
        stablePolls = 0;
        currentDelay = 800;
      }

      scheduleNext(currentDelay);
    };

    let timeoutId: ReturnType<typeof setTimeout>;
    scheduleNext(currentDelay);

    return () => {
      stopped = true;
      clearTimeout(timeoutId);
    };
  }, [activeProject?.projectId, state.activeProjectId, currentTask?.taskId, currentTask?.status]);

  const projectOptions: AgentProject[] = useMemo(() => state.projects, [state.projects]);
  const taskCountsByProjectId: Record<string, number> = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(state.tasksByProjectId || {}).map(([projectId, tasks]: [string, AgentTask[]]) => [
          projectId,
          tasks.length,
        ]),
      ),
    [state.tasksByProjectId],
  );
  const currentStageLabel: string = (STAGE_LABELS as Record<string, string>)[currentTask?.stage || ''] || '等待中';

  const handleCreateProject = async (): Promise<void> => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const payload = (buildAgentProjectPayload as any)({
      projectTitle,
      fallbackTitle: `Agent 项目 ${state.nextProjectNumber}`,
      projectGoal,
      selectedPaperIds,
    });

    try {
      const response = await apiService.createAgentProject(payload);
      const project: AgentProject = normalizeAgentProjectResponse(response).project;
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        projects: upsertProject(prev.projects, project),
        nextProjectNumber: resolveNextAgentProjectNumber(
          upsertProject(prev.projects, project),
          Number(prev.nextProjectNumber || 1) + 1,
        ),
        activeProjectId: project.projectId,
        activeProject: project,
        activeWorkspace: null,
        currentTask: null,
        latestTask: null,
        error: '',
      }));
      setProjectTitle('');
      setProjectGoal('');
      setSelectedPaperIds(resolveInitialAgentPaperSelection(paperLibrary, activePaperId) as string[]);
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          '创建 Agent 项目失败',
      }));
    }
  };

  const handleDeleteProject = async (project: AgentProject): Promise<void> => {
    const normalizedProject: AgentProject = normalizeAgentProject(project);
    if (!normalizedProject.projectId) return;
    const confirmed: boolean = window.confirm(
      `确定删除项目"${normalizedProject.title}"吗？此操作会删除该项目的任务历史。`,
    );
    if (!confirmed) return;

    try {
      await apiService.deleteAgentProject(normalizedProject.projectId);
      setState((prev: AgentWorkspaceState) => ({
        ...removeAgentProjectFromState(prev, normalizedProject.projectId),
        error: '',
      }));
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          '删除 Agent 项目失败',
      }));
    }
  };

  const handleCreateTask = async (): Promise<void> => {
    const nextPrompt: string = prompt.trim();
    if (!activeProject?.projectId || !nextPrompt) return;

    try {
      const runPayload: Record<string, unknown> = {
        prompt: nextPrompt,
        focusedPaperIds: activeProject.paperIds,
        constraints: activeProject.defaultConstraints || '',
        allowExternalSearch,
        allowWebSearch,
        allowIterativeSearch,
        domain: domain || '',
        context: {
          activePaperId,
        },
      };
      await apiService.createAgentRun(activeProject.projectId, runPayload);
      try {
        await loadWorkspace(activeProject.projectId);
      } catch {
        const response = await apiService.createAgentTask(activeProject.projectId, runPayload);
        const task: AgentTask = normalizeAgentTaskResponse(response).task as unknown as AgentTask;
        cacheTask(task, true);
      }
      setPrompt('');
      setState((prev: AgentWorkspaceState) => ({ ...prev, error: '' }));
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          '创建 Agent 任务失败',
      }));
    }
  };

  const handleRefresh = async (): Promise<void> => {
    if (!state.activeProjectId) return;

    try {
      const projectResponse = await apiService.getAgentProject(state.activeProjectId);
      const project: AgentProject = normalizeAgentProjectResponse(projectResponse).project;
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        activeProject: project,
        projects: upsertProject(prev.projects, project),
        error: '',
      }));

      if (!project.latestTaskId) {
        setState((prev: AgentWorkspaceState) => ({
          ...prev,
          activeWorkspace:
            (prev.activeWorkspace as { project?: { projectId?: string } })?.project?.projectId === project.projectId
              ? prev.activeWorkspace
              : null,
        }));
      }

      try {
        await loadWorkspace(project.projectId, currentTask?.taskId || '');
        return;
      } catch {
        // Older Java/Python runtimes may not expose the workspace endpoint yet.
      }

      try {
        await loadProjectTaskHistory(project.projectId, currentTask?.taskId || '');
        return;
      } catch {
        // Older Java/Python runtimes may not expose the task-history endpoint yet.
      }

      if (currentTask?.taskId) {
        const taskResponse = await apiService.getAgentTask(currentTask.taskId);
        cacheTask(normalizeAgentTaskResponse(taskResponse).task as unknown as AgentTask, true);
      } else if (project.latestTaskId) {
        const taskResponse = await apiService.getAgentTask(project.latestTaskId);
        cacheTask(normalizeAgentTaskResponse(taskResponse).task as unknown as AgentTask, true);
      }
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          '刷新 Agent 项目失败',
      }));
    }
  };

  const handleCancelTask = async (): Promise<void> => {
    if (!currentTask?.taskId) return;

    try {
      const response = await apiService.cancelAgentTask(currentTask.taskId);
      cacheTask(normalizeAgentTaskResponse(response).task as unknown as AgentTask, true);
      setState((prev: AgentWorkspaceState) => ({ ...prev, error: '' }));
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          '取消 Agent 任务失败',
      }));
    }
  };

  const handleQuickPrompt = (label: string): void => {
    const base: string = activeProject?.paperIds?.length
      ? `请围绕当前项目中的论文执行"${label}"，输出可追踪证据、阶段结论和下一步研究建议。`
      : `请帮我执行"${label}"，并说明还需要补充哪些论文或上下文。`;
    setPrompt(base);
  };

  const handleSelectProject = (project: AgentProject): void => {
    const normalizedProject: AgentProject = normalizeAgentProject(project);
    setState((prev: AgentWorkspaceState) => {
      const nextTasks: AgentTask[] = getProjectTasks(prev.tasksByProjectId, normalizedProject.projectId);
      return {
        ...prev,
        activeProjectId: normalizedProject.projectId,
        activeProject: normalizedProject,
        activeWorkspace:
          (prev.activeWorkspace as { project?: { projectId?: string } })?.project?.projectId === normalizedProject.projectId
            ? prev.activeWorkspace
            : null,
        currentTask: nextTasks[0] || null,
        latestTask: nextTasks[0] || prev.latestTask,
        error: '',
      };
    });
  };

  const handleSelectTask = (task: AgentTask): void => {
    setState((prev: AgentWorkspaceState) => ({
      ...prev,
      currentTask: task,
      latestTask: task,
    }));
  };

  const handleReviewPlan = async (payload: Record<string, unknown>): Promise<void> => {
    if (!currentTask?.taskId) return;
    try {
      const reviewPayload = buildAgentPlanReviewPayload(payload);
      const runId: string = (currentTask as { runId?: string }).runId || currentTask.taskId;
      try {
        await apiService.reviewAgentRunPlan(runId, reviewPayload);
        await loadWorkspace(currentTask.projectId, currentTask.taskId);
      } catch {
        const response = await apiService.reviewAgentPlan(currentTask.taskId, reviewPayload);
        cacheTask(normalizeAgentTaskResponse(response).task as unknown as AgentTask, true);
      }
      setState((prev: AgentWorkspaceState) => ({ ...prev, error: '' }));
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          'Agent 计划确认失败',
      }));
    }
  };

  const handleReviewFinal = async (payload: Record<string, unknown>): Promise<void> => {
    if (!currentTask?.taskId) return;
    try {
      const runId: string = (currentTask as { runId?: string }).runId || currentTask.taskId;
      try {
        await apiService.reviewAgentRunFinal(runId, payload);
        await loadWorkspace(currentTask.projectId, currentTask.taskId);
      } catch {
        const response = await apiService.reviewAgentFinal(currentTask.taskId, payload);
        cacheTask(normalizeAgentTaskResponse(response).task as unknown as AgentTask, true);
      }
      setState((prev: AgentWorkspaceState) => ({ ...prev, error: '' }));
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          'Agent 终稿确认失败',
      }));
    }
  };

  const handleAddSelectedPaper = (paperId: string): void => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    setSelectedPaperIds((prev: string[]) => (addSelectedAgentPaperId as any)(prev, paperId) as string[]);
  };

  const handleRemoveSelectedPaper = (paperId: string): void => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    setSelectedPaperIds((prev: string[]) => (removeSelectedAgentPaperId as any)(prev, paperId) as string[]);
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
          allowExternalSearch={allowExternalSearch}
          onAllowExternalSearchChange={setAllowExternalSearch}
          allowWebSearch={allowWebSearch}
          onAllowWebSearchChange={setAllowWebSearch}
          allowIterativeSearch={allowIterativeSearch}
          onAllowIterativeSearchChange={setAllowIterativeSearch}
          domain={domain}
          onDomainChange={setDomain}
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
