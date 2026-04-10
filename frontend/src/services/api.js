import axios from 'axios';

export const resolveApiBaseUrl = (
  env = globalThis.__VITE_ENV__ ?? (typeof import.meta !== 'undefined' ? import.meta.env : undefined),
) => env?.VITE_API_BASE_URL || 'http://localhost:8080/api';

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
      console.error('API Error:', error);
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

  translatePage: async (pdfId, pageIndex, pageText, paperSkeleton = null, pageLayout = null) => {
    const controller = new AbortController();
    let didTimeout = false;
    const timeoutId = setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, 90000);

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
          timeout: 90000,
        },
      );
    } catch (error) {
      if (didTimeout || error?.code === 'ECONNABORTED') {
        throw new Error('当前页翻译超时，请重试或减少等待时间。');
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  },
});

const apiClient = createApiClient();

export const apiService = createApiService(apiClient);
export const uploadPdf = apiService.uploadPdf;

export default apiClient;
