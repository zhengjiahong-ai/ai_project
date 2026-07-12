import { collectSourcesByIds, normalizeEvidenceSources } from '../evidenceCitationModel.js';

export const createEmptyAgentWorkspaceState = () => ({
  projects: [],
  activeProjectId: '',
  activeProject: null,
  activeWorkspace: null,
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

export const buildAgentPlanReviewPayload = (payload = {}) => {
  const allowExternalSearch = Boolean(payload.allowExternalSearch);
  const allowWebSearch = Boolean(payload.allowWebSearch);
  return {
    planItems: (Array.isArray(payload.planItems) ? payload.planItems : []).map((item) => ({
      ...item,
      allowExternalSearch: item?.id === 'external' ? allowExternalSearch : false,
      allowWebSearch: item?.id === 'external' ? allowWebSearch : false,
    })),
    focusedPaperIds: Array.isArray(payload.focusedPaperIds) ? payload.focusedPaperIds : [],
    constraints: `${payload.constraints ?? ''}`,
    reviewNotes: `${payload.reviewNotes ?? ''}`,
    allowWebSearch,
  };
};

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
  const evidenceItems = normalizeEvidenceSources(task.evidenceItems);
  const findings = Array.isArray(task.findings) ? task.findings : [];
  const conflicts = (Array.isArray(task.conflicts) ? task.conflicts : []).map((conflict) => ({
    ...conflict,
    sources: Array.isArray(conflict?.sourceIds)
      ? collectSourcesByIds(conflict.sourceIds, evidenceItems)
      : normalizeEvidenceSources(conflict?.sources),
  }));
  const reportSourceIds = findings.flatMap((finding) => Array.isArray(finding?.sourceIds) ? finding.sourceIds : []);
  const extConfig = task.externalSearchConfig && typeof task.externalSearchConfig === 'object' ? task.externalSearchConfig : {};
  const extBudget = extConfig.budget && typeof extConfig.budget === 'object' ? extConfig.budget : {};
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
    evidenceItems,
    findings,
    comparisonTable: task.comparisonTable && typeof task.comparisonTable === 'object' ? task.comparisonTable : { columns: [], rows: [] },
    conflicts,
    reportSources: collectSourcesByIds(reportSourceIds, evidenceItems),
    openQuestions: Array.isArray(task.openQuestions) ? task.openQuestions : [],
    reviewRisks: Array.isArray(task.reviewRisks) ? task.reviewRisks : [],
    humanReview: task.humanReview && typeof task.humanReview === 'object' ? task.humanReview : {},
    constraints: `${task.constraints ?? ''}`,
    draftReport: `${task.draftReport ?? task.report ?? ''}`,
    error: `${task.error ?? ''}`,
    createdAt: `${task.createdAt ?? ''}`.trim(),
    updatedAt: `${task.updatedAt ?? ''}`.trim(),
    externalSearchConfig: {
      allowExternalSearch: Boolean(extConfig.allowExternalSearch),
      provider: `${extConfig.provider ?? ''}`.trim() || 'disabled',
      budget: {
        callLimit: Number.isFinite(Number(extBudget.callLimit)) ? Number(extBudget.callLimit) : 0,
        evidenceLimit: Number.isFinite(Number(extBudget.evidenceLimit)) ? Number(extBudget.evidenceLimit) : 0,
        callsUsed: Number.isFinite(Number(extBudget.callsUsed)) ? Number(extBudget.callsUsed) : 0,
        evidenceUsed: Number.isFinite(Number(extBudget.evidenceUsed)) ? Number(extBudget.evidenceUsed) : 0,
      },
      status: `${extConfig.status ?? ''}`.trim() || 'disabled',
      degradation: `${extConfig.degradation ?? ''}`,
    },
  };
};

export const normalizeAgentRun = (value) => {
  const run = value && typeof value === 'object' ? value : {};
  const extConfig = run.externalSearchConfig && typeof run.externalSearchConfig === 'object' ? run.externalSearchConfig : {};
  const extBudget = extConfig.budget && typeof extConfig.budget === 'object' ? extConfig.budget : {};
  return {
    runId: `${run.runId ?? ''}`.trim(),
    taskId: `${run.runId ?? ''}`.trim(),
    projectId: `${run.projectId ?? ''}`.trim(),
    traceId: `${run.traceId ?? ''}`.trim(),
    status: `${run.status ?? ''}`.trim() || 'pending',
    executionPhase: `${run.executionPhase ?? ''}`.trim() || 'planning',
    stage: `${run.executionPhase ?? ''}`.trim() || 'planning',
    progress: Number.isFinite(Number(run.progress)) ? Number(run.progress) : 0,
    prompt: `${run.prompt ?? ''}`.trim(),
    focusedPaperIds: Array.isArray(run.focusedPaperIds) ? run.focusedPaperIds.map((item) => `${item ?? ''}`.trim()).filter(Boolean) : [],
    constraints: `${run.constraints ?? ''}`.trim(),
    context: run.context && typeof run.context === 'object' ? run.context : {},
    humanReview: run.humanReview && typeof run.humanReview === 'object' ? run.humanReview : {},
    reviewRisks: Array.isArray(run.reviewRisks) ? run.reviewRisks : [],
    traceSummary: run.traceSummary && typeof run.traceSummary === 'object' ? run.traceSummary : {},
    externalSearchConfig: {
      allowExternalSearch: Boolean(extConfig.allowExternalSearch),
      provider: `${extConfig.provider ?? ''}`.trim() || 'disabled',
      budget: {
        callLimit: Number.isFinite(Number(extBudget.callLimit)) ? Number(extBudget.callLimit) : 0,
        evidenceLimit: Number.isFinite(Number(extBudget.evidenceLimit)) ? Number(extBudget.evidenceLimit) : 0,
        callsUsed: Number.isFinite(Number(extBudget.callsUsed)) ? Number(extBudget.callsUsed) : 0,
        evidenceUsed: Number.isFinite(Number(extBudget.evidenceUsed)) ? Number(extBudget.evidenceUsed) : 0,
      },
      status: `${extConfig.status ?? ''}`.trim() || 'disabled',
      degradation: `${extConfig.degradation ?? ''}`,
    },
    error: `${run.error ?? ''}`.trim(),
    createdAt: `${run.createdAt ?? ''}`.trim(),
    updatedAt: `${run.updatedAt ?? ''}`.trim(),
  };
};

