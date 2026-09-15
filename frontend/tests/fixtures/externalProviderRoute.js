const now = '2026-06-29T03:30:00.000Z';

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

const externalConfig = (scenario, status = 'ready') => ({
  allowExternalSearch: true,
  provider: 'crossref',
  budget: {
    callLimit: 3,
    evidenceLimit: 15,
    callsUsed: status === 'ready' ? 0 : scenario === 'success' ? 1 : 0,
    evidenceUsed: status === 'ready' ? 0 : scenario === 'success' ? 1 : 0,
  },
  status: scenario === 'failure' && status !== 'ready' ? 'degraded' : status,
  degradation: scenario === 'failure' && status !== 'ready' ? 'External academic provider failed.' : '',
});

const toRun = (task) => ({
  runId: task.taskId,
  taskId: task.taskId,
  projectId: task.projectId,
  traceId: task.traceId,
  status: task.status,
  executionPhase: task.stage,
  progress: task.progress,
  prompt: task.prompt,
  focusedPaperIds: task.focusedPaperIds,
  constraints: task.constraints || '',
  context: {},
  humanReview: task.humanReview || {},
  reviewRisks: task.reviewRisks || [],
  traceSummary: task.traceSummary || {},
  externalSearchConfig: task.externalSearchConfig,
  error: task.error || '',
  createdAt: task.createdAt,
  updatedAt: task.updatedAt,
});

const toPendingReview = (task) => ({
  runId: task.taskId,
  status: task.status === 'awaiting_plan_review' ? 'pending' : task.status === 'running' ? 'approved' : task.status === 'awaiting_final_review' ? 'final_pending' : 'completed',
  planItems: task.planItems || [],
});

const toArtifacts = (task) => ({
  runId: task.taskId,
  evidenceItems: task.evidenceItems || [],
  toolCallSummary: task.toolCalls || [],
  findings: task.findings || [],
  comparisonTable: task.comparisonTable || { columns: [], rows: [] },
  conflicts: task.conflicts || [],
  openQuestions: task.openQuestions || [],
  draftReport: task.draftReport || '',
});

const toTimeline = (task) =>
  (task.events || []).map((event, index) => ({
    id: event.eventId || `entry-${index + 1}`,
    type: event.type || 'status_changed',
    title: event.summary || event.type || 'Event',
    detail: event.summary || '',
    phase: event.stage || task.stage || 'planning',
    meta: event.meta || {},
    timestamp: task.updatedAt || now,
  }));

const toWorkspace = (project, task) => ({
  project,
  activeRun: task ? toRun(task) : null,
  pendingReview: task ? toPendingReview(task) : null,
  latestArtifacts: task ? toArtifacts(task) : null,
  recentRuns: task ? [toRun(task)] : [],
  timeline: task ? toTimeline(task) : [],
  uiHints: {},
});

