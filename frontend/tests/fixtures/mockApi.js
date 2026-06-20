const now = '2026-06-18T10:00:00.000Z';

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

const completedTask = {
  taskId: 'task-smoke-1',
  projectId: 'project-smoke-1',
  traceId: 'trace-smoke-1',
  status: 'succeeded',
  stage: 'done',
  progress: 1,
  prompt: '比较论文的方法、证据与局限性',
  focusedPaperIds: ['paper-smoke-1'],
  planItems: [
    { id: 'retrieve', label: '检索论文证据', detail: '读取方法与结论章节', status: 'done' },
  ],
  events: [
    { eventId: 'event-1', type: 'task_completed', stage: 'done', summary: '研究任务已完成' },
  ],
  toolCalls: [
    { id: 'tool-1', name: 'search_paper', target: 'paper-smoke-1', result: '命中 1 条证据', status: 'succeeded' },
  ],
  evidenceItems: [
    {
      sourceId: 'source-smoke-1',
      pdfId: 'paper-smoke-1',
      sectionId: 'methods',
      pageIndex: 0,
      sourceType: 'paper',
      text: 'Smoke 论文采用可追踪检索流程验证方法设计。',
    },
  ],
  findings: [
    { id: 'finding-1', summary: '方法设计具备明确的证据追踪链路。', sourceIds: ['source-smoke-1'] },
  ],
  comparisonTable: {
    columns: ['论文', '方法', '局限'],
    rows: [['Smoke 测试论文', '证据检索', '仅覆盖单篇 fixture']],
  },
  conflicts: [],
  openQuestions: ['真实多论文结果仍需全栈验证。'],
  draftReport: '## Current Conclusion\nSmoke Agent 已完成证据检索并生成可追踪结论。',
  createdAt: now,
  updatedAt: now,
};

const runningTask = {
  ...completedTask,
  status: 'running',
  stage: 'retrieving',
  progress: 0.55,
  evidenceItems: [],
  findings: [],
  toolCalls: [],
  events: [{ eventId: 'event-0', type: 'retrieval_started', stage: 'retrieving', summary: '正在检索证据' }],
  comparisonTable: { columns: [], rows: [] },
  draftReport: '',
};

const plannedTask = {
  ...runningTask,
  status: 'awaiting_plan_review',
  stage: 'planning',
  progress: 0.2,
  planItems: [{ id: 'retrieve', label: '检索论文证据', detail: '读取方法与结论章节', status: 'pending' }],
};

const draftTask = {
  ...completedTask,
  status: 'awaiting_final_review',
  stage: 'synthesizing',
  progress: 0.95,
  reviewRisks: [{ riskId: 'open:1', type: 'open_question', label: '开放问题', detail: '真实多论文结果仍需全栈验证。', sourceIds: [], reviewStatus: 'pending' }],
};

export const installMockApi = async (page) => {
  const state = {
    project: null,
    task: null,
    taskPollCount: 0,
    projectPayload: null,
    taskPayload: null,
  };

  await page.route('http://localhost:8081/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === 'POST' && url.pathname === '/api/upload') {
      await json(route, {
        status: 'success',
        pdfId: 'paper-smoke-1',
        title: 'Smoke 测试论文',
        authors: ['Pixiu Test'],
        ragIndexed: true,
        ragChunkCount: 1,
        paper_structure: {
          title: 'Smoke 测试论文',
          research_problem: '验证浏览器 smoke 流程',
          core_hypothesis: '路由 mock 可以稳定覆盖 UI 主路径',
          sections: [{ id: 'methods', title: 'Methods', summary: '测试方法' }],
        },
        paper_skeleton: {
          title: 'Smoke 测试论文',
          sections: [{ id: 'methods', title: 'Methods', summary: '测试方法' }],
        },
      });
      return;
    }

    await json(route, { status: 'error', message: `Unexpected reader API request: ${request.method()} ${url.pathname}` }, 404);
  });

  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.method() === 'GET' && path === '/api/agent-projects') {
      await json(route, { status: 'success', projects: state.project ? [state.project] : [] });
      return;
    }

    if (request.method() === 'POST' && path === '/api/agent-projects') {
      state.projectPayload = request.postDataJSON();
      state.project = {
        projectId: 'project-smoke-1',
        ...state.projectPayload,
        latestTaskId: '',
        createdAt: now,
        updatedAt: now,
      };
      await json(route, { status: 'success', project: state.project });
      return;
    }

    if (request.method() === 'GET' && path === '/api/agent-projects/project-smoke-1') {
      await json(route, { status: 'success', project: state.project });
      return;
    }

    if (request.method() === 'GET' && path === '/api/agent-projects/project-smoke-1/tasks') {
      await json(route, {
        status: 'success',
        projectId: 'project-smoke-1',
        tasks: state.task ? [state.task] : [],
        limit: 20,
      });
      return;
    }

    if (request.method() === 'POST' && path === '/api/agent-projects/project-smoke-1/tasks') {
      state.taskPayload = request.postDataJSON();
      state.task = { ...plannedTask, prompt: state.taskPayload.prompt };
      state.project = { ...state.project, latestTaskId: state.task.taskId, updatedAt: now };
      await json(route, { status: 'success', task: state.task });
      return;
    }

    if (request.method() === 'POST' && path === '/api/agent-tasks/task-smoke-1/plan-review') {
      state.planReviewPayload = request.postDataJSON();
      state.task = { ...runningTask, prompt: state.taskPayload.prompt, planItems: state.planReviewPayload.planItems };
      state.taskPollCount = 0;
      await json(route, { status: 'success', task: state.task });
      return;
    }

    if (request.method() === 'GET' && path === '/api/agent-tasks/task-smoke-1') {
      state.taskPollCount += 1;
      state.task = state.taskPollCount >= 2
        ? { ...draftTask, prompt: state.taskPayload.prompt }
        : { ...runningTask, prompt: state.taskPayload.prompt };
      await json(route, { status: 'success', task: state.task });
      return;
    }

    if (request.method() === 'POST' && path === '/api/agent-tasks/task-smoke-1/final-review') {
      state.finalReviewPayload = request.postDataJSON();
      state.task = { ...completedTask, prompt: state.taskPayload.prompt, reviewRisks: draftTask.reviewRisks.map((risk) => ({ ...risk, reviewStatus: 'reviewed' })) };
      await json(route, { status: 'success', task: state.task });
      return;
    }

    await json(route, { status: 'error', message: `Unexpected agent API request: ${request.method()} ${path}` }, 404);
  });

  return state;
};
