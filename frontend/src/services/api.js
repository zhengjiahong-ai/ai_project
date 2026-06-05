import axios from 'axios';

export const resolveApiBaseUrl = (
  env = globalThis.__VITE_ENV__ ?? (typeof import.meta !== 'undefined' ? import.meta.env : undefined),
) => env?.VITE_API_BASE_URL || 'http://localhost:8081/api';

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

export const createApiService = (client) => ({
  uploadPdf: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return client.post('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },

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

  createResearchTask: async (question, pdfId, paperSkeleton = null, userConstraints = '', briefPreview = null) => {
    const payload = {
      question,
      pdfId,
      paperSkeleton,
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

  getLatestResearchTask: async (pdfId) =>
    client.get(`/research-tasks/latest?pdfId=${encodeURIComponent(pdfId)}`),

  getTrace: async (traceId) => client.get(`/traces/${encodeURIComponent(traceId)}`),

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
  }) =>
    client.post('/background-knowledge', {
      pdfId,
      paperSkeleton,
      paperStructure,
      paper_topic,
      user_knowledge_level,
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
});

const apiClient = createApiClient();

export const apiService = createApiService(apiClient);
export const uploadPdf = apiService.uploadPdf;

export default apiClient;