const buildTaskStates = (scenario) => {
  const base = {
    taskId: 'task-external-1',
    projectId: 'project-external-1',
    traceId: 'trace-external-1',
    prompt: '',
    focusedPaperIds: ['paper-external-1'],
    constraints: '',
    planItems: [
      { id: 'retrieve', label: '检索内部论文证据', detail: '先读取当前论文和项目论文', status: 'pending', allowExternalSearch: false },
      { id: 'external', label: 'External academic search', detail: '仅在证据不足时查询 Crossref', status: 'pending', allowExternalSearch: false },
    ],
    events: [],
    toolCalls: [],
    evidenceItems: [],
    findings: [],
    comparisonTable: { columns: [], rows: [] },
    conflicts: [],
    openQuestions: [],
    draftReport: '',
    humanReview: { planStatus: 'pending', finalStatus: 'not_started' },
    reviewRisks: [],
    traceSummary: {},
    error: '',
    createdAt: now,
    updatedAt: now,
    externalSearchConfig: externalConfig(scenario),
  };

  const planned = { ...base, status: 'awaiting_plan_review', stage: 'planning', progress: 0.2 };
  const running = {
    ...base,
    status: 'running',
    stage: 'retrieving',
    progress: 0.6,
    humanReview: { planStatus: 'approved', finalStatus: 'not_started' },
    events: [{ eventId: 'event-start', type: 'retrieval_started', stage: 'retrieving', summary: '内部证据不足，开始受限外部补查' }],
  };
  const internalEvidence = {
    sourceId: 'source-internal-1',
    pdfId: 'paper-external-1',
    sectionId: 'methods',
    pageIndex: 0,
    sourceType: 'paper',
    text: '内部论文只覆盖原始实验，缺少外部适用范围验证。',
  };
  const externalEvidence = {
    sourceId: 'source-external-crossref-1',
    sourceType: 'external_academic',
    provider: 'crossref',
    providerId: '10.3390/app12188972',
    title: 'Deep Residual Learning for Image Recognition: A Survey',
    authors: ['Targ S', 'Almeida D', 'Lyman K'],
    year: 2022,
    doi: '10.3390/app12188972',
    url: 'https://doi.org/10.3390/app12188972',
    retrievedAt: '2026-06-29T03:15:00Z',
    abstract: 'A survey of residual learning methods and their application boundaries.',
    text: '外部综述证据补充了适用范围边界。',
  };
  const failed = scenario === 'failure';
  const draft = {
    ...base,
    status: 'awaiting_final_review',
    stage: 'synthesizing',
    progress: 0.95,
    humanReview: { planStatus: 'approved', finalStatus: 'pending' },
    externalSearchConfig: externalConfig(scenario, failed ? 'degraded' : 'success'),
    events: [{
      eventId: failed ? 'event-degraded' : 'event-external',
      type: failed ? 'tool_failed' : 'tool_completed',
      stage: 'retrieving',
      summary: failed ? 'External academic provider failed.' : 'Crossref 返回 1 条外部证据',
    }],
    toolCalls: [{
      id: 'tool-external-1',
      name: 'retrieve_external_academic',
      target: 'crossref',
      result: failed ? 'Provider failed; continued with internal evidence.' : 'Collected 1 external evidence item.',
      status: failed ? 'failed' : 'succeeded',
      meta: failed ? { reason: 'External academic provider failed.' } : {},
    }],
    evidenceItems: failed ? [internalEvidence] : [internalEvidence, externalEvidence],
    findings: [{
      id: 'finding-external-1',
      summary: failed ? '外部 Provider 失败，保留内部判断和未解决缺口。' : '外部综述证据补充了适用范围边界。',
      sourceIds: failed ? ['source-internal-1'] : ['source-internal-1', 'source-external-crossref-1'],
    }],
    draftReport: failed
      ? '## Degraded Result\nExternal academic provider failed. 内部证据与未解决缺口均已保留。'
      : '## External Validation\n外部综述证据补充了适用范围边界。[source-external-crossref-1]',
    reviewRisks: [{
      riskId: 'external:1',
      type: failed ? 'external_degradation' : 'external_source',
      label: failed ? '外部检索降级' : '外部来源核验',
      detail: failed ? 'External academic provider failed.' : '请人工核验 DOI、URL 与摘要一致性。',
      sourceIds: failed ? [] : ['source-external-crossref-1'],
      reviewStatus: 'pending',
    }],
  };
  const completed = {
    ...draft,
    status: 'succeeded',
    stage: 'done',
    progress: 1,
    humanReview: { planStatus: 'approved', finalStatus: 'approved' },
    events: [...draft.events, { eventId: 'event-complete', type: 'task_completed', stage: 'done', summary: '研究任务已完成' }],
  };
  return { planned, running, draft, completed };
};

