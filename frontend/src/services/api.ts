import axios, { type AxiosInstance, type AxiosResponse } from 'axios';

// ── Core API types ──────────────────────────────────────────────────────────

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface PaperSkeleton {
  abstract?: string;
  introduction?: string;
  [key: string]: unknown;
}

export interface ChatResponse {
  status?: string;
  reply?: string;
  message?: string;
  sentenceSourceMap?: unknown[];
  rag_sources?: unknown[];
  data?: {
    reply?: string;
    sentenceSourceMap?: unknown[];
    rag_sources?: unknown[];
  };
}

export interface UploadResponse {
  status: string;
  pdfId: string;
  title?: string;
  parseStatus?: string;
  parseMessage?: string;
  ragIndexed?: boolean;
  ragChunkCount?: number;
  ragErrorCode?: string;
  paper_structure?: Record<string, unknown>;
  message?: string;
  authors?: string[];
}

export interface CriticalReadingResponse {
  status: string;
  analysis?: Record<string, unknown>;
  message?: string;
  errorCode?: string;
}

export interface BackgroundKnowledgeRequest {
  pdfId: string;
  paperSkeleton?: Record<string, unknown> | null;
  paperStructure?: Record<string, unknown> | null;
  paper_topic?: string | null;
  user_knowledge_level?: string;
  reader_profile?: Record<string, unknown> | null;
  behavior_signals?: Record<string, unknown> | null;
}

export interface SocraticRequest {
  pdfId: string;
  paperSkeleton: Record<string, unknown> | null;
  readingProgress: Record<string, unknown>;
}

export interface SocraticAnswerRequest extends SocraticRequest {
  currentIndex: number;
  currentQuestion: string;
  userAnswer: string;
  turns?: Record<string, unknown>[];
}

export interface TranslatePageRequest {
  pdfId: string;
  pageIndex: number;
  pageText: string;
  paperSkeleton?: Record<string, unknown> | null;
  pageLayout?: Record<string, unknown> | null;
}

export interface TranslatePageOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface ResearchTaskPayload {
  question: string;
  pdfId: string;
  paperSkeleton?: Record<string, unknown> | null;
  allowExternalSearch: boolean;
  allowWebSearch: boolean;
  userConstraints?: string;
  briefPreview?: Record<string, unknown> | null;
}

export interface AgentProjectPayload {
  title: string;
  goal: string;
  paperIds: string[];
}

export interface AgentRunPayload {
  prompt: string;
  focusedPaperIds?: string[];
  constraints?: string;
  domain?: string;
  allowExternalSearch?: boolean;
  allowWebSearch?: boolean;
  allowIterativeSearch?: boolean;
}

export interface PlanReviewPayload {
  planItems: Record<string, unknown>[];
  focusedPaperIds: string[];
  constraints: string;
  reviewNotes: string;
  allowWebSearch?: boolean;
}

export interface FinalReviewPayload {
  decision: string;
  reviewNotes?: string;
}

export interface PaperDraftPayload {
  question: string;
  title: string;
  findings: unknown[];
  evidenceItems: unknown[];
  conflicts: unknown[];
  sourceIds: string[];
}

export interface ResearchMonitorPayload {
  source: string;
  query: string;
  label?: string;
}

// ── API client types ────────────────────────────────────────────────────────

export interface ApiClient extends AxiosInstance {
  // Augmented with response interceptor (strips to response.data)
}

