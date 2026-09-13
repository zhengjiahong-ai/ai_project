import React, { useEffect, useMemo, useRef, useState } from 'react';

import { apiService, type AgentRunPayload, type FinalReviewPayload } from '../../services/api';
import AgentWorkspaceMain from './AgentWorkspaceMain.jsx';
import AgentWorkspaceSidebar, { AgentWorkspaceLeftRail } from './AgentWorkspaceSidebar.jsx';
import {
  addSelectedAgentPaperId,
  buildAgentProjectPayload,
  buildAgentPlanReviewPayload,
  appendAgentTaskForProject,
  buildTaskFromRunWorkspace,
  mergeAgentRunFallback,
  createEmptyAgentWorkspaceState,
  getProjectTasks,
  normalizeAgentProject,
  normalizeAgentProjectListResponse,
  normalizeAgentProjectResponse,
  normalizeAgentTask,
  normalizeAgentTaskListResponse,
  normalizeAgentTaskResponse,
  normalizeAgentWorkspaceResponse,
  normalizeAgentMessage,
  normalizeAgentResearchTask,
  removeAgentProjectFromState,
  removeSelectedAgentPaperId,
  resolveInitialAgentPaperSelection,
  resolveNextAgentProjectNumber,
  type AgentProject,
  type AgentMessage,
  type AgentResearchTask,
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
  const researchTasksByProjectId = Object.fromEntries(
    Object.entries(snapshot?.researchTasksByProjectId || {}).map(([projectId, tasks]: [string, unknown]) => [
      projectId,
      (Array.isArray(tasks) ? tasks : []).map(normalizeAgentResearchTask).filter((task) => task.taskId),
    ]),
  ) as Record<string, AgentResearchTask[]>;
  const messagesByTaskId = Object.fromEntries(
    Object.entries(snapshot?.messagesByTaskId || {}).map(([taskId, messages]: [string, unknown]) => [
      taskId,
      (Array.isArray(messages) ? messages : []).map(normalizeAgentMessage).filter((message) => message.messageId),
    ]),
  ) as Record<string, AgentMessage[]>;
  return {
    ...createEmptyAgentWorkspaceState(),
    ...(snapshot || {}),
    projects,
    activeProject: snapshot?.activeProject ? normalizeAgentProject(snapshot.activeProject) : null,
    activeWorkspace: snapshot?.activeWorkspace ?? null,
    latestTask: snapshot?.latestTask ? normalizeAgentTask(snapshot.latestTask) : null,
    currentTask: snapshot?.currentTask ? normalizeAgentTask(snapshot.currentTask) : null,
    tasksByProjectId,
    researchTasksByProjectId,
    messagesByTaskId,
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
  const pendingSubmissionRef = useRef<{ signature: string; key: string } | null>(null);
  const [projectTitle, setProjectTitle] = useState<string>('');
  const [projectGoal, setProjectGoal] = useState<string>('');
  const [selectedPaperIds, setSelectedPaperIds] = useState<string[]>(() =>
    resolveInitialAgentPaperSelection(paperLibrary, activePaperId) as string[],
  );
  const [prompt, setPrompt] = useState<string>('');
  const [allowExternalSearch, setAllowExternalSearch] = useState<boolean>(false);
  const [allowWebSearch, setAllowWebSearch] = useState<boolean>(false);
  const [allowKnowledgeGraph, setAllowKnowledgeGraph] = useState<boolean>(true);
  const [domain, setDomain] = useState<string>('');
  const [allowIterativeSearch, setAllowIterativeSearch] = useState<boolean>(false);
  const [leftCollapsed, setLeftCollapsed] = useState<boolean>(false);

  const activeProject: AgentProject | null = state.activeProject;
  const projectTasks: AgentTask[] = useMemo(
    () => getProjectTasks(state.tasksByProjectId, state.activeProjectId),
    [state.tasksByProjectId, state.activeProjectId],
  );
  const projectResearchTasks: AgentResearchTask[] = useMemo(
    () => state.researchTasksByProjectId[state.activeProjectId] || [],
    [state.researchTasksByProjectId, state.activeProjectId],
  );
  const currentMessages: AgentMessage[] = state.activeResearchTaskId
    ? state.messagesByTaskId[state.activeResearchTaskId] || []
    : [];

  const [debateResult, setDebateResult] = useState<any>(null);

  const handleDebateComplete = (result: any): void => {
    setDebateResult(result);
  };


  const currentTask: any = (() => {
    const base: any = state.currentTask || projectTasks[0] || null;
    return base && debateResult ? { ...base, debateResult } : base;
  })();

  useEffect(() => {
    saveAgentWorkspaceSnapshot({
      projects: state.projects,
      activeProjectId: state.activeProjectId,
      activeProject: state.activeProject,
      activeWorkspace: state.activeWorkspace,
      latestTask: state.latestTask,
      currentTask: state.currentTask,
      tasksByProjectId: state.tasksByProjectId,
      researchTasksByProjectId: state.researchTasksByProjectId,
      messagesByTaskId: state.messagesByTaskId,
      activeResearchTaskId: state.activeResearchTaskId,
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
    const researchTasks = ((workspace.tasks as unknown[]) || [])
      .map(normalizeAgentResearchTask)
      .filter((task: AgentResearchTask) => task.taskId);
    const workspaceActiveTaskId = `${workspace.activeTaskId ?? ''}`.trim();
    const selectedResearchTaskId =
      researchTasks.find((task: AgentResearchTask) => task.taskId === preferredTaskId || task.latestRunId === preferredTaskId)?.taskId ||
      workspaceActiveTaskId ||
      researchTasks[0]?.taskId ||
      '';
    const messages = ((workspace.messages as unknown[]) || []).map(normalizeAgentMessage);
    const workspaceProjectId = `${(workspace.project as { projectId?: string })?.projectId ?? ''}`;
    setState((prev: AgentWorkspaceState) => {
      const cachedPreferredTask = preferredTaskId
        ? getProjectTasks(prev.tasksByProjectId, workspaceProjectId).find((task: AgentTask) => task.taskId === preferredTaskId) || null
        : null;
      const selectedTask: AgentTask | null =
        recentTasks.find((task: AgentTask) => task.taskId === preferredTaskId) ||
        activeTask ||
        cachedPreferredTask ||
        recentTasks[0] ||
        prev.currentTask ||
        null;
      return {
        ...prev,
        activeWorkspace: workspace,
        activeProject: (workspace.project as { projectId?: string })?.projectId
          ? (workspace.project as AgentProject)
          : prev.activeProject,
        currentTask: selectedTask,
        latestTask: activeTask || selectedTask || prev.latestTask,
        tasksByProjectId: workspaceProjectId
          ? recentTasks.length
            ? replaceProjectTasks(prev.tasksByProjectId, workspaceProjectId, recentTasks)
            : prev.tasksByProjectId
          : prev.tasksByProjectId,
        researchTasksByProjectId: (workspace.project as { projectId?: string })?.projectId
          ? {
              ...prev.researchTasksByProjectId,
              [(workspace.project as { projectId: string }).projectId]: researchTasks,
            }
          : prev.researchTasksByProjectId,
        activeResearchTaskId: selectedResearchTaskId,
        messagesByTaskId: workspaceActiveTaskId
          ? { ...prev.messagesByTaskId, [workspaceActiveTaskId]: messages }
          : prev.messagesByTaskId,
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
      const runId: string = (currentTask as { runId?: string }).runId || currentTask.taskId;

      // 轮询优先读取项目 workspace，失败时并行读取 run 元数据、artifacts 和 timeline
      try {
        const workspaceResponse = await apiService.getAgentWorkspace(projectId);
        if (stopped) return;
        const activeRun = (workspaceResponse as { workspace?: { activeRun?: { status?: string; taskStatus?: string } } })
          ?.workspace?.activeRun;
        prevStatus = activeRun?.status ?? activeRun?.taskStatus ?? null;
        applyWorkspaceState(workspaceResponse, currentTask.taskId);
      } catch {
        // workspace 暂时不可用时并行读取 run、artifacts 和 timeline，保留完整产物
        try {
          const [runResponse, artifactsResponse, timelineResponse] = await Promise.all([
            apiService.getAgentRun(runId),
            apiService.getAgentRunArtifacts(runId).catch(() => null),
            apiService.getAgentRunTimeline(runId).catch(() => null),
          ]);
          if (stopped) return;

          const run = (runResponse as { run?: Record<string, unknown> })?.run;
          const task = mergeAgentRunFallback({
            previousTask: currentTask as ReturnType<typeof buildTaskFromRunWorkspace>,
            run,
            artifacts: (artifactsResponse as { artifacts?: Record<string, unknown> } | null)?.artifacts ?? null,
            timeline: (timelineResponse as { timeline?: unknown[] } | null)?.timeline ?? null,
          }) as AgentTask | null;
          if (task) {
            prevStatus = task.status;
            cacheTask(task, true);
          }
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

    const targetProjectId: string = activeProject.projectId;
    const targetResearchTaskId: string = state.activeResearchTaskId;
    const submissionSignature: string = `${targetProjectId}\n${targetResearchTaskId}\n${nextPrompt}`;
    if (pendingSubmissionRef.current?.signature !== submissionSignature) {
      pendingSubmissionRef.current = {
        signature: submissionSignature,
        key: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
      };
    }

    try {
      const runPayload: Record<string, unknown> = {
        prompt: nextPrompt,
        reviewMode: 'auto',
        idempotencyKey: pendingSubmissionRef.current.key,
        focusedPaperIds: activeProject.paperIds,
        constraints: activeProject.defaultConstraints || '',
        allowExternalSearch,
        allowWebSearch,
        allowIterativeSearch,
        allowKnowledgeGraph,
        domain: domain || '',
        context: {
          activePaperId,
        },
      };

      // 通过项目持久化 run 接口创建任务
      const response = targetResearchTaskId
        ? await apiService.createAgentTaskRun(
            targetResearchTaskId,
            runPayload as unknown as AgentRunPayload,
          )
        : await apiService.createAgentRun(
            targetProjectId,
            runPayload as unknown as AgentRunPayload,
          );

      // 校验返回的 run 契约
      const returnedRun = (response as { run?: Record<string, unknown> })?.run;
      const returnedRunId: string = `${returnedRun?.runId ?? ''}`.trim();
      const returnedProjectId: string = `${returnedRun?.projectId ?? ''}`.trim();
      const returnedResearchTaskId: string = `${returnedRun?.taskId ?? ''}`.trim();

      if (!returnedRunId) {
        throw new Error('创建 Agent 任务失败：后端未返回 runId');
      }
      if (!returnedProjectId) {
        throw new Error('创建 Agent 任务失败：后端未返回 projectId');
      }
      if (returnedProjectId !== targetProjectId) {
        throw new Error(
          `创建 Agent 任务失败：run 归属项目 ${returnedProjectId} 与当前项目 ${targetProjectId} 不一致`,
        );
      }
      if (!returnedResearchTaskId) {
        throw new Error('创建 Agent 任务失败：后端未返回 taskId');
      }
      if (targetResearchTaskId && returnedResearchTaskId !== targetResearchTaskId) {
        throw new Error('创建 Agent 任务失败：run 未归入当前研究任务');
      }

      // 立即缓存新任务，确保它进入当前项目任务列表
      const createdTask = buildTaskFromRunWorkspace({ run: returnedRun }) as AgentTask | null;
      if (createdTask) {
        cacheTask(createdTask, true);
      }
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        activeResearchTaskId: returnedResearchTaskId,
      }));
      pendingSubmissionRef.current = null;

      // 清空输入，避免用户以为没有提交
      setPrompt('');

      // 刷新 workspace 以获取最新状态；刷新失败不影响已创建的任务
      try {
        await loadWorkspace(targetProjectId, returnedRunId);
        setState((prev: AgentWorkspaceState) => ({ ...prev, error: '' }));
      } catch (refreshError: unknown) {
        const originalMessage: string =
          (refreshError as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (refreshError as { message?: string })?.message ||
          '';
        setState((prev: AgentWorkspaceState) => ({
          ...prev,
          error: `任务已创建，但工作区刷新失败${originalMessage ? `：${originalMessage}` : ''}`,
        }));
      }
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          '创建 Agent 任务失败',
      }));
    }
  };

  // 24-3: Handle debate completion
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
      const runId: string = (currentTask as { runId?: string }).runId || currentTask.taskId;
      const response = await apiService.cancelAgentRun(runId);
      const cancelled = mergeAgentRunFallback({
        previousTask: currentTask,
        run: (response as { run?: Record<string, unknown> }).run,
      }) as AgentTask | null;
      if (cancelled) cacheTask(cancelled, true);
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

  const handleRetryTask = async (): Promise<void> => {
    if (!currentTask?.taskId) return;
    try {
      const runId: string = (currentTask as { runId?: string }).runId || currentTask.taskId;
      const response = await apiService.retryAgentRun(runId);
      const retried = buildTaskFromRunWorkspace({
        run: (response as { run?: Record<string, unknown> }).run,
      }) as AgentTask | null;
      if (!retried?.taskId || retried.projectId !== currentTask.projectId) {
        throw new Error('重试失败：后端返回了无效的运行记录');
      }
      cacheTask(retried, true);
      await loadWorkspace(retried.projectId, retried.taskId);
      setState((prev: AgentWorkspaceState) => ({ ...prev, error: '' }));
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error: (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message || '重试 Agent 任务失败',
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
      const nextResearchTasks = prev.researchTasksByProjectId[normalizedProject.projectId] || [];
      const nextResearchTaskId = nextResearchTasks[0]?.taskId || '';
      const nextRun =
        nextTasks.find((task) => task.taskId === nextResearchTasks[0]?.latestRunId) ||
        nextTasks[0] ||
        null;
      return {
        ...prev,
        activeProjectId: normalizedProject.projectId,
        activeProject: normalizedProject,
        activeWorkspace:
          (prev.activeWorkspace as { project?: { projectId?: string } })?.project?.projectId === normalizedProject.projectId
            ? prev.activeWorkspace
            : null,
        activeResearchTaskId: nextResearchTaskId,
        currentTask: nextRun,
        latestTask: nextRun || prev.latestTask,
        error: '',
      };
    });
  };

  const handleStartNewResearchTask = (): void => {
    pendingSubmissionRef.current = null;
    setState((prev: AgentWorkspaceState) => ({
      ...prev,
      activeResearchTaskId: '',
      currentTask: null,
      error: '',
    }));
  };

  const handleSelectTask = async (researchTask: AgentResearchTask): Promise<void> => {
    const cachedRun = projectTasks.find((task) => task.taskId === researchTask.latestRunId) || null;
    setState((prev: AgentWorkspaceState) => ({
      ...prev,
      activeResearchTaskId: researchTask.taskId,
      currentTask: cachedRun,
      latestTask: cachedRun || prev.latestTask,
      error: '',
    }));
    try {
      const [messageResponse, runResponse, artifactsResponse, timelineResponse] = await Promise.all([
        apiService.getAgentTaskMessages(researchTask.taskId),
        apiService.getAgentRun(researchTask.latestRunId),
        apiService.getAgentRunArtifacts(researchTask.latestRunId).catch(() => null),
        apiService.getAgentRunTimeline(researchTask.latestRunId).catch(() => null),
      ]);
      const messages = Array.isArray((messageResponse as { messages?: unknown[] })?.messages)
        ? (messageResponse as { messages: unknown[] }).messages.map(normalizeAgentMessage)
        : [];
      const selectedRun = buildTaskFromRunWorkspace({
        run: (runResponse as { run?: Record<string, unknown> })?.run,
        latestArtifacts: (artifactsResponse as { artifacts?: Record<string, unknown> } | null)?.artifacts,
        timeline: (timelineResponse as { timeline?: unknown[] } | null)?.timeline,
      }) as AgentTask | null;
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        activeResearchTaskId: researchTask.taskId,
        messagesByTaskId: {
          ...prev.messagesByTaskId,
          [researchTask.taskId]: messages,
        },
        currentTask: selectedRun || prev.currentTask,
        latestTask: selectedRun || prev.latestTask,
        tasksByProjectId: selectedRun
          ? appendAgentTaskForProject(prev.tasksByProjectId, selectedRun) as Record<string, AgentTask[]>
          : prev.tasksByProjectId,
        error: '',
      }));
    } catch (error: unknown) {
      setState((prev: AgentWorkspaceState) => ({
        ...prev,
        error:
          (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data?.message ||
          (error as { message?: string })?.message ||
          '加载研究任务失败',
      }));
    }
  };

  const handleReviewPlan = async (payload: Record<string, unknown>): Promise<void> => {
    if (!currentTask?.taskId) return;
    try {
      const runId: string = (currentTask as { runId?: string }).runId || currentTask.taskId;
      const reviewPayload = buildAgentPlanReviewPayload(payload);

      // 计划审核通过 run API 提交
      await apiService.reviewAgentRunPlan(runId, reviewPayload);
      await loadWorkspace(currentTask.projectId, currentTask.taskId);

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

      // 最终审核通过 run API 提交
      await apiService.reviewAgentRunFinal(runId, payload as unknown as FinalReviewPayload);
      await loadWorkspace(currentTask.projectId, currentTask.taskId);

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
    <div className="agent-shell flex h-full min-h-0 min-w-0 flex-1 overflow-hidden">
      <div
        className="grid h-full min-h-0 min-w-0 flex-1 overflow-hidden"
        style={{
          gridTemplateColumns: `${leftCollapsed ? '48px' : '292px'} minmax(0,1fr)`,
        }}
      >
        {leftCollapsed ? (
          <AgentWorkspaceLeftRail onExpand={() => setLeftCollapsed(false)} />
        ) : (
          <AgentWorkspaceSidebar
            activeProject={activeProject}
            currentTask={currentTask}
            projectTasks={projectResearchTasks}
            activeResearchTaskId={state.activeResearchTaskId}
            projectOptions={projectOptions}
            activeProjectId={state.activeProjectId}
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
            onSelectTask={handleSelectTask}
            onStartNewTask={handleStartNewResearchTask}
            onDeleteProject={handleDeleteProject}
            onCollapse={() => setLeftCollapsed(true)}
          />
        )}

        <AgentWorkspaceMain
          activeProject={activeProject}
          currentTask={currentTask}
          stateError={state.error}
          projectTasks={projectResearchTasks}
          messages={currentMessages}
          currentStageLabel={currentStageLabel}
          prompt={prompt}
          onPromptChange={setPrompt}
          onQuickPrompt={handleQuickPrompt}
          onCreateTask={handleCreateTask}
          onRefresh={handleRefresh}
          onCancelTask={handleCancelTask}
          onRetryTask={handleRetryTask}
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
          allowKnowledgeGraph={allowKnowledgeGraph}
          onAllowKnowledgeGraphChange={setAllowKnowledgeGraph}    onAllowIterativeSearchChange={setAllowIterativeSearch}
          domain={domain}
          onDomainChange={setDomain}
          onDebateComplete={handleDebateComplete}
        />

      </div>
    </div>
  );
};

export default AgentWorkspace;
