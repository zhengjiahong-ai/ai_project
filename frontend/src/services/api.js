import axios from 'axios';

export const resolveApiBaseUrl = (
  env = globalThis.__VITE_ENV__ ?? (typeof import.meta !== 'undefined' ? import.meta.env : undefined),
) => env?.VITE_API_BASE_URL || 'http://localhost:8081/api';

export const resolveAgentApiBaseUrl = (
  env = globalThis.__VITE_ENV__ ?? (typeof import.meta !== 'undefined' ? import.meta.env : undefined),
) => env?.VITE_AGENT_API_BASE_URL || 'http://localhost:8000/api';

export const createApiClient = (baseURL = resolveApiBaseUrl(), axiosInstance = axios) => {
  const client = axiosInstance.create({
    baseURL,
    timeout: 1200000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  client.interceptors.response.use(
    (response) => response.data,
    (error) => {
      const shouldSuppressLog =
        axios.isCancel(error) ||
        error?.name === 'CanceledError' ||
        error?.message === 'canceled' ||
        Boolean(error?.config?.skipErrorLog);
      if (!shouldSuppressLog) {
        console.error('API Error:', error);
      }
      return Promise.reject(error);
    },
  );

  return client;
};

const isHttpNotFound = (error) => error?.response?.status === 404;

const withAgentFallback = async (primaryRequest, fallbackRequest) => {
  try {
    return await primaryRequest();
  } catch (error) {
    if (isHttpNotFound(error) && fallbackRequest) {
      return fallbackRequest();
    }
    throw error;
  }
};

export const createApiService = (client, agentFallbackClient = null, options = {}) => {
  const agentPrimaryClient = options.agentDirect && agentFallbackClient ? agentFallbackClient : client;
  const agentSecondaryClient = options.agentDirect ? null : agentFallbackClient;

  return {
  uploadPdf: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return client.post('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },

  uploadCodeExecutionArtifact: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return client.post('/code-execution-artifacts', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  createCodeExecutionJob: async (artifactId) => client.post('/code-execution-jobs', { artifactId }),
  listCodeExecutionJobs: async () => client.get('/code-execution-jobs'),
  getCodeExecutionJob: async (jobId) => client.get(`/code-execution-jobs/${encodeURIComponent(jobId)}`),
  reviewCodeExecution: async (jobId, decision, expectedTaskDigest, reason = undefined) =>
    client.post(`/code-execution-jobs/${encodeURIComponent(jobId)}/execution-review`, {
      decision,
      expectedTaskDigest,
      ...(reason ? { reason } : {}),
    }),
  reviewCodePublication: async (jobId, decision, expectedPublicationDigest, reason = undefined) =>
    client.post(`/code-execution-jobs/${encodeURIComponent(jobId)}/publication-review`, {
      decision,
      expectedPublicationDigest,
      ...(reason ? { reason } : {}),
    }),

  sendMessage: async (message, pdfId = null, history = [], paperSkeleton = null, signal = null) =>
    client.post(
      '/chat',
      {
        message,
        pdfId,
        history,
        paperSkeleton,
      },
      { signal },
    ),

  getChatHistory: async (sessionId) => client.get(`/chat/history/${encodeURIComponent(sessionId)}`),

  createResearchTask: async (question, pdfId, paperSkeleton = null, userConstraints = '', briefPreview = null, allowExternalSearch = false, allowWebSearch = false) => {
    const payload = {
      question,
      pdfId,
      paperSkeleton,
      allowExternalSearch,
      allowWebSearch,
    };
    if (`${userConstraints || ''}`.trim()) {
      payload.userConstraints = userConstraints;
    }
    if (briefPreview && typeof briefPreview === 'object') {
      payload.briefPreview = briefPreview;
    }
    return client.post('/research-tasks', payload);
  },

  previewResearchBrief: async (question, pdfId, paperSkeleton = null, userConstraints = '') =>
    client.post('/research-tasks/brief-preview', {
      question,
      pdfId,
      paperSkeleton,
      userConstraints,
    }),

  getResearchTask: async (taskId) => client.get(`/research-tasks/${encodeURIComponent(taskId)}`),
  reviewResearchPlan: async (taskId, payload) => client.post(`/research-tasks/${encodeURIComponent(taskId)}/plan-review`, payload),
  reviewResearchFinal: async (taskId, payload) => client.post(`/research-tasks/${encodeURIComponent(taskId)}/final-review`, payload),

  getLatestResearchTask: async (pdfId) =>
    client.get(`/research-tasks/latest?pdfId=${encodeURIComponent(pdfId)}`, { skipErrorLog: true }),

  getTrace: async (traceId) => client.get(`/traces/${encodeURIComponent(traceId)}`),

  createAgentProject: async (payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post('/agent-projects', payload, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.post('/agent-projects', payload) : null,
    ),

  listAgentProjects: async () =>
    withAgentFallback(
      () => agentPrimaryClient.get('/agent-projects', { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get('/agent-projects') : null,
    ),

  getAgentProject: async (projectId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}`, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}`) : null,
    ),

  updateAgentProject: async (projectId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.patch(`/agent-projects/${encodeURIComponent(projectId)}`, payload, { skipErrorLog: true }),
      agentSecondaryClient
        ? () => agentSecondaryClient.patch(`/agent-projects/${encodeURIComponent(projectId)}`, payload)
        : null,
    ),

  deleteAgentProject: async (projectId) =>
    withAgentFallback(
      () => agentPrimaryClient.delete(`/agent-projects/${encodeURIComponent(projectId)}`, { skipErrorLog: true }),
      agentSecondaryClient
        ? () => agentSecondaryClient.delete(`/agent-projects/${encodeURIComponent(projectId)}`)
        : null,
    ),

  addAgentProjectPapers: async (projectId, paperIds) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/papers`, { paperIds }, { skipErrorLog: true }),
      agentSecondaryClient
        ? () => agentSecondaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/papers`, { paperIds })
        : null,
    ),

  removeAgentProjectPaper: async (projectId, pdfId) =>
    withAgentFallback(
      () =>
        agentPrimaryClient.delete(`/agent-projects/${encodeURIComponent(projectId)}/papers/${encodeURIComponent(pdfId)}`, {
          skipErrorLog: true,
        }),
      agentSecondaryClient
        ? () =>
            agentSecondaryClient.delete(
              `/agent-projects/${encodeURIComponent(projectId)}/papers/${encodeURIComponent(pdfId)}`,
            )
        : null,
    ),

  createAgentRun: async (projectId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/runs`, payload, { skipErrorLog: true }),
      agentSecondaryClient
        ? () => agentSecondaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/runs`, payload)
        : null,
    ),

  getAgentWorkspace: async (projectId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}/workspace`, { skipErrorLog: true }),
      agentSecondaryClient
        ? () => agentSecondaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}/workspace`)
        : null,
    ),

  createAgentTask: async (projectId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/tasks`, payload, { skipErrorLog: true }),
      agentSecondaryClient
        ? () => agentSecondaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/tasks`, payload)
        : null,
    ),

  getLatestAgentTask: async (projectId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}/tasks/latest`, { skipErrorLog: true }),
      agentSecondaryClient
        ? () => agentSecondaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}/tasks/latest`)
        : null,
    ),

  listAgentProjectTasks: async (projectId, limit = 20) => {
    const normalizedLimit = Number.isFinite(Number(limit)) && Number(limit) > 0 ? Math.floor(Number(limit)) : 20;
    const path = `/agent-projects/${encodeURIComponent(projectId)}/tasks?limit=${encodeURIComponent(normalizedLimit)}`;
    return withAgentFallback(
      () => agentPrimaryClient.get(path, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get(path) : null,
    );
  },

  getAgentTask: async (taskId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-tasks/${encodeURIComponent(taskId)}`, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get(`/agent-tasks/${encodeURIComponent(taskId)}`) : null,
    ),

  getAgentRun: async (runId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-runs/${encodeURIComponent(runId)}`, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get(`/agent-runs/${encodeURIComponent(runId)}`) : null,
    ),

  getAgentRunArtifacts: async (runId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-runs/${encodeURIComponent(runId)}/artifacts`, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get(`/agent-runs/${encodeURIComponent(runId)}/artifacts`) : null,
    ),

  getAgentRunTimeline: async (runId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-runs/${encodeURIComponent(runId)}/timeline`, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get(`/agent-runs/${encodeURIComponent(runId)}/timeline`) : null,
    ),

  cancelAgentTask: async (taskId) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-tasks/${encodeURIComponent(taskId)}/cancel`, null, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.post(`/agent-tasks/${encodeURIComponent(taskId)}/cancel`) : null,
    ),

  reviewAgentPlan: async (taskId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-tasks/${encodeURIComponent(taskId)}/plan-review`, payload, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.post(`/agent-tasks/${encodeURIComponent(taskId)}/plan-review`, payload) : null,
    ),

  reviewAgentFinal: async (taskId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-tasks/${encodeURIComponent(taskId)}/final-review`, payload, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.post(`/agent-tasks/${encodeURIComponent(taskId)}/final-review`, payload) : null,
    ),

  reviewAgentRunPlan: async (runId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-runs/${encodeURIComponent(runId)}/plan-review`, payload, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.post(`/agent-runs/${encodeURIComponent(runId)}/plan-review`, payload) : null,
    ),

  reviewAgentRunFinal: async (runId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-runs/${encodeURIComponent(runId)}/final-review`, payload, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.post(`/agent-runs/${encodeURIComponent(runId)}/final-review`, payload) : null,
    ),

  getAgentTrace: async (traceId) =>
    withAgentFallback(
      () => agentPrimaryClient.get(`/agent-traces/${encodeURIComponent(traceId)}`, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.get(`/agent-traces/${encodeURIComponent(traceId)}`) : null,
    ),

  cancelResearchTask: async (taskId) =>
    client.post(`/research-tasks/${encodeURIComponent(taskId)}/cancel`),

  explainText: async (text, pdfId, pageNumber, context = '') =>
    client.post('/explain', {
      text,
      pdfId,
      pageNumber,
      context,
    }),

  socraticQuestions: async (paper_content, reading_progress) =>
    client.post('/socratic-questions', {
      paper_content,
      reading_progress,
    }),

  startSocraticSession: async (pdfId, paperSkeleton, readingProgress) =>
    client.post('/socratic-session/start', {
      pdfId,
      paperSkeleton,
      readingProgress,
    }),

  answerSocraticSession: async (
    pdfId,
    paperSkeleton,
    readingProgress,
    currentIndex,
    currentQuestion,
    userAnswer,
    turns = [],
  ) =>
    client.post('/socratic-session/answer', {
      pdfId,
      paperSkeleton,
      readingProgress,
      currentIndex,
      currentQuestion,
      userAnswer,
      turns,
    }),

  criticalReading: async (pdfId) => client.post(`/critical-reading/${encodeURIComponent(pdfId)}`),

  backgroundKnowledge: async ({
    pdfId,
    paperSkeleton = null,
    paperStructure = null,
    paper_topic = null,
    user_knowledge_level = '普通/一般',
    reader_profile = null,
    behavior_signals = null,
  }) =>
    client.post('/background-knowledge', {
      pdfId,
      paperSkeleton,
      paperStructure,
      paper_topic,
      user_knowledge_level,
      reader_profile,
      behavior_signals,
    }),

  translatePage: async (pdfId, pageIndex, pageText, paperSkeleton = null, pageLayout = null, options = {}) => {
    const timeoutMs = Number(options?.timeoutMs) > 0 ? Number(options.timeoutMs) : 90000;
    const externalSignal = options?.signal || null;
    const controller = new AbortController();
    let didTimeout = false;
    const handleExternalAbort = () => controller.abort();
    const timeoutId = setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, timeoutMs);

    if (externalSignal) {
      if (externalSignal.aborted) {
        handleExternalAbort();
      } else {
        externalSignal.addEventListener('abort', handleExternalAbort, { once: true });
      }
    }

    try {
      return await client.post(
        '/translate-page',
        {
          pdfId,
          pageIndex,
          pageText,
          paperSkeleton,
          pageLayout,
        },
        {
          signal: controller.signal,
          timeout: timeoutMs,
          skipErrorLog: true,
        },
      );
    } catch (error) {
      if (didTimeout || error?.code === 'ECONNABORTED') {
        throw new Error('当前页翻译超时，请重试或减少等待时间。');
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', handleExternalAbort);
      }
    }
  },

  answerAgentClarification: async (runId, payload) =>
    withAgentFallback(
      () => agentPrimaryClient.post(`/agent-runs/${encodeURIComponent(runId)}/clarification`, payload, { skipErrorLog: true }),
      agentSecondaryClient ? () => agentSecondaryClient.post(`/agent-runs/${encodeURIComponent(runId)}/clarification`, payload) : null,
    ),

  createResearchMonitor: async (payload) =>
    agentPrimaryClient.post('/research-monitors', payload),

  getResearchMonitors: async () =>
    agentPrimaryClient.get('/research-monitors'),

  checkResearchMonitor: async (monitorId) =>
    agentPrimaryClient.get(`/research-monitors/${encodeURIComponent(monitorId)}/check`),

  getResearchMonitorDigest: async (monitorId) =>
    agentPrimaryClient.get(`/research-monitors/${encodeURIComponent(monitorId)}/digest`),

  deactivateResearchMonitor: async (monitorId) =>
    agentPrimaryClient.delete(`/research-monitors/${encodeURIComponent(monitorId)}`),

  generatePaperDraft: async (payload) =>
    agentPrimaryClient.post('/generate-paper-draft', payload),

  };
};

const apiClient = createApiClient();
const agentFallbackClient = createApiClient(resolveAgentApiBaseUrl());

export const apiService = createApiService(apiClient, agentFallbackClient, { agentDirect: true });
export const uploadPdf = apiService.uploadPdf;

export default apiClient;