export interface ApiService {
  uploadPdf: (file: File) => Promise<UploadResponse>;
  sendMessage: (message: string, pdfId: string | null, history: ChatMessage[], paperSkeleton: PaperSkeleton | null, signal?: AbortSignal | null) => Promise<ChatResponse>;
  criticalReading: (pdfId: string) => Promise<CriticalReadingResponse>;
  backgroundKnowledge: (params: BackgroundKnowledgeRequest) => Promise<unknown>;
  startSocraticSession: (pdfId: string, paperSkeleton: Record<string, unknown> | null, readingProgress: Record<string, unknown>) => Promise<unknown>;
  answerSocraticSession: (pdfId: string, paperSkeleton: Record<string, unknown> | null, readingProgress: Record<string, unknown>, currentIndex: number, currentQuestion: string, userAnswer: string, turns?: Record<string, unknown>[]) => Promise<unknown>;
  translatePage: (pdfId: string, pageIndex: number, pageText: string, paperSkeleton: Record<string, unknown> | null, pageLayout: Record<string, unknown> | null, options?: TranslatePageOptions) => Promise<unknown>;
  generatePaperDraft: (payload: PaperDraftPayload) => Promise<unknown>;
  createAgentProject: (payload: AgentProjectPayload) => Promise<unknown>;
  createAgentRun: (projectId: string, payload: AgentRunPayload) => Promise<unknown>;
  reviewAgentRunPlan: (runId: string, payload: PlanReviewPayload) => Promise<unknown>;
  reviewAgentRunFinal: (runId: string, payload: FinalReviewPayload) => Promise<unknown>;
  getAgentWorkspace: (projectId: string) => Promise<unknown>;
  getAgentRunArtifacts: (runId: string) => Promise<unknown>;
  getAgentRunTimeline: (runId: string) => Promise<unknown>;
  createResearchTask: (question: string, pdfId: string, paperSkeleton?: Record<string, unknown> | null, userConstraints?: string, briefPreview?: Record<string, unknown> | null, allowExternalSearch?: boolean, allowWebSearch?: boolean) => Promise<unknown>;
  getResearchTask: (taskId: string) => Promise<unknown>;
  createAgentTask: (projectId: string, payload: Record<string, unknown>) => Promise<unknown>;
  listAgentProjectTasks: (projectId: string, limit?: number) => Promise<unknown>;
  listAgentProjects: () => Promise<unknown>;
  getAgentProject: (projectId: string) => Promise<unknown>;
  updateAgentProject: (projectId: string, payload: Record<string, unknown>) => Promise<unknown>;
  deleteAgentProject: (projectId: string) => Promise<unknown>;
  addAgentProjectPapers: (projectId: string, paperIds: string[]) => Promise<unknown>;
  removeAgentProjectPaper: (projectId: string, pdfId: string) => Promise<unknown>;
  getAgentTask: (taskId: string) => Promise<unknown>;
  getAgentRun: (runId: string) => Promise<unknown>;
  cancelAgentTask: (taskId: string) => Promise<unknown>;
  reviewAgentPlan: (taskId: string, payload: Record<string, unknown>) => Promise<unknown>;
  reviewAgentFinal: (taskId: string, payload: Record<string, unknown>) => Promise<unknown>;
  getAgentTrace: (traceId: string) => Promise<unknown>;
  cancelResearchTask: (taskId: string) => Promise<unknown>;
  explainText: (text: string, pdfId: string, pageNumber: number, context?: string) => Promise<unknown>;
  socraticQuestions: (paper_content: string, reading_progress: Record<string, unknown>) => Promise<unknown>;
  uploadCodeExecutionArtifact: (file: File) => Promise<unknown>;
  createCodeExecutionJob: (artifactId: string) => Promise<unknown>;
  listCodeExecutionJobs: () => Promise<unknown>;
  getCodeExecutionJob: (jobId: string) => Promise<unknown>;
  reviewCodeExecution: (jobId: string, decision: string, expectedTaskDigest: string, reason?: string) => Promise<unknown>;
  reviewCodePublication: (jobId: string, decision: string, expectedPublicationDigest: string, reason?: string) => Promise<unknown>;
  getChatHistory: (sessionId: string) => Promise<unknown>;
  previewResearchBrief: (question: string, pdfId: string, paperSkeleton?: Record<string, unknown> | null, userConstraints?: string) => Promise<unknown>;
  reviewResearchPlan: (taskId: string, payload: Record<string, unknown>) => Promise<unknown>;
  reviewResearchFinal: (taskId: string, payload: Record<string, unknown>) => Promise<unknown>;
  getLatestResearchTask: (pdfId: string) => Promise<unknown>;
  getTrace: (traceId: string) => Promise<unknown>;
  getLatestAgentTask: (projectId: string) => Promise<unknown>;
  answerAgentClarification: (runId: string, payload: Record<string, unknown>) => Promise<unknown>;
  createResearchMonitor: (payload: ResearchMonitorPayload) => Promise<unknown>;
  getResearchMonitors: () => Promise<unknown>;
  checkResearchMonitor: (monitorId: string) => Promise<unknown>;
  getResearchMonitorDigest: (monitorId: string) => Promise<unknown>;
  deactivateResearchMonitor: (monitorId: string) => Promise<unknown>;