export const normalizeAgentArtifactsResponse = (response) => ({
  status: `${response?.status ?? ''}`.trim() || 'error',
  artifacts: {
    runId: `${response?.artifacts?.runId ?? ''}`.trim(),
    evidenceItems: normalizeEvidenceSources(response?.artifacts?.evidenceItems),
    toolCallSummary: Array.isArray(response?.artifacts?.toolCallSummary) ? response.artifacts.toolCallSummary : [],
    findings: Array.isArray(response?.artifacts?.findings) ? response.artifacts.findings : [],
    comparisonTable: response?.artifacts?.comparisonTable && typeof response.artifacts.comparisonTable === 'object'
      ? response.artifacts.comparisonTable
      : { columns: [], rows: [] },
    conflicts: Array.isArray(response?.artifacts?.conflicts) ? response.artifacts.conflicts : [],
    openQuestions: Array.isArray(response?.artifacts?.openQuestions) ? response.artifacts.openQuestions : [],
    draftReport: `${response?.artifacts?.draftReport ?? ''}`,
  },
});

export const normalizeAgentTimelineResponse = (response) => ({
  status: `${response?.status ?? ''}`.trim() || 'error',
  timeline: Array.isArray(response?.timeline) ? response.timeline : [],
});

export const buildTaskFromRunWorkspace = ({ run = null, pendingReview = null, latestArtifacts = null, timeline = [] } = {}) => {
  if (!run) return null;
  const normalizedRun = normalizeAgentRun(run);
  const artifacts = normalizeAgentArtifactsResponse({ status: 'success', artifacts: latestArtifacts || {} }).artifacts;
  const evidenceItems = artifacts.evidenceItems;
  const findings = artifacts.findings;
  const conflicts = (Array.isArray(artifacts.conflicts) ? artifacts.conflicts : []).map((conflict) => ({
    ...conflict,
    sources: Array.isArray(conflict?.sourceIds)
      ? collectSourcesByIds(conflict.sourceIds, evidenceItems)
      : normalizeEvidenceSources(conflict?.sources),
  }));
  const reportSourceIds = findings.flatMap((finding) => Array.isArray(finding?.sourceIds) ? finding.sourceIds : []);
  return {
    taskId: normalizedRun.taskId,
    runId: normalizedRun.runId,
    projectId: normalizedRun.projectId,
    traceId: normalizedRun.traceId,
    status: normalizedRun.status,
    stage: normalizedRun.stage,
    progress: normalizedRun.progress,
    prompt: normalizedRun.prompt,
    focusedPaperIds: normalizedRun.focusedPaperIds,
    constraints: normalizedRun.constraints,
    planItems: Array.isArray(pendingReview?.planItems) ? pendingReview.planItems : [],
    events: Array.isArray(timeline) ? timeline.map((entry) => ({
      eventId: `${entry?.id ?? ''}`.trim(),
      type: `${entry?.type ?? ''}`.trim(),
      timestamp: `${entry?.timestamp ?? ''}`.trim(),
      taskId: normalizedRun.taskId,
      stage: `${entry?.phase ?? ''}`.trim(),
      summary: `${entry?.detail ?? entry?.title ?? ''}`.trim(),
      meta: entry?.meta && typeof entry.meta === 'object' ? entry.meta : {},
    })) : [],
    toolCalls: artifacts.toolCallSummary,
    evidenceItems,
    findings,
    comparisonTable: artifacts.comparisonTable,
    conflicts,
    reportSources: collectSourcesByIds(reportSourceIds, evidenceItems),
    openQuestions: artifacts.openQuestions,
    reviewRisks: normalizedRun.reviewRisks,
    humanReview: normalizedRun.humanReview,
    draftReport: artifacts.draftReport,
    error: normalizedRun.error,
    createdAt: normalizedRun.createdAt,
    updatedAt: normalizedRun.updatedAt,
    externalSearchConfig: normalizedRun.externalSearchConfig,
  };
};

export const normalizeAgentWorkspaceResponse = (response) => {
  const workspace = response?.workspace && typeof response.workspace === 'object' ? response.workspace : {};
  return {
    status: `${response?.status ?? ''}`.trim() || 'error',
    workspace: {
      project: normalizeAgentProject(workspace.project),
      activeRun: workspace.activeRun ? normalizeAgentRun(workspace.activeRun) : null,
      pendingReview: workspace.pendingReview && typeof workspace.pendingReview === 'object' ? workspace.pendingReview : null,
      latestArtifacts: workspace.latestArtifacts && typeof workspace.latestArtifacts === 'object' ? workspace.latestArtifacts : null,
      recentRuns: Array.isArray(workspace.recentRuns) ? workspace.recentRuns.map(normalizeAgentRun) : [],
      timeline: Array.isArray(workspace.timeline) ? workspace.timeline : [],
      uiHints: workspace.uiHints && typeof workspace.uiHints === 'object' ? workspace.uiHints : {},
    },
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
