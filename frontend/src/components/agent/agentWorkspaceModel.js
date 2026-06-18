export const createEmptyAgentWorkspaceState = () => ({
  projects: [],
  activeProjectId: '',
  activeProject: null,
  latestTask: null,
  currentTask: null,
  tasksByProjectId: {},
  nextProjectNumber: 1,
  loading: false,
  error: '',
});

export const resolveNextAgentProjectNumber = (projects = [], nextProjectNumber = null) => {
  const projectList = Array.isArray(projects) ? projects : [];
  const titleNumbers = projectList
    .map((project) => `${project?.title ?? ''}`.trim().match(/^Agent 项目\s+(\d+)$/))
    .filter(Boolean)
    .map((match) => Number(match[1]))
    .filter((value) => Number.isInteger(value) && value > 0);
  const inferredNext = Math.max(projectList.length + 1, titleNumbers.length ? Math.max(...titleNumbers) + 1 : 1);
  const snapshotNext = Number(nextProjectNumber);
  return Number.isInteger(snapshotNext) && snapshotNext > 0 ? Math.max(snapshotNext, inferredNext) : inferredNext;
};

const normalizePaperId = (value) => `${value ?? ''}`.trim();

export const getAgentArtifactSaveState = ({ activePdfId = '', content = '' } = {}) => {
  if (!normalizePaperId(activePdfId)) {
    return {
      canSave: false,
      reason: '请先在阅读 IDE 打开一篇论文，再保存到工作台。',
    };
  }

  const hasContent = Array.isArray(content) ? content.length > 0 : Boolean(`${content ?? ''}`.trim());
  return hasContent
    ? { canSave: true, reason: '' }
    : { canSave: false, reason: '当前产物尚未生成。' };
};

export const resolveInitialAgentPaperSelection = (paperLibrary = [], activePaperId = '') => {
  const targetPaperId = normalizePaperId(activePaperId);
  if (!targetPaperId) return [];

  const hasPaper = (Array.isArray(paperLibrary) ? paperLibrary : []).some(
    (paper) => normalizePaperId(paper?.id) === targetPaperId,
  );
  return hasPaper ? [targetPaperId] : [];
};

export const addSelectedAgentPaperId = (selectedPaperIds = [], paperId = '') => {
  const targetPaperId = normalizePaperId(paperId);
  const previousIds = (Array.isArray(selectedPaperIds) ? selectedPaperIds : [])
    .map(normalizePaperId)
    .filter(Boolean);

  if (!targetPaperId || previousIds.includes(targetPaperId)) return previousIds;
  return [...previousIds, targetPaperId];
};

export const removeSelectedAgentPaperId = (selectedPaperIds = [], paperId = '') => {
  const targetPaperId = normalizePaperId(paperId);
  return (Array.isArray(selectedPaperIds) ? selectedPaperIds : [])
    .map(normalizePaperId)
    .filter((item) => item && item !== targetPaperId);
};

export const buildAgentProjectPayload = ({
  projectTitle = '',
  fallbackTitle = 'Agent 项目',
  projectGoal = '',
  selectedPaperIds = [],
} = {}) => ({
  title: `${projectTitle ?? ''}`.trim() || `${fallbackTitle ?? ''}`.trim() || 'Agent 项目',
  goal: `${projectGoal ?? ''}`.trim(),
  paperIds: (Array.isArray(selectedPaperIds) ? selectedPaperIds : []).reduce(
    (items, paperId) => addSelectedAgentPaperId(items, paperId),
    [],
  ),
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

export const normalizeAgentTaskListResponse = (response) => {
  const limit = Number(response?.limit);
  return {
    status: `${response?.status ?? ''}`.trim() || 'error',
    projectId: `${response?.projectId ?? ''}`.trim(),
    tasks: Array.isArray(response?.tasks) ? response.tasks.map(normalizeAgentTask).filter((task) => task.taskId) : [],
    limit: Number.isInteger(limit) && limit > 0 ? limit : 20,
  };
};

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

export const removeAgentProjectFromState = (state, projectId) => {
  const targetProjectId = `${projectId ?? ''}`.trim();
  if (!targetProjectId) return state;

  const nextProjects = (state.projects || []).filter((project) => project.projectId !== targetProjectId);
  const nextTasksByProjectId = Object.fromEntries(
    Object.entries(state.tasksByProjectId || {}).filter(([taskProjectId]) => taskProjectId !== targetProjectId),
  );
  const wasActive = state.activeProjectId === targetProjectId;

  if (!wasActive) {
    return {
      ...state,
      projects: nextProjects,
      tasksByProjectId: nextTasksByProjectId,
      latestTask: state.latestTask?.projectId === targetProjectId ? state.currentTask : state.latestTask,
    };
  }

  const nextActiveProject = nextProjects[0] || null;
  const nextTask = getProjectTasks(nextTasksByProjectId, nextActiveProject?.projectId)[0] || null;
  return {
    ...state,
    projects: nextProjects,
    activeProjectId: nextActiveProject?.projectId || '',
    activeProject: nextActiveProject,
    currentTask: nextTask,
    latestTask: nextTask,
    tasksByProjectId: nextTasksByProjectId,
  };
};
