import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { createApiService, resolveAgentApiBaseUrl, resolveApiBaseUrl } from './api.ts';
import { canReviewExecution, canReviewPublication, groupCodeExecutionJobs } from '../components/codeExecutionApprovalModel.js';


const assertContract = (value, schema, path = 'response') => {
  const typeChecks = {
    object: (item) => item !== null && typeof item === 'object' && !Array.isArray(item),
    array: Array.isArray,
    string: (item) => typeof item === 'string',
    number: (item) => typeof item === 'number' && Number.isFinite(item),
    integer: Number.isInteger,
    boolean: (item) => typeof item === 'boolean',
    null: (item) => item === null,
  };
  if (schema.type) {
    assert.equal(typeChecks[schema.type](value), true, `${path} must be ${schema.type}`);
  }
  if (schema.enum) {
    assert.equal(schema.enum.includes(value), true, `${path} must match its enum`);
  }
  if (schema.type === 'object') {
    for (const key of schema.required || []) {
      assert.equal(Object.hasOwn(value, key), true, `${path}.${key} is required`);
    }
    for (const [key, childSchema] of Object.entries(schema.properties || {})) {
      if (Object.hasOwn(value, key)) {
        assertContract(value[key], childSchema, `${path}.${key}`);
      }
    }
  }
  if (schema.type === 'array' && schema.items) {
    value.forEach((item, index) => assertContract(item, schema.items, `${path}[${index}]`));
  }
};


