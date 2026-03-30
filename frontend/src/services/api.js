import axios from 'axios';

// 从环境变量获取 API 基础 URL，如果没有则使用默认值
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080/api';
export const uploadPdf = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  return axios.post(`${API_BASE_URL}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000 // 因为 AI 生成慢，设置 1 分钟超时
  });
};
// 创建 axios 实例
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    // 可以在这里添加 token 等认证信息
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    // 统一错误处理
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// API 方法定义
export const apiService = {
  // 上传 PDF 文件
  uploadPdf: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },

  // 发送消息给 AI
  sendMessage: async (message, pdfId = null) => {
    return apiClient.post('/chat', {
      message,
      pdfId,
    });
  },

  // 获取对话历史
  getChatHistory: async (sessionId) => {
    return apiClient.get(`/chat/history/${sessionId}`);
  },

  // 划词解释
  explainText: async (text, pdfId, pageNumber) => {
    return apiClient.post('/explain', {
      text,
      pdfId,
      pageNumber,
    });
  },

  // 引导式学习（苏格拉底式提问）
  socraticQuestions: async (paper_content, reading_progress) => {
    return apiClient.post('/socratic-questions', {
      paper_content,
      reading_progress,
    });
  },

  // 批判性阅读
  criticalReading: async (pdfId) => {
    return apiClient.post(`/critical-reading/${pdfId}`);
  },
};

export default apiClient;