export const installExternalProviderRoute = async (page, { scenario = 'success' } = {}) => {
  const states = buildTaskStates(scenario);
  const state = {
    scenario,
    project: null,
    task: null,
    taskPollCount: 0,
    workspacePollCount: 0,
    projectPayload: null,
    taskPayload: null,
    planReviewPayload: null,
    finalReviewPayload: null,
  };

  await page.route('http://localhost:8081/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname === '/api/upload') {
      await json(route, {
        status: 'success',
        pdfId: 'paper-external-1',
        title: '外部检索测试论文',
        authors: ['Pixiu Test'],
        ragIndexed: true,
        ragChunkCount: 1,
        paper_structure: { title: '外部检索测试论文', research_problem: '外部证据验证' },
        paper_skeleton: { title: '外部检索测试论文', sections: [{ id: 'methods', title: 'Methods', summary: '内部证据' }] },
      });
      return;
    }
    await json(route, { status: 'error', message: `Unexpected reader API request: ${request.method()} ${url.pathname}` }, 404);
  });

  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/agent-projects') {
      await json(route, { status: 'success', projects: state.project ? [state.project] : [] });
      return;
    }
    if (request.method() === 'POST' && path === '/api/agent-projects') {
      state.projectPayload = request.postDataJSON();
      state.project = { projectId: 'project-external-1', ...state.projectPayload, latestTaskId: '', createdAt: now, updatedAt: now };
      await json(route, { status: 'success', project: state.project });
      return;
    }
    if (request.method() === 'GET' && path === '/api/agent-projects/project-external-1') {
      await json(route, { status: 'success', project: state.project });
      return;
    }
    if (request.method() === 'GET' && path === '/api/agent-projects/project-external-1/workspace') {
      state.workspacePollCount += 1;
      if (state.task?.status === 'running') {
        state.taskPollCount += 1;
        state.task = state.taskPollCount >= 2
          ? { ...states.draft, prompt: state.taskPayload.prompt, planItems: state.planReviewPayload.planItems }
          : { ...states.running, prompt: state.taskPayload.prompt, planItems: state.planReviewPayload.planItems };
      }
      await json(route, { status: 'success', workspace: toWorkspace(state.project, state.task) });
      return;
    }
    if (request.method() === 'GET' && path === '/api/agent-projects/project-external-1/tasks') {
      await json(route, { status: 'success', projectId: 'project-external-1', tasks: state.task ? [state.task] : [], limit: 20 });
      return;
    }
    if (request.method() === 'POST' && path === '/api/agent-projects/project-external-1/runs') {
      state.taskPayload = request.postDataJSON();
      state.task = { ...states.planned, prompt: state.taskPayload.prompt };
      state.project = { ...state.project, latestTaskId: state.task.taskId, updatedAt: now };
      await json(route, { status: 'success', run: toRun(state.task) });
      return;
    }
    if (request.method() === 'POST' && path === '/api/agent-projects/project-external-1/tasks') {
      state.taskPayload = request.postDataJSON();
      state.task = { ...states.planned, prompt: state.taskPayload.prompt };
      state.project = { ...state.project, latestTaskId: state.task.taskId, updatedAt: now };
      await json(route, { status: 'success', task: state.task });
      return;
    }
    if (request.method() === 'GET' && path === '/api/agent-runs/task-external-1') {
      await json(route, { status: 'success', run: toRun(state.task || states.planned) });
      return;
    }
    if (request.method() === 'GET' && path === '/api/agent-runs/task-external-1/artifacts') {
      await json(route, { status: 'success', artifacts: toArtifacts(state.task || states.planned) });
      return;
    }
    if (request.method() === 'GET' && path === '/api/agent-runs/task-external-1/timeline') {
      await json(route, { status: 'success', timeline: toTimeline(state.task || states.planned) });
      return;
    }
    if (request.method() === 'POST' && path === '/api/agent-runs/task-external-1/plan-review') {
      state.planReviewPayload = request.postDataJSON();
      state.task = { ...states.running, prompt: state.taskPayload.prompt, planItems: state.planReviewPayload.planItems };
      state.taskPollCount = 0;
      await json(route, { status: 'success', run: toRun(state.task), pendingReview: toPendingReview(state.task) });
      return;
    }
    if (request.method() === 'POST' && path === '/api/agent-tasks/task-external-1/plan-review') {
      state.planReviewPayload = request.postDataJSON();
      state.task = { ...states.running, prompt: state.taskPayload.prompt, planItems: state.planReviewPayload.planItems };
      state.taskPollCount = 0;
      await json(route, { status: 'success', task: state.task });
      return;
    }
    if (request.method() === 'GET' && path === '/api/agent-tasks/task-external-1') {
      state.taskPollCount += 1;
      state.task = state.taskPollCount >= 2
        ? { ...states.draft, prompt: state.taskPayload.prompt }
        : { ...states.running, prompt: state.taskPayload.prompt, planItems: state.planReviewPayload.planItems };
      await json(route, { status: 'success', task: state.task });
      return;
    }
    if (request.method() === 'POST' && path === '/api/agent-runs/task-external-1/final-review') {
      state.finalReviewPayload = request.postDataJSON();
      state.task = { ...states.completed, prompt: state.taskPayload.prompt };
      await json(route, { status: 'success', run: toRun(state.task), artifacts: toArtifacts(state.task) });
      return;
    }
    if (request.method() === 'POST' && path === '/api/agent-tasks/task-external-1/final-review') {
      state.finalReviewPayload = request.postDataJSON();
      state.task = { ...states.completed, prompt: state.taskPayload.prompt };
      await json(route, { status: 'success', task: state.task });
      return;
    }
    await json(route, { status: 'error', message: `Unexpected agent API request: ${request.method()} ${path}` }, 404);
  });

  return state;
};