  // LangGraph Agent Graph
  runAgentGraph: (payload: AgentRunPayload) => Promise<unknown>;
  resumeAgentGraph: (threadId: string, payload: Record<string, unknown>) => Promise<unknown>;
  getAgentGraphState: (threadId: string) => Promise<unknown>;

  // Multi-Agent Debate
  createDebateRun(projectId: string, body: {
    research_prompt: string;
    paper_ids: string[];
    constraints?: Record<string, unknown>;
    num_agents?: number;
  }): Promise<{ status: string; data: any }>;

  getDebateResult(projectId: string, runId: string): Promise<{ status: string; data: any }>;
}

// ── Implementation ──────────────────────────────────────────────────────────

export const resolveApiBaseUrl = (
  env = globalThis.__VITE_ENV__ ?? (typeof import.meta !== 'undefined' ? import.meta.env : undefined),
) => env?.VITE_API_BASE_URL || 'http://localhost:8081/api';

export const resolveAgentApiBaseUrl = (
  env = globalThis.__VITE_ENV__ ?? (typeof import.meta !== 'undefined' ? import.meta.env : undefined),
) => env?.VITE_AGENT_API_BASE_URL || 'http://localhost:8081/api';

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

const isHttpNotFound = (error: unknown): boolean => (error as { response?: { status?: number } })?.response?.status === 404;

const withAgentFallback = async <T>(primaryRequest: () => Promise<T>, fallbackRequest: (() => Promise<T>) | null): Promise<T> => {
  try {
    return await primaryRequest();
  } catch (error) {
    if (isHttpNotFound(error) && fallbackRequest) {
      return fallbackRequest();
    }
    throw error;
  }
};

interface CreateApiServiceOptions {
  agentDirect?: boolean;
}

export const createApiService = (client: ApiClient, agentFallbackClient: ApiClient | null = null, options: CreateApiServiceOptions = {}) => {
  const agentPrimaryClient: ApiClient = options.agentDirect && agentFallbackClient ? agentFallbackClient : client;
  const agentSecondaryClient: ApiClient | null = options.agentDirect ? null : agentFallbackClient;

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

  sendMessage: async (message, pdfId = null, history = [], paperSkeleton = null, signal = undefined) =>
    client.post(
      '/chat',
      {
        message,
        pdfId,
        history,
        paperSkeleton,
      },
      signal ? { signal } : {},
    ),

  getChatHistory: async (sessionId) => client.get(`/chat/history/${encodeURIComponent(sessionId)}`),

  createResearchTask: async (question, pdfId, paperSkeleton = null, userConstraints = '', briefPreview = null, allowExternalSearch = false, allowWebSearch = false) => {
    const payload: Record<string, unknown> = {
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

  translatePage: async (pdfId, pageIndex, pageText, paperSkeleton = null, pageLayout = null, options: TranslatePageOptions = {}) => {
    const timeoutMs = Number(options?.timeoutMs) > 0 ? Number(options.timeoutMs) : 90000;
    const externalSignal: AbortSignal | null = options?.signal || null;
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
    } catch (error: unknown) {
      if (didTimeout || (error as { code?: string })?.code === 'ECONNABORTED') {
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

  // LangGraph Agent Graph
  runAgentGraph: async (payload) =>
    agentPrimaryClient.post('/agent-graph', payload),

  resumeAgentGraph: async (threadId, payload) =>
    agentPrimaryClient.post(`/agent-graph/${encodeURIComponent(threadId)}/resume`, payload),

  getAgentGraphState: async (threadId) =>
    agentPrimaryClient.get(`/agent-graph/${encodeURIComponent(threadId)}`),

  // Multi-Agent Debate
  createDebateRun: (projectId, body) =>
    client.post(`/agent-projects/${projectId}/debate`, body),

  getDebateResult: (projectId, runId) =>
    client.get(`/agent-projects/${projectId}/debate/${runId}`),

  } as ApiService;
};

const apiClient = createApiClient();
const agentFallbackClient = createApiClient('http://localhost:8000/api');

export const apiService = createApiService(apiClient, agentFallbackClient, { agentDirect: false });
export const uploadPdf = apiService.uploadPdf;

export default apiClient;
