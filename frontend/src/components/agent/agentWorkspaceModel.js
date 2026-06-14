export const createEmptyAgentWorkspaceState = () => ({
  projects: [],
  activeProjectId: '',
  activeProject: null,
  latestTask: null,
  currentTask: null,
  tasksByProjectId: {},
  loading: false,
  error: '',
});

export const normalizeAgentProject = (value) => {
  const project = value && typeof value === 'object' ? value : {};
  return {
    projectId: `${project.projectId ?? ''}`.trim(),
    title: `${project.title ?? ''}`.trim() || 'Agent 研究项目',
    goal: `${project.goal ?? ''}`.trim(),
    paperIds: Array.isArray(project.paperIds) ? project.paperIds.map((item) => `${item ?? ''}`.trim()).filter(Boolean) : [],
    papers: Array.isArray(project.papers) ? project.papers : [],
    latestTaskId: `${project.latestTaskId ?? ''}`.trim(),
    defaultConstraints: `${project.defaultConstraints ?? ''}`.trim(),
    createdAt: `${project.createdAt ?? ''}`.trim(),
    updatedAt: `${project.updatedAt ?? ''}`.trim(),
  };
};

export const normalizeAgentTask = (value) => {
  const task = value && typeof value === 'object' ? value : {};
  return {
    taskId: `${task.taskId ?? ''}`.trim(),
    projectId: `${task.projectId ?? ''}`.trim(),
    traceId: `${task.traceId ?? ''}`.trim(),
    status: `${task.status ?? ''}`.trim() || 'pending',
    stage: `${task.stage ?? ''}`.trim() || 'planning',
    progress: Number.isFinite(Number(task.progress)) ? Number(task.progress) : 0,
    prompt: `${task.prompt ?? task.question ?? ''}`.trim(),
    focusedPaperIds: Array.isArray(task.focusedPaperIds) ? task.focusedPaperIds.map((item) => `${item ?? ''}`.trim()).filter(Boolean) : [],
    planItems: Array.isArray(task.planItems || task.plan) ? task.planItems || task.plan : [],
    events: Array.isArray(task.events) ? task.events : [],
    toolCalls: Array.isArray(task.toolCalls) ? task.toolCalls : [],
    evidenceItems: Array.isArray(task.evidenceItems) ? task.evidenceItems : [],
    findings: Array.isArray(task.findings) ? task.findings : [],
    comparisonTable: task.comparisonTable && typeof task.comparisonTable === 'object' ? task.comparisonTable : { columns: [], rows: [] },
    conflicts: Array.isArray(task.conflicts) ? task.conflicts : [],
    openQuestions: Array.isArray(task.openQuestions) ? task.openQuestions : [],
    draftReport: `${task.draftReport ?? task.report ?? ''}`,
    error: `${task.error ?? ''}`,
    createdAt: `${task.createdAt ?? ''}`.trim(),
    updatedAt: `${task.updatedAt ?? ''}`.trim(),
  };
};

export const normalizeAgentProjectListResponse = (response) => ({
  status: `${response?.status ?? ''}`.trim() || 'error',
  projects: Array.isArray(response?.projects) ? response.projects.map(normalizeAgentProject) : [],
});

export const normalizeAgentProjectResponse = (response) => ({
  status: `${response?.status ?? ''}`.trim() || 'error',
  project: normalizeAgentProject(response?.project),
});

export const normalizeAgentTaskResponse = (response) => ({
  status: `${response?.status ?? ''}`.trim() || 'error',
  task: normalizeAgentTask(response?.task),
});

export const appendAgentTaskForProject = (tasksByProjectId, task) => {
  if (!task?.projectId || !task?.taskId) return tasksByProjectId || {};
  const previousTasks = tasksByProjectId?.[task.projectId] || [];
  const nextTasks = [
    task,
    ...previousTasks.filter((item) => item.taskId !== task.taskId),
  ].sort((a, b) => {
    const left = new Date(a.updatedAt || a.createdAt || 0).getTime();
    const right = new Date(b.updatedAt || b.createdAt || 0).getTime();
    return right - left;
  });

  return {
    ...(tasksByProjectId || {}),
    [task.projectId]: nextTasks,
  };
};

export const getProjectTasks = (tasksByProjectId, projectId) =>
  projectId ? tasksByProjectId?.[projectId] || [] : [];