const run = async () => {
  const pendingExecution = { jobId: 'job-1', status: 'awaiting_approval', approval: { decision: 'pending' } };
  const pendingPublication = { jobId: 'job-2', status: 'succeeded', executionResult: { status: 'succeeded' }, publicationDigest: 'a'.repeat(64), publicationApproval: { decision: 'pending' } };
  assert.equal(canReviewExecution(pendingExecution), true);
  assert.equal(canReviewPublication(pendingPublication), true);
  assert.deepEqual(groupCodeExecutionJobs([pendingExecution, pendingPublication]).map((group) => group.jobs.length), [1, 1, 0]);
  const sharedContract = JSON.parse(
    readFileSync(new URL('../../../contracts/api-contract-smoke.json', import.meta.url), 'utf8'),
  );
  assert.equal(sharedContract.schemaVersion, 1);
  const contractOperations = Object.fromEntries(
    sharedContract.operations.map((operation) => [operation.operation, operation]),
  );
  assert.deepEqual(Object.keys(contractOperations).sort(), [
    'agent-final-review',
    'agent-plan-review',
    'agent-projects',
    'agent-run',
    'agent-run-artifacts',
    'agent-run-final-review',
    'agent-run-plan-review',
    'agent-run-timeline',
    'agent-runs',
    'agent-task',
    'agent-tasks',
    'agent-traces',
    'agent-workspace',
    'background',
    'chat',
    'code-execution-jobs',
    'critical',
    'research',
    'research-final-review',
    'research-plan-review',
    'research-task',
    'trace',
  ]);

  assert.equal(resolveApiBaseUrl({ VITE_API_BASE_URL: 'http://example.com/api' }), 'http://example.com/api');
  assert.equal(resolveAgentApiBaseUrl({ VITE_AGENT_API_BASE_URL: 'http://agent.example.com/api' }), 'http://agent.example.com/api');

  let uploadCall;
  const uploadService = createApiService({
    post: async (url, body, config) => {
      uploadCall = { url, body, config };
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await uploadService.uploadPdf(new Blob(['pdf'], { type: 'application/pdf' }));
  assert.equal(uploadCall.url, '/upload');
  assert.ok(uploadCall.body instanceof FormData);
  assert.equal(uploadCall.config.headers['Content-Type'], 'multipart/form-data');

  await uploadService.uploadCodeExecutionArtifact(new Blob(['a,b\n1,2\n'], { type: 'text/csv' }));
  assert.equal(uploadCall.url, '/code-execution-artifacts');
  assert.ok(uploadCall.body instanceof FormData);

  await uploadService.createCodeExecutionJob('artifact-1');
  assert.equal(uploadCall.url, '/code-execution-jobs');
  assert.deepEqual(uploadCall.body, { artifactId: 'artifact-1' });

  await uploadService.reviewCodeExecution('job/1', 'approved', 'task-digest');
  assert.equal(uploadCall.url, '/code-execution-jobs/job%2F1/execution-review');
  assert.deepEqual(uploadCall.body, { decision: 'approved', expectedTaskDigest: 'task-digest' });

  await uploadService.reviewCodePublication('job/1', 'approved', 'publication-digest');
  assert.equal(uploadCall.url, '/code-execution-jobs/job%2F1/publication-review');
  assert.deepEqual(uploadCall.body, { decision: 'approved', expectedPublicationDigest: 'publication-digest' });

  let historyUrl = '';
  const historyService = createApiService({
    get: async (url) => {
      historyUrl = url;
      return { status: 'success' };
    },
    post: async () => ({}),
  });

  await historyService.getChatHistory('session-1');
  assert.equal(historyUrl, '/chat/history/session-1');

  let createResearchPayload = null;
  let createResearchUrl = '';
  const createResearchService = createApiService({
    post: async (url, body) => {
      createResearchUrl = url;
      createResearchPayload = body;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await createResearchService.createResearchTask('研究问题', 'paper-1', { abstract: 'summary' });
  assert.equal(createResearchUrl, '/research-tasks');
  assert.deepEqual(createResearchPayload, {
    question: '研究问题',
    pdfId: 'paper-1',
    paperSkeleton: { abstract: 'summary' },
    allowExternalSearch: false,
    allowWebSearch: false,
  });

  await createResearchService.createResearchTask('研究问题', 'paper-1', null, '', null, true);
  assert.equal(createResearchPayload.allowExternalSearch, true);

  await createResearchService.previewResearchBrief('研究问题', 'paper-1', { abstract: 'summary' }, '重点看实验');
  assert.equal(createResearchUrl, '/research-tasks/brief-preview');
  assert.deepEqual(createResearchPayload, {
    question: '研究问题',
    pdfId: 'paper-1',
    paperSkeleton: { abstract: 'summary' },
    userConstraints: '重点看实验',
  });

  let getResearchUrl = '';
  const getResearchService = createApiService({
    get: async (url) => {
      getResearchUrl = url;
      return { status: 'success' };
    },
    post: async () => ({}),
  });

  await getResearchService.getResearchTask('task-1');
  assert.equal(getResearchUrl, '/research-tasks/task-1');

  await getResearchService.getLatestResearchTask('paper 1');
  assert.equal(getResearchUrl, '/research-tasks/latest?pdfId=paper%201');

  await getResearchService.getTrace('trace 1');
  assert.equal(getResearchUrl, '/traces/trace%201');

  let agentUrl = '';
  let agentPayload = null;
  const agentService = createApiService({
    get: async (url) => {
      agentUrl = url;
      return { status: 'success' };
    },
    post: async (url, body) => {
      agentUrl = url;
      agentPayload = body;
      return { status: 'success' };
    },
    patch: async (url, body) => {
      agentUrl = url;
      agentPayload = body;
      return { status: 'success' };
    },
    delete: async (url) => {
      agentUrl = url;
      return { status: 'success' };
    },
  });

  await agentService.createAgentProject({ title: 'Agent 项目', paperIds: ['paper-1'] });
  assert.equal(agentUrl, '/agent-projects');
  assert.deepEqual(agentPayload, { title: 'Agent 项目', paperIds: ['paper-1'] });

  await agentService.listAgentProjects();
  assert.equal(agentUrl, '/agent-projects');

  await agentService.getAgentProject('project 1');
  assert.equal(agentUrl, '/agent-projects/project%201');

  await agentService.updateAgentProject('project 1', { goal: 'new goal' });
  assert.equal(agentUrl, '/agent-projects/project%201');
  assert.deepEqual(agentPayload, { goal: 'new goal' });

  await agentService.addAgentProjectPapers('project 1', ['paper-2']);
  assert.equal(agentUrl, '/agent-projects/project%201/papers');
  assert.deepEqual(agentPayload, { paperIds: ['paper-2'] });

  await agentService.removeAgentProjectPaper('project 1', 'paper 2');
  assert.equal(agentUrl, '/agent-projects/project%201/papers/paper%202');

  await agentService.deleteAgentProject('project 1');
  assert.equal(agentUrl, '/agent-projects/project%201');

  await agentService.createAgentTask('project 1', { prompt: 'compare' });
  assert.equal(agentUrl, '/agent-projects/project%201/tasks');
  assert.deepEqual(agentPayload, { prompt: 'compare' });

  await agentService.createAgentTask('project 1', { prompt: 'compare', allowExternalSearch: true });
  assert.equal(agentPayload.allowExternalSearch, true);

  await agentService.createAgentRun('project 1', { prompt: 'compare' });
  assert.equal(agentUrl, '/agent-projects/project%201/runs');
  assert.deepEqual(agentPayload, { prompt: 'compare' });

  await agentService.getAgentWorkspace('project 1');
  assert.equal(agentUrl, '/agent-projects/project%201/workspace');

  await agentService.getLatestAgentTask('project 1');
  assert.equal(agentUrl, '/agent-projects/project%201/tasks/latest');

  await agentService.listAgentProjectTasks('project 1', 20);
  assert.equal(agentUrl, '/agent-projects/project%201/tasks?limit=20');

  await agentService.getAgentTask('task 1');
  assert.equal(agentUrl, '/agent-tasks/task%201');

  await agentService.getAgentRun('task 1');
  assert.equal(agentUrl, '/agent-runs/task%201');

  await agentService.getAgentRunArtifacts('task 1');
  assert.equal(agentUrl, '/agent-runs/task%201/artifacts');

  await agentService.getAgentRunTimeline('task 1');
  assert.equal(agentUrl, '/agent-runs/task%201/timeline');

  await agentService.cancelAgentTask('task 1');
  assert.equal(agentUrl, '/agent-tasks/task%201/cancel');

  await agentService.reviewAgentRunPlan('task 1', { planItems: [] });
  assert.equal(agentUrl, '/agent-runs/task%201/plan-review');
  assert.deepEqual(agentPayload, { planItems: [] });

  await agentService.reviewAgentRunFinal('task 1', { riskReviews: [] });
  assert.equal(agentUrl, '/agent-runs/task%201/final-review');
  assert.deepEqual(agentPayload, { riskReviews: [] });

  await agentService.getAgentTrace('trace 1');
  assert.equal(agentUrl, '/agent-traces/trace%201');

  const agentFallbackCalls = [];
  const agentFallbackService = createApiService(
    {
      get: async (url) => {
        agentFallbackCalls.push(`primary:${url}`);
        const error = new Error('not found');
        error.response = { status: 404 };
        throw error;
      },
      post: async () => ({}),
      patch: async () => ({}),
      delete: async (url) => {
        agentFallbackCalls.push(`primary:${url}`);
        const error = new Error('not found');
        error.response = { status: 404 };
        throw error;
      },
    },
    {
      get: async (url) => {
        agentFallbackCalls.push(`fallback:${url}`);
        return { status: 'success', projects: [] };
      },
      delete: async (url) => {
        agentFallbackCalls.push(`fallback:${url}`);
        return { status: 'success', projectId: 'project 1' };
      },
    },
  );

  await agentFallbackService.listAgentProjects();
  assert.deepEqual(agentFallbackCalls, ['primary:/agent-projects', 'fallback:/agent-projects']);
  agentFallbackCalls.length = 0;

  await agentFallbackService.deleteAgentProject('project 1');
  assert.deepEqual(agentFallbackCalls, [
    'primary:/agent-projects/project%201',
    'fallback:/agent-projects/project%201',
  ]);
  agentFallbackCalls.length = 0;

  await agentFallbackService.listAgentProjectTasks('project 1', 20);
  assert.deepEqual(agentFallbackCalls, [
    'primary:/agent-projects/project%201/tasks?limit=20',
    'fallback:/agent-projects/project%201/tasks?limit=20',
  ]);
  agentFallbackCalls.length = 0;

  await agentFallbackService.getAgentWorkspace('project 1');
  assert.deepEqual(agentFallbackCalls, [
    'primary:/agent-projects/project%201/workspace',
    'fallback:/agent-projects/project%201/workspace',
  ]);

  let cancelResearchUrl = '';
  const cancelResearchService = createApiService({
    post: async (url) => {
      cancelResearchUrl = url;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await cancelResearchService.cancelResearchTask('task-1');
  assert.equal(cancelResearchUrl, '/research-tasks/task-1/cancel');

  let criticalReadingUrl = '';
  const criticalReadingService = createApiService({
    post: async (url) => {
      criticalReadingUrl = url;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await criticalReadingService.criticalReading('paper-1');
  assert.equal(criticalReadingUrl, '/critical-reading/paper-1');

  let backgroundPayload = null;
  let backgroundUrl = '';
  const backgroundService = createApiService({
    post: async (url, body) => {
      backgroundUrl = url;
      backgroundPayload = body;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await backgroundService.backgroundKnowledge({
    pdfId: 'paper-1',
    paperSkeleton: { abstract: 'summary' },
    paperStructure: { research_problem: 'RAG' },
    paper_topic: 'RAG',
    user_knowledge_level: '进阶',
    reader_profile: {
      selfAssessedFamiliarity: '一般',
      preferredDepth: '深入',
      learningGoal: '理解方法链路',
      knownConcepts: ['Transformer'],
      confusingConcepts: ['图检索'],
    },
    behavior_signals: {
      questionCount: 3,
      recentQuestions: ['为什么要图检索'],
    },
  });
  assert.equal(backgroundUrl, '/background-knowledge');
  assert.deepEqual(backgroundPayload, {
    pdfId: 'paper-1',
    paperSkeleton: { abstract: 'summary' },
    paperStructure: { research_problem: 'RAG' },
    paper_topic: 'RAG',
    user_knowledge_level: '进阶',
    reader_profile: {
      selfAssessedFamiliarity: '一般',
      preferredDepth: '深入',
      learningGoal: '理解方法链路',
      knownConcepts: ['Transformer'],
      confusingConcepts: ['图检索'],
    },
    behavior_signals: {
      questionCount: 3,
      recentQuestions: ['为什么要图检索'],
    },
  });

  let explainPayload = null;
  let explainUrl = '';
  const explainService = createApiService({
    post: async (url, body) => {
      explainUrl = url;
      explainPayload = body;
      return { status: 'success', explanation: '解释' };
    },
    get: async () => ({}),
  });

  await explainService.explainText('contrastive loss', 'paper-1', 4, 'This page introduces contrastive learning.');
  assert.equal(explainUrl, '/explain');
  assert.deepEqual(explainPayload, {
    text: 'contrastive loss',
    pdfId: 'paper-1',
    pageNumber: 4,
    context: 'This page introduces contrastive learning.',
  });

  let translatePayload = null;
  let translateUrl = '';
  let translateConfig = null;
  const translationService = createApiService({
    post: async (url, body, config) => {
      translateUrl = url;
      translatePayload = body;
      translateConfig = config;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await translationService.translatePage(
    'paper-1',
    3,
    'Source text',
    { abstract: 'summary' },
    {
      viewport: { width: 600, height: 800 },
      blocks: [{ id: 'block-1', text: 'Source text', bbox: { left: 0.1, top: 0.1, width: 0.2, height: 0.1 } }],
      excludedZonesVersion: 1,
    },
  );
  assert.equal(translateUrl, '/translate-page');
  assert.deepEqual(translatePayload, {
    pdfId: 'paper-1',
    pageIndex: 3,
    pageText: 'Source text',
    paperSkeleton: { abstract: 'summary' },
    pageLayout: {
      viewport: { width: 600, height: 800 },
      blocks: [{ id: 'block-1', text: 'Source text', bbox: { left: 0.1, top: 0.1, width: 0.2, height: 0.1 } }],
      excludedZonesVersion: 1,
    },
  });
  assert.equal(translateConfig.timeout, 90000);
  assert.ok(translateConfig.signal);
  assert.equal(translateConfig.skipErrorLog, true);

  let customTranslateConfig = null;
  const customTranslationService = createApiService({
    post: async (_url, _body, config) => {
      customTranslateConfig = config;
      return { status: 'success' };
    },
    get: async () => ({}),
  });
  const customController = new AbortController();
  await customTranslationService.translatePage('paper-1', 1, 'Source text', null, null, {
    timeoutMs: 12345,
    signal: customController.signal,
  });
  assert.equal(customTranslateConfig.timeout, 12345);
  assert.ok(customTranslateConfig.signal);
  assert.equal(customTranslateConfig.skipErrorLog, true);

  const readerCalls = [];
  const readerContractClient = {
    post: async (url, body) => {
      readerCalls.push({ method: 'POST', url, body });
      const operation = sharedContract.operations.find((item) => item.frontendPath === url);
      return operation.gatewayResponse;
    },
    get: async (url) => {
      readerCalls.push({ method: 'GET', url });
      const operation = sharedContract.operations.find((item) => item.frontendPath === url);
      return operation.gatewayResponse;
    },
  };
  const agentCalls = [];
  const agentContractClient = {
    post: async (url, body) => {
      agentCalls.push({ method: 'POST', url, body });
      const operation = sharedContract.operations.find((item) => item.frontendPath === url);
      return operation.gatewayResponse;
    },
    get: async (url) => {
      agentCalls.push({ method: 'GET', url });
      const operation = sharedContract.operations.find((item) => item.frontendPath === url);
      return operation.gatewayResponse;
    },
  };
  const contractService = createApiService(readerContractClient, agentContractClient, { agentDirect: true });

  const chatContract = contractOperations.chat;
  const chatResponse = await contractService.sendMessage(
    chatContract.frontendRequest.message,
    chatContract.frontendRequest.pdfId,
    chatContract.frontendRequest.history,
    chatContract.frontendRequest.paperSkeleton,
  );
  assert.deepEqual(readerCalls.at(-1), {
    method: chatContract.method,
    url: chatContract.frontendPath,
    body: chatContract.frontendRequest,
  });
  assertContract(chatResponse, chatContract.pythonResponseContract);

  const criticalContract = contractOperations.critical;
  const criticalResponse = await contractService.criticalReading('paper-contract-1');
  assert.deepEqual(readerCalls.at(-1), {
    method: criticalContract.method,
    url: criticalContract.frontendPath,
    body: undefined,
  });
  assertContract(criticalResponse.analysis, criticalContract.pythonResponseContract, 'response.analysis');

  const backgroundContract = contractOperations.background;
  const backgroundResponse = await contractService.backgroundKnowledge(backgroundContract.frontendRequest);
  assert.deepEqual(readerCalls.at(-1), {
    method: backgroundContract.method,
    url: backgroundContract.frontendPath,
    body: backgroundContract.frontendRequest,
  });
  assertContract(backgroundResponse, backgroundContract.pythonResponseContract);

  const researchContract = contractOperations.research;
  const researchRequest = researchContract.frontendRequest;
  const researchResponse = await contractService.createResearchTask(
    researchRequest.question,
    researchRequest.pdfId,
    researchRequest.paperSkeleton,
    researchRequest.userConstraints,
    researchRequest.briefPreview,
  );
  assert.deepEqual(readerCalls.at(-1), {
    method: researchContract.method,
    url: researchContract.frontendPath,
    body: { ...researchRequest, allowWebSearch: false },
  });
  assertContract(researchResponse, researchContract.pythonResponseContract);

  const researchPlanContract = contractOperations['research-plan-review'];
  const researchPlanResponse = await contractService.reviewResearchPlan(
    'research-task-contract-1',
    researchPlanContract.frontendRequest,
  );
  assert.deepEqual(readerCalls.at(-1), {
    method: researchPlanContract.method,
    url: researchPlanContract.frontendPath,
    body: researchPlanContract.frontendRequest,
  });
  assertContract(researchPlanResponse, researchPlanContract.pythonResponseContract);

  const researchTaskContract = contractOperations['research-task'];
  const researchTaskResponse = await contractService.getResearchTask('research-task-contract-1');
  assert.deepEqual(readerCalls.at(-1), {
    method: researchTaskContract.method,
    url: researchTaskContract.frontendPath,
  });
  assertContract(researchTaskResponse, researchTaskContract.pythonResponseContract);

  const researchFinalContract = contractOperations['research-final-review'];
  const researchFinalResponse = await contractService.reviewResearchFinal(
    'research-task-contract-1',
    researchFinalContract.frontendRequest,
  );
  assert.deepEqual(readerCalls.at(-1), {
    method: researchFinalContract.method,
    url: researchFinalContract.frontendPath,
    body: researchFinalContract.frontendRequest,
  });
  assertContract(researchFinalResponse, researchFinalContract.pythonResponseContract);

  const traceContract = contractOperations.trace;
  const traceResponse = await contractService.getTrace('trace-contract-1');
  assert.deepEqual(readerCalls.at(-1), { method: traceContract.method, url: traceContract.frontendPath });
  assertContract(traceResponse, traceContract.pythonResponseContract);

  const projectContract = contractOperations['agent-projects'];
  const projectResponse = await contractService.createAgentProject(projectContract.frontendRequest);
  assert.deepEqual(agentCalls.at(-1), {
    method: projectContract.method,
    url: projectContract.frontendPath,
    body: projectContract.frontendRequest,
  });
  assertContract(projectResponse, projectContract.pythonResponseContract);

  const taskContract = contractOperations['agent-tasks'];
  const taskResponse = await contractService.createAgentTask('project-contract-1', taskContract.frontendRequest);
  assert.deepEqual(agentCalls.at(-1), {
    method: taskContract.method,
    url: taskContract.frontendPath,
    body: taskContract.frontendRequest,
  });
  assertContract(taskResponse, taskContract.pythonResponseContract);

  const workspaceContract = contractOperations['agent-workspace'];
  const workspaceResponse = await contractService.getAgentWorkspace('project-contract-1');
  assert.deepEqual(agentCalls.at(-1), {
    method: workspaceContract.method,
    url: workspaceContract.frontendPath,
  });
  assertContract(workspaceResponse, workspaceContract.pythonResponseContract);

  const runsContract = contractOperations['agent-runs'];
  const runsResponse = await contractService.createAgentRun('project-contract-1', runsContract.frontendRequest);
  assert.deepEqual(agentCalls.at(-1), {
    method: runsContract.method,
    url: runsContract.frontendPath,
    body: runsContract.frontendRequest,
  });
  assertContract(runsResponse, runsContract.pythonResponseContract);

  const agentPlanContract = contractOperations['agent-plan-review'];
  const agentPlanResponse = await contractService.reviewAgentPlan(
    'agent-task-contract-1',
    agentPlanContract.frontendRequest,
  );
  assert.deepEqual(agentCalls.at(-1), {
    method: agentPlanContract.method,
    url: agentPlanContract.frontendPath,
    body: agentPlanContract.frontendRequest,
  });
  assertContract(agentPlanResponse, agentPlanContract.pythonResponseContract);

  const agentTaskContract = contractOperations['agent-task'];
  const agentTaskResponse = await contractService.getAgentTask('agent-task-contract-1');
  assert.deepEqual(agentCalls.at(-1), {
    method: agentTaskContract.method,
    url: agentTaskContract.frontendPath,
  });
  assertContract(agentTaskResponse, agentTaskContract.pythonResponseContract);

  const agentRunContract = contractOperations['agent-run'];
  const agentRunResponse = await contractService.getAgentRun('agent-run-contract-1');
  assert.deepEqual(agentCalls.at(-1), {
    method: agentRunContract.method,
    url: agentRunContract.frontendPath,
  });
  assertContract(agentRunResponse, agentRunContract.pythonResponseContract);

  const agentFinalContract = contractOperations['agent-final-review'];
  const agentFinalResponse = await contractService.reviewAgentFinal(
    'agent-task-contract-1',
    agentFinalContract.frontendRequest,
  );
  assert.deepEqual(agentCalls.at(-1), {
    method: agentFinalContract.method,
    url: agentFinalContract.frontendPath,
    body: agentFinalContract.frontendRequest,
  });
  assertContract(agentFinalResponse, agentFinalContract.pythonResponseContract);

  const agentRunPlanContract = contractOperations['agent-run-plan-review'];
  const agentRunPlanResponse = await contractService.reviewAgentRunPlan(
    'agent-run-contract-1',
    agentRunPlanContract.frontendRequest,
  );
  assert.deepEqual(agentCalls.at(-1), {
    method: agentRunPlanContract.method,
    url: agentRunPlanContract.frontendPath,
    body: agentRunPlanContract.frontendRequest,
  });
  assertContract(agentRunPlanResponse, agentRunPlanContract.pythonResponseContract);

  const agentRunFinalContract = contractOperations['agent-run-final-review'];
  const agentRunFinalResponse = await contractService.reviewAgentRunFinal(
    'agent-run-contract-1',
    agentRunFinalContract.frontendRequest,
  );
  assert.deepEqual(agentCalls.at(-1), {
    method: agentRunFinalContract.method,
    url: agentRunFinalContract.frontendPath,
    body: agentRunFinalContract.frontendRequest,
  });
  assertContract(agentRunFinalResponse, agentRunFinalContract.pythonResponseContract);

  const agentRunArtifactsContract = contractOperations['agent-run-artifacts'];
  const agentRunArtifactsResponse = await contractService.getAgentRunArtifacts('agent-run-contract-1');
  assert.deepEqual(agentCalls.at(-1), {
    method: agentRunArtifactsContract.method,
    url: agentRunArtifactsContract.frontendPath,
  });
  assertContract(agentRunArtifactsResponse, agentRunArtifactsContract.pythonResponseContract);

  const agentRunTimelineContract = contractOperations['agent-run-timeline'];
  const agentRunTimelineResponse = await contractService.getAgentRunTimeline('agent-run-contract-1');
  assert.deepEqual(agentCalls.at(-1), {
    method: agentRunTimelineContract.method,
    url: agentRunTimelineContract.frontendPath,
  });
  assertContract(agentRunTimelineResponse, agentRunTimelineContract.pythonResponseContract);

  const agentTraceContract = contractOperations['agent-traces'];
  const agentTraceResponse = await contractService.getAgentTrace('agent-trace-contract-1');
  assert.deepEqual(agentCalls.at(-1), {
    method: agentTraceContract.method,
    url: agentTraceContract.frontendPath,
  });
  assertContract(agentTraceResponse, agentTraceContract.pythonResponseContract);

  console.log('frontend api smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
